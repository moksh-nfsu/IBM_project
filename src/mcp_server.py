"""ThreatLens MCP server: the tools IBM Bob calls at runtime (PLAN.md section 11).

Tools
  list_campaigns(previous_cutoff, current_cutoff)   campaigns with label, state, hashtag, planned event
  get_campaign_intel(campaign_id)                   full schema-4.7 intel (+ cluster facts)
  get_posts(post_ids)                               evidence rows (masked text, sha256)
  list_violations(min_severity)                     per-post BNS / IT Act violations with explanations
  render_threat_brief(campaign_id, analyst, analyst_assessment)   writes the HTML brief

Run from src/:  python mcp_server.py   (stdio transport; register it in Bob as
command "python", args ["mcp_server.py"], working directory src/).
The analysis runs once per cutoff pair and is kept in memory. LLM_MODE from
src/.env applies (default auto: cache -> IBM Bob -> rules).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP
except ImportError:  # mcp 2.x renamed FastMCP to MCPServer (same decorator API)
    from mcp.server.mcpserver import MCPServer as FastMCP

from threatlens.brief import render_brief
from threatlens.pipeline import DEFAULT_CURRENT, DEFAULT_PREVIOUS, analyze, load_sample
from threatlens.schema import post_sha256

IST = timezone(timedelta(hours=5, minutes=30))
mcp = FastMCP("ThreatLens")

_data: dict = {}
_results: dict[tuple[str, str], dict] = {}
_active: tuple[str, str] = (DEFAULT_PREVIOUS, DEFAULT_CURRENT)


def _cutoff(value: str) -> str:
    """Accept '2026-09-26T14:10', '14:10' or a full ISO string; return ISO with the IST offset."""
    value = (value or "").strip()
    if len(value) <= 5 and ":" in value:
        value = f"2026-09-26T{value}"
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=IST)).isoformat()


def _result(previous_cutoff: str | None = None, current_cutoff: str | None = None) -> dict:
    global _active
    if previous_cutoff or current_cutoff:
        _active = (_cutoff(previous_cutoff or _active[0]), _cutoff(current_cutoff or _active[1]))
    if _active not in _results:
        if not _data:
            _data["df"], _data["incidents"] = load_sample()
        mode = os.getenv("LLM_MODE", "auto")
        _results[_active] = analyze(_data["df"], _data["incidents"], *_active,
                                    llm_mode=mode if mode in ("auto", "bob", "rules") else "auto")
    return _results[_active]


def _find(campaign_id: str) -> dict | None:
    return next((c for c in _result()["campaigns"] if c["campaign_id"] == campaign_id.strip().upper()), None)


def _public(c: dict) -> dict:
    """Schema-4.7 intel without internal keys, plus the cluster facts Bob needs."""
    out = {k: v for k, v in c.items() if not k.startswith("_")}
    cl, cls = c["_cluster"], c["_classification"]
    out["cluster_facts"] = {
        "main_hashtag": c["_main_hashtag"], "accounts": len(cl["account_ids"]), "posts": len(cl["post_ids"]),
        "start": cl["start"], "end": cl["end"], "detected_at": cl["detected_at"],
        "coordination_score": cl["coordination_score"], "contributions": cl["contributions"],
        "districts": cl["districts"], "snapshot_time": c["_snapshot_time"],
    }
    out["classification"] = cls
    return json.loads(json.dumps(out, ensure_ascii=False, default=str))


@mcp.tool()
def list_campaigns(previous_cutoff: str = "2026-09-26T14:10", current_cutoff: str = "2026-09-26T23:59") -> list[dict]:
    """List the campaigns detected at current_cutoff (compared with previous_cutoff), highest state first.

    Cutoffs are IST times on 2026-09-26, e.g. "2026-09-26T14:10" or "14:10".
    """
    rows = []
    for c in _result(previous_cutoff, current_cutoff)["campaigns"]:
        pe = c["offline"]["planned_event"]
        wc = c["what_changed"]
        rows.append({
            "campaign_id": c["campaign_id"], "label": c["label"], "state": c["state"],
            "main_hashtag": c["_main_hashtag"], "accounts": len(c["_cluster"]["account_ids"]),
            "posts": len(c["_cluster"]["post_ids"]),
            "planned_event": {"place": pe["place"], "time": pe["time"], "hours_from_snapshot": pe["hours_from_snapshot"]}
            if pe else None,
            "change": "NEW" if wc["is_new_campaign"] else ("CHANGED" if wc["items"] else "UNCHANGED"),
        })
    return rows


@mcp.tool()
def get_campaign_intel(campaign_id: str) -> dict:
    """Full evidence-linked intelligence for one campaign (e.g. "CMP-1"), from the last list_campaigns cutoffs."""
    c = _find(campaign_id)
    if c is None:
        return {"error": f"Unknown campaign {campaign_id!r}. Call list_campaigns first.",
                "available": [x["campaign_id"] for x in _result()["campaigns"]]}
    return _public(c)


@mcp.tool()
def get_posts(post_ids: list[str]) -> list[dict]:
    """Evidence rows for the given post ids: handle, IST timestamp, PII-masked text, sha256."""
    _result()
    df = _data["df"].set_index("post_id", drop=False)
    rows = []
    for pid in post_ids:
        if pid in df.index:
            r = df.loc[pid]
            rows.append({"post_id": pid, "handle": r["handle"], "timestamp": r["timestamp"].isoformat(),
                         "text_masked": r["text_masked"], "hashtags": list(r["hashtags"]),
                         "sha256": post_sha256(r)})
        else:
            rows.append({"post_id": pid, "error": "not found"})
    return rows


@mcp.tool()
def list_violations(min_severity: str = "high") -> list[dict]:
    """Posts that violate BNS / IT Act provisions, at or above min_severity (low|medium|high|critical),
    with the sections IBM Bob applied and why."""
    order = ["low", "medium", "high", "critical"]
    floor = order.index(min_severity) if min_severity in order else 2
    r = _result()
    rows = []
    for pid, v in r["violations"].items():
        if v["violation"] and order.index(v["severity"]) >= floor:
            rows.append({"post_id": pid, "severity": v["severity"], "categories": v["categories"],
                         "target": v["target"], "evidence_quote": v["evidence_quote"],
                         "sections": [{"act": s["act"], "section": s["section"], "title": s["title"],
                                       "explanation": s["explanation"]} for s in v["sections"]],
                         "in_campaign": pid in r["in_campaign"]})
    return rows


@mcp.tool()
def render_threat_brief(campaign_id: str, analyst: str, analyst_assessment: str = "") -> dict:
    """Render the HTML threat brief. Pass Bob's cited assessment (<=150 words) as analyst_assessment."""
    c = _find(campaign_id)
    if c is None:
        return {"error": f"Unknown campaign {campaign_id!r}. Call list_campaigns first."}
    brief_id, _html, path = render_brief(c, analyst, analyst_assessment or None)
    return {"brief_id": brief_id, "path": str(path.resolve()), "state": c["state"],
            "assessment_source": "IBM Bob" if analyst_assessment.strip() else "ThreatLens deterministic fallback"}


if __name__ == "__main__":
    mcp.run()
