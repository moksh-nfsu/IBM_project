"""M6: Threat brief renderer (PLAN.md section 11).

render_brief(intel, analyst, analyst_assessment=None) fills templates/brief.html
(Jinja2) and saves src/outputs/<brief_id>.html. The analyst assessment is
normally drafted by IBM Bob through the MCP server; without it, a deterministic
assessment is written from the intel so the brief is always complete.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from threatlens.correlation import IST, STATES, STATE_RANK, _to_dt
from threatlens.paths import OUTPUTS, TEMPLATES

STATE_COLOURS = {"DETECTED": "#8a8a8a", "COORDINATED": "#1f5fbf", "AMPLIFYING": "#d4a106",
                 "ESCALATING": "#e06c00", "MOBILIZATION": "#c0161b"}
_MAX_EVIDENCE = 20

_env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
_env.filters["hhmm"] = lambda s: _to_dt(s).astimezone(IST).strftime("%H:%M") if s else "—"
_env.filters["when"] = lambda s: _to_dt(s).astimezone(IST).strftime("%a %d %b %Y, %H:%M IST") if s else "—"


def countdown(planned: dict | None) -> str:
    if not planned:
        return "no planned gathering found"
    h = planned["hours_from_snapshot"]
    return f"in {h:.1f} h from the snapshot" if h >= 0 else f"{-h:.1f} h before the snapshot — already passed"


def bluf(intel: dict) -> list[str]:
    """Three deterministic lines: what, where, current state + planned-event countdown."""
    c, cls = intel["_cluster"], intel["_classification"]
    start, end = _to_dt(c["start"]).strftime("%H:%M"), _to_dt(c["end"]).strftime("%H:%M")
    target = f" targeting {cls['target']}" if cls.get("target") else ""
    what = (f"WHAT: {len(c['account_ids'])} accounts ran a coordinated {intel['label']} campaign{target} under "
            f"{intel['_main_hashtag']} ({len(c['post_ids'])} posts, {start}–{end} IST; "
            f"narrative {intel['narrative']['path']}).")
    pe = intel["offline"]["planned_event"]
    wheres = []
    if pe:
        wheres.append(f"posts call people to {pe['place']}")
    wheres += [f"{m['incident_id']} ({m['confidence']}, {m['note']})" for m in intel["offline"]["matches"]]
    districts = ", ".join(sorted(c.get("districts", {}), key=lambda d: -c["districts"][d])[:2])
    where = "WHERE: " + ("; ".join(wheres) if wheres else "no place named in the posts") + \
            f". Accounts mostly from {districts}."
    top = next(t for t in intel["triggers"] if t["state"] == intel["state"])
    state = f"STATE: {intel['state']} (trigger {top['id']}: {top['observed']})"
    if pe:
        state += f"; planned gathering {_env.filters['when'](pe['time'])}, {countdown(pe)}."
    else:
        state += "."
    return [what, where, state]


def default_assessment(intel: dict) -> str:
    """Fact-only assessment used when Bob has not drafted one. Every claim cites post ids."""
    def ids(xs):
        return "[" + ", ".join(xs[:3]) + "]"
    c, cls = intel["_cluster"], intel["_classification"]
    lines = [f"ThreatLens assesses {intel['campaign_id']} ({intel['_main_hashtag']}) as {intel['label']} "
             f"in state {intel['state']}."]
    for t in intel["triggers"]:
        if t["counts_toward_state"] and STATE_RANK[t["state"]] >= 1:
            lines.append(f"{t['id']} ({t['state']}): {t['observed']} {ids(t['evidence_post_ids'])}.")
    if cls.get("evidence_quote"):
        lines.append(f"Key post: \"{cls['evidence_quote']}\" [{cls['evidence_post_id']}].")
    for m in intel["offline"]["matches"]:
        lines.append(f"{m['incident_id']} matched with {m['confidence']} confidence: {m['note']} "
                     f"{ids(m['evidence_post_ids'])}.")
    pe = intel["offline"]["planned_event"]
    if pe:
        lines.append(f"Planned gathering at {pe['place']}, {_env.filters['when'](pe['time'])} "
                     f"({countdown(pe)}) {ids(pe['evidence_post_ids'])}.")
    lines.append(f"{len(c['account_ids'])} accounts, coordination score {c['coordination_score']}/100. "
                 "Human review required before any action.")
    return " ".join(lines)


def _evidence_rows(intel: dict) -> list[tuple[str, dict]]:
    """Most important cited posts first (triggers, planned event, key post), max 20."""
    idx = intel["evidence_index"]
    order = [p for t in intel["triggers"] if t["fired"] for p in t["evidence_post_ids"]]
    order += (intel["offline"]["planned_event"] or {}).get("evidence_post_ids", [])
    order += [intel["_classification"].get("evidence_post_id")] + sorted(idx, key=lambda p: idx[p]["timestamp"])
    pids = [p for p in dict.fromkeys(order) if p in idx][:_MAX_EVIDENCE]
    return [(p, idx[p]) for p in sorted(pids, key=lambda p: idx[p]["timestamp"])]


def render_brief(intel: dict, analyst: str, analyst_assessment: str | None = None) -> tuple[str, str, Path]:
    """Render and save the brief. Returns (brief_id, html, path)."""
    now = datetime.now(IST)
    snap = _to_dt(intel["_snapshot_time"])
    brief_id = f"TB-{snap.strftime('%Y%m%d')}-{intel['campaign_id']}-{now.strftime('%H%M')}"
    analyst = (analyst or "").strip() or "Duty analyst"
    if analyst_assessment and analyst_assessment.strip():
        assessment = analyst_assessment.strip()
        label = f"Drafted by IBM Bob from campaign intelligence; reviewed by {analyst}"
    else:
        assessment = default_assessment(intel)
        label = f"Deterministic assessment generated by ThreatLens from the intel; reviewed by {analyst}"
    reached = {h["state"] for h in intel["state_history"]}
    html = _env.get_template("brief.html").render(
        intel=intel, cluster=intel["_cluster"], brief_id=brief_id, analyst=analyst,
        generated_at=now.strftime("%d %b %Y, %H:%M IST"),
        snapshot=snap.strftime("%d %b %Y, %H:%M IST"), main_hashtag=intel["_main_hashtag"],
        bluf=bluf(intel), assessment=assessment, assessment_label=label,
        states=STATES, reached=reached, colours=STATE_COLOURS, state_colour=STATE_COLOURS[intel["state"]],
        countdown=countdown(intel["offline"]["planned_event"]), evidence=_evidence_rows(intel),
    )
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    path = OUTPUTS / f"{brief_id}.html"
    path.write_text(html, encoding="utf-8")
    return brief_id, html, path
