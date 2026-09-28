"""M5: Threat correlation & campaign evolution (PLAN.md section 10).

Turns each M2 cluster (+ M3 label, + M4 legal) into schema-4.7 campaign
intelligence: narrative phases, propagation, timeline, what changed since the
previous snapshot, online-offline correlation, the campaign state with its
explicit triggers T1-T5, the action ladder and an evidence index.

Everything here is a plain, written rule over the posts and IBM Bob's post-level analysis
(categories, place, time). Bob also writes the optional 2-sentence narrative summary (cached, with
a template fallback). Every finding carries ``evidence_post_ids`` pointing at real posts.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from threatlens import bob_client
from threatlens.classify import (
    HOSTILE, INTIMIDATE, SHARE, TIME_RE, find_places, find_time_phrase, is_mobilization, lex_hit,
)
from threatlens.coordination import _densest_window_pids
from threatlens.schema import post_sha256

IST = timezone(timedelta(hours=5, minutes=30))
STATES = ["DETECTED", "COORDINATED", "AMPLIFYING", "ESCALATING", "MOBILIZATION"]
STATE_RANK = {s: i for i, s in enumerate(STATES)}
PHASES = ["CLAIM", "AMPLIFICATION", "INFLAMMATORY", "MOBILIZATION"]
BUCKET = timedelta(minutes=10)

_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5,
             "sunday": 6, "सोमवार": 0, "मंगलवार": 1, "बुधवार": 2, "गुरुवार": 3, "शुक्रवार": 4,
             "शनिवार": 5, "रविवार": 6}
_GENERIC_PLACE_WORDS = {"market", "station", "chowk", "bazaar", "gate", "maidan", "office", "bus",
                        "stand", "chauraha", "ground", "central", "highway", "road", "the"}


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.isoformat()


def _to_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=IST)
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(IST).strftime("%a %d %b %H:%M IST")


# ===========================================================================
# 10.1 Narrative phase per post
# ===========================================================================

_HOSTILE_CATS = {"incitement_violence", "criminal_intimidation", "religious_insult"}


def tag_phase(text: str, repost_of: str | None, copies_earlier_post: bool, categories=()) -> str:
    """First match wins: MOBILIZATION > INFLAMMATORY > AMPLIFICATION > CLAIM.

    ``categories`` are Bob's violation categories for the post; the lexicons are the fallback.
    """
    if "unlawful_assembly_call" in categories or is_mobilization(text):
        return "MOBILIZATION"
    if set(categories) & _HOSTILE_CATS or lex_hit(text, HOSTILE):
        return "INFLAMMATORY"
    if repost_of or lex_hit(text, SHARE) or copies_earlier_post:
        return "AMPLIFICATION"
    return "CLAIM"


def _copies(cdf: pd.DataFrame, near_dup_groups: list[list[str]]) -> set[str]:
    """Posts that are near-duplicates of an EARLIER post (the first post of a group is the original)."""
    order = {pid: i for i, pid in enumerate(cdf.sort_values("timestamp")["post_id"])}
    copies = set()
    for grp in near_dup_groups:
        members = sorted((p for p in grp if p in order), key=order.get)
        copies.update(members[1:])
    return copies


def phase_by_post(cdf: pd.DataFrame, near_dup_groups: list[list[str]],
                  violations: dict | None = None) -> dict[str, str]:
    copies = _copies(cdf, near_dup_groups)
    v = violations or {}
    return {r.post_id: tag_phase(r.text, r.repost_of, r.post_id in copies,
                                 (v.get(r.post_id) or {}).get("categories", ()))
            for r in cdf.sort_values("timestamp").itertuples()}


def post_place_time(pid: str, text: str, violations: dict | None) -> tuple[str | None, str | None]:
    """Place and time named in a post: Bob's reading first, then the regex helpers."""
    v = (violations or {}).get(pid) or {}
    place = v.get("location") or (find_places(text) or [None])[0]
    when = v.get("time") or (find_time_phrase(text) if TIME_RE.search(text or "") else None)
    return place, when


def build_narrative(cdf: pd.DataFrame, phases: dict[str, str]) -> dict:
    """Phases in first-seen order with counts, an example quote and up to 5 evidence ids."""
    recs: dict[str, dict] = {}
    for r in cdf.sort_values("timestamp").itertuples():
        ph = phases[r.post_id]
        rec = recs.setdefault(ph, {"phase": ph, "first_seen": _iso(r.timestamp), "post_count": 0,
                                   "example_quote": r.text_masked[:160], "evidence_post_ids": []})
        rec["post_count"] += 1
        if len(rec["evidence_post_ids"]) < 5:
            rec["evidence_post_ids"].append(r.post_id)
    ordered = list(recs.values())
    return {"phases": ordered, "path": " → ".join(p["phase"] for p in ordered),
            "summary": "", "summary_source": "rules"}


def _summary(narr: dict, cluster: dict, classification: dict, state: str, planned: dict | None,
             main_tag: str, mode: str) -> tuple[str, str]:
    n_acc, n_posts = len(cluster["account_ids"]), len(cluster["post_ids"])
    start, end = _to_dt(cluster["start"]).strftime("%H:%M"), _to_dt(cluster["end"]).strftime("%H:%M")
    label = classification.get("label", "benign")
    first = f"{n_acc} accounts posted {n_posts} times under {main_tag} between {start} and {end} IST, " \
            f"moving {narr['path']}."
    if planned:
        second = f"The latest posts call people to {planned['place']} at {_fmt(_to_dt(planned['time']))}."
    elif label == "benign":
        second = "The content is organic celebration with no hostile or mobilizing language."
    elif classification.get("target"):
        second = f"It is labelled {label} and targets {classification['target']}; current state {state}."
    else:
        second = f"It is labelled {label}; current state {state}."
    fallback = f"{first} {second}"
    examples = "\n".join(f"- {p['phase']} ({p['post_count']} posts): {p['example_quote']}" for p in narr["phases"])
    prompt = ("Write exactly 2 plain sentences for a police analyst summarising this fictional social-media "
              "campaign. Only use the facts below; do not add new facts, names or places.\n"
              f"Hashtag: {main_tag}. Accounts: {n_acc}. Posts: {n_posts}. Window: {start}-{end} IST. "
              f"Label: {label}. State: {state}. Narrative path: {narr['path']}.\n"
              f"Planned event: {planned['place'] + ' at ' + _fmt(_to_dt(planned['time'])) if planned else 'none'}.\n"
              f"Phase examples:\n{examples}\nSummary:")
    if mode == "rules":
        return fallback, "rules"
    key = bob_client.cache_key("narrative-v1", [sorted(cluster["post_ids"]), state, narr["path"]])
    hit = bob_client.cache_get(key) if mode == "auto" else None
    if hit:
        return hit, "cache"
    try:
        text, _ = bob_client.run(prompt + "\nReply with the 2 sentences only.", max_turns=2)
        text = text.strip().strip('"')
        if not text:
            raise RuntimeError("empty reply")
        bob_client.cache_put(key, text)
        return text, "bob"
    except Exception:
        return fallback, "rules"


# ===========================================================================
# 10.2 Propagation
# ===========================================================================

def build_propagation(cdf: pd.DataFrame, cluster: dict, copies: set[str], full_df: pd.DataFrame) -> dict:
    cdf = cdf.sort_values("timestamp")
    start = cdf["timestamp"].iloc[0]
    t = start.replace(minute=start.minute - start.minute % 10, second=0, microsecond=0)
    buckets, seen_acc, seen = [], set(), {"hashtags": set(), "urls": set(), "media": set()}
    cum_posts = 0
    while t <= cdf["timestamp"].iloc[-1]:
        b = cdf[(cdf["timestamp"] >= t) & (cdf["timestamp"] < t + BUCKET)]
        new_acc = set(b["account_id"]) - seen_acc
        seen_acc |= new_acc
        cum_posts += len(b)
        new = {}
        for field in ("hashtags", "urls", "media"):
            items = list(dict.fromkeys(x for xs in b[field] for x in xs if x not in seen[field]))
            seen[field].update(items)
            new[field] = items
        buckets.append({"start": _iso(t), "posts": len(b), "new_accounts": len(new_acc),
                        "cum_accounts": len(seen_acc), "cum_posts": cum_posts,
                        "new_hashtags": new["hashtags"], "new_urls": new["urls"], "new_media": new["media"],
                        "reposts": int(b["repost_of"].notna().sum()),
                        "copies": int(b["post_id"].isin(copies).sum()),
                        "post_ids": b["post_id"].tolist()})
        t += BUCKET

    by_pid = full_df.set_index("post_id")
    first_posters = []
    for acc in cluster.get("first_posters", []) or cdf["account_id"].drop_duplicates().head(3).tolist():
        rows = cdf[cdf["account_id"] == acc]
        if not rows.empty:
            r = rows.iloc[0]
            first_posters.append({"account_id": acc, "handle": r["handle"], "first_post_id": r["post_id"],
                                  "t": _iso(r["timestamp"])})

    # Amplifiers: accounts whose posts were reposted or copied the most.
    reposts_received: Counter = Counter()
    copies_of_text: Counter = Counter()
    originals: dict[str, list[str]] = {}
    for r in cdf.itertuples():
        if r.repost_of and r.repost_of in by_pid.index:
            author = by_pid.loc[r.repost_of, "account_id"]
            reposts_received[author] += 1
            originals.setdefault(author, []).append(r.repost_of)
    order = {pid: i for i, pid in enumerate(cdf["post_id"])}
    for grp in cluster.get("near_dup_groups", []):
        members = sorted((p for p in grp if p in order), key=order.get)
        if len(members) > 1:
            author = by_pid.loc[members[0], "account_id"]
            copies_of_text[author] += len(members) - 1
            originals.setdefault(author, []).append(members[0])
    total = reposts_received + copies_of_text
    amplifiers = []
    for acc, _ in total.most_common(5):
        r = cdf[cdf["account_id"] == acc].iloc[0]
        amplifiers.append({"account_id": acc, "handle": r["handle"],
                           "reposts_received": reposts_received[acc], "copies_of_their_text": copies_of_text[acc],
                           "followers": int(r["followers"]),
                           "evidence_post_ids": list(dict.fromkeys(originals[acc]))[:5]})
    peak = max(buckets, key=lambda b: b["posts"])
    return {"buckets": buckets, "peak_bucket": peak["start"], "first_posters": first_posters,
            "amplifiers": amplifiers,
            "potential_reach": int(cdf.drop_duplicates("account_id")["followers"].sum())}


def burst_bucket(buckets: list[dict]) -> dict | None:
    """First bucket with >= 2x the previous bucket's posts and >= 8 posts (T3 / 10.3)."""
    prev = 0
    for b in buckets:
        if b["posts"] >= 8 and b["posts"] >= 2 * prev:
            return b
        prev = b["posts"]
    return None


# ===========================================================================
# 10.5 Online-offline correlation
# ===========================================================================

_HOUR_RE = re.compile(r"(\d{1,2})\s?(baje|pm|am|बजे)", re.IGNORECASE)
_PERIOD_HOUR_RE = re.compile(r"(raat|shaam|subah)\s+(\d{1,2})\b", re.IGNORECASE)
_PM_WORDS = re.compile(r"shaam|sham|raat|evening|night|शाम|रात", re.IGNORECASE)
_AM_WORDS = re.compile(r"subah|morning|सुबह", re.IGNORECASE)


def _hour(text: str) -> int | None:
    m = _HOUR_RE.search(text)
    if m:
        h, suffix = int(m.group(1)), m.group(2).lower()
    else:
        m = _PERIOD_HOUR_RE.search(text)
        if not m:
            return None
        h, suffix = int(m.group(2)), m.group(1).lower()
    if h > 23:
        return None
    if suffix == "am" or _AM_WORDS.search(text) and suffix != "pm":
        return h % 12
    if suffix == "pm" or _PM_WORDS.search(text):
        return h % 12 + 12
    return h + 12 if h <= 6 else h  # bare "5 baje" means evening in everyday use


def parse_mentioned_time(text: str, ref_dt: datetime) -> datetime | None:
    """Turn a time mention into an absolute IST datetime (PLAN 10.5).

    weekday -> next occurrence on/after the post date; "N baje" + shaam/raat -> PM;
    "aaj raat" -> 21:00 same day; "kal" -> next day; abhi/turant -> the post time.
    An explicit clock time wins over abhi ("abhi ... raat 8 baje se pehle" -> 20:00).
    """
    ref_dt = _to_dt(ref_dt).astimezone(IST)
    t = (text or "").lower()
    hour = _hour(t)
    day = ref_dt.date()
    weekday = next((d for name, d in _WEEKDAYS.items()
                    if re.search(r"(?<![\wऀ-ॿ])" + name + r"(?![\wऀ-ॿ])", t)), None)
    if weekday is not None:
        day = day + timedelta(days=(weekday - day.weekday()) % 7)
    elif re.search(r"\bkal\b", t):
        day = day + timedelta(days=1)
    if hour is not None:
        return datetime(day.year, day.month, day.day, hour, 0, tzinfo=IST)
    if "aaj raat" in t:
        return datetime(day.year, day.month, day.day, 21, 0, tzinfo=IST)
    if weekday is not None or re.search(r"\bkal\b", t):
        return datetime(day.year, day.month, day.day, ref_dt.hour, ref_dt.minute, tzinfo=IST)
    if re.search(r"\b(abhi|turant)\b", t):
        return ref_dt
    return None


def _tokens(place: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", place.lower()) if w not in _GENERIC_PLACE_WORDS and len(w) > 2}


def build_offline(cdf: pd.DataFrame, classification: dict, phases: dict[str, str],
                  incidents: list[dict], snapshot_dt: datetime, violations: dict | None = None) -> dict:
    cdf = cdf.sort_values("timestamp")
    first, last = cdf["timestamp"].iloc[0], cdf["timestamp"].iloc[-1]
    place_posts: dict[str, list[str]] = {}
    for r in cdf.itertuples():
        places = find_places(r.text)
        loc = ((violations or {}).get(r.post_id) or {}).get("location")
        if loc and loc not in places:
            places.append(loc)
        for p in places:
            place_posts.setdefault(p, []).append(r.post_id)
    loc = classification.get("location_mentioned")
    if loc and loc not in place_posts:
        ids = cdf[cdf["text"].str.contains(re.escape(loc), case=False)]["post_id"].tolist()
        if ids:
            place_posts[loc] = ids

    benign = classification.get("label") == "benign"
    matches = []
    for inc in incidents:
        when = _to_dt(inc["reported_at"])
        evidence, kind = [], None
        if first - timedelta(hours=3) <= when <= last + timedelta(hours=6):
            for place, ids in place_posts.items():
                if _tokens(place) & _tokens(inc["location"]):
                    evidence, kind = ids, "location+time"
                    break
        if not kind and first - timedelta(hours=6) <= when <= last + timedelta(hours=6):
            district_re = re.compile(r"\b" + re.escape(inc["district"]) + r"\b", re.IGNORECASE)
            ids = [r.post_id for r in cdf.itertuples() if district_re.search(r.text)]
            if ids:
                evidence, kind = ids, "location"
        if not kind:
            continue
        delta = int((when - first).total_seconds() // 60)
        note = ("campaign references or distorts a real incident" if delta < 0
                else "possible offline outcome of the campaign")
        if benign:
            note += " (benign campaign: reported only, never escalates the state)"
        matches.append({"incident_id": inc["incident_id"], "confidence": "HIGH" if kind == "location+time" else "MEDIUM",
                        "match": kind, "time_delta_min": delta, "note": note,
                        "incident": f"{inc['location']}, {inc['district']} — {inc['category']} at "
                                    f"{when.strftime('%H:%M')}: {inc['description']}",
                        "reported_at": _iso(when), "evidence_post_ids": evidence[:5]})

    # Planned event: the latest parsed time + place among MOBILIZATION posts.
    planned, candidates = None, []
    for r in cdf.itertuples():
        if phases.get(r.post_id) != "MOBILIZATION":
            continue
        place, phrase = post_place_time(r.post_id, r.text, violations)
        when = (parse_mentioned_time(phrase, r.timestamp) if phrase else None) or \
            parse_mentioned_time(r.text, r.timestamp)
        if place and when and when >= r.timestamp - timedelta(minutes=1):
            candidates.append((when, place, r.post_id))
    if candidates:
        when, place, _ = max(candidates, key=lambda c: c[0])
        ids = [pid for w, p, pid in candidates if w == when and p == place]
        planned = {"place": place, "time": _iso(when),
                   "hours_from_snapshot": round((when - snapshot_dt).total_seconds() / 3600, 1),
                   "time_phrase": post_place_time(ids[0], cdf.set_index("post_id").loc[ids[0], "text"],
                                                  violations)[1],
                   "evidence_post_ids": ids[:5]}
    return {"matches": matches, "planned_event": planned}


# ===========================================================================
# 10.6 Campaign state: explicit triggers
# ===========================================================================

def build_triggers(cdf: pd.DataFrame, cluster: dict, classification: dict, phases: dict[str, str],
                   copies: set[str], buckets: list[dict], violations: dict | None = None) -> list[dict]:
    cdf = cdf.sort_values("timestamp").reset_index(drop=True)
    label = classification.get("label", "benign")
    not_benign = label != "benign"
    ts = dict(zip(cdf["post_id"], cdf["timestamp"]))
    triggers = []

    def add(tid, state, condition, threshold, observed, fired, fired_at, evidence):
        triggers.append({"id": tid, "state": state, "condition": condition, "threshold": threshold,
                         "observed": observed, "fired": bool(fired), "fired_at": _iso(fired_at) if fired else None,
                         "evidence_post_ids": list(dict.fromkeys(evidence))[:5] or cdf["post_id"].head(1).tolist()})

    n_acc = cdf["account_id"].nunique()
    add("T1", "DETECTED", "M2 cluster with at least 5 accounts", "≥ 5 accounts", f"{n_acc} accounts",
        n_acc >= 5, cdf["timestamp"].iloc[min(4, len(cdf) - 1)], cdf["post_id"].head(5).tolist())

    score, signals = cluster.get("coordination_score", 0), cluster.get("signals", {})
    strong = [k for k, v in signals.items() if v >= 0.5]
    biggest = max(cluster.get("near_dup_groups", []) or [[]], key=len)
    add("T2", "COORDINATED", "coordination score ≥ 60 AND at least 2 signals ≥ 0.5",
        "score ≥ 60, ≥ 2 strong signals", f"score {score}, strong signals: {', '.join(strong) or 'none'}",
        score >= 60 and len(strong) >= 2, cluster.get("detected_at"), biggest or cdf["post_id"].head(5).tolist())

    amplified = [p for p in cdf["post_id"] if p in copies or cdf.loc[cdf["post_id"] == p, "repost_of"].iloc[0]]
    ratio = len(amplified) / len(cdf)
    burst = burst_bucket(buckets)
    add("T3", "AMPLIFYING", "(reposts + near-copies) ≥ 30% of posts AND a 10-min bucket with ≥ 2× the previous "
        "bucket's posts and ≥ 8 posts", "≥ 30% amplified + burst bucket",
        f"{ratio:.0%} amplified ({len(amplified)}/{len(cdf)}); burst: "
        + (f"{burst['posts']} posts at {_to_dt(burst['start']).strftime('%H:%M')}" if burst else "none"),
        ratio >= 0.3 and burst is not None, burst["start"] if burst else None,
        [p for p in (burst or {}).get("post_ids", []) if p in amplified] or amplified)

    inflammatory = [p for p, ph in phases.items() if ph == "INFLAMMATORY"]
    inflammatory.sort(key=ts.get)
    intim_posts = [r.post_id for r in cdf.itertuples() if lex_hit(r.text, INTIMIDATE)]
    intimidation = bool(classification.get("intimidation"))
    if intimidation:
        ev = intim_posts or [classification.get("evidence_post_id")]
        at = ts.get(ev[0])
    else:
        ev = inflammatory[:3]
        at = ts[inflammatory[2]] if len(inflammatory) >= 3 else None
    add("T4", "ESCALATING", "label ≠ benign AND (≥ 3 INFLAMMATORY posts OR intimidation = true)",
        "≥ 3 inflammatory posts or intimidation", f"label {label}, {len(inflammatory)} inflammatory posts, "
        f"intimidation={intimidation}", not_benign and (len(inflammatory) >= 3 or intimidation), at,
        ev or inflammatory)

    mob_first: dict[str, str] = {}
    for r in cdf.itertuples():
        if r.account_id not in mob_first and phases.get(r.post_id) == "MOBILIZATION" \
                and all(post_place_time(r.post_id, r.text, violations)):
            mob_first[r.account_id] = r.post_id
    mob_ids = list(mob_first.values())
    add("T5", "MOBILIZATION", "label ≠ benign AND ≥ 3 distinct accounts post MOBILIZATION content naming a "
        "place and a time", "≥ 3 accounts", f"{len(mob_ids)} accounts",
        not_benign and len(mob_ids) >= 3, ts[mob_ids[2]] if len(mob_ids) >= 3 else None, mob_ids)

    for t in triggers:  # benign campaigns are capped at COORDINATED
        t["counts_toward_state"] = t["fired"] and (not_benign or STATE_RANK[t["state"]] <= 1)
    return triggers


def state_from_triggers(triggers: list[dict]) -> tuple[str, list[dict]]:
    """State = highest counted trigger; history in fired_at order."""
    counted = sorted((t for t in triggers if t["counts_toward_state"]), key=lambda t: STATE_RANK[t["state"]])
    state = counted[-1]["state"] if counted else "DETECTED"
    history, entered = [], None
    for t in counted:  # the ladder only climbs: a state is entered no earlier than the one below it
        at = t["fired_at"]
        entered = at if entered is None or (at and at > entered) else entered
        history.append({"state": t["state"], "entered_at": entered, "trigger_id": t["id"]})
    return state, history


# ===========================================================================
# 10.3 Timeline
# ===========================================================================

def build_timeline(cdf: pd.DataFrame, narrative: dict, propagation: dict, offline: dict,
                   triggers: list[dict], history: list[dict]) -> list[dict]:
    cdf = cdf.sort_values("timestamp")
    first = cdf.iloc[0]
    events = [{"t": _iso(first["timestamp"]), "type": "FIRST_POST",
               "description": f"First post by @{first['handle']}: \"{first['text_masked'][:90]}\"",
               "evidence_post_ids": [first["post_id"]]}]
    window = _densest_window_pids(cdf, minutes=10)
    wdf = cdf[cdf["post_id"].isin(window)]
    if len(wdf) >= 3:
        events.append({"t": _iso(wdf["timestamp"].min()), "type": "COORDINATION_BURST",
                       "description": f"Densest 10 minutes: {len(wdf)} posts from {wdf['account_id'].nunique()} accounts",
                       "evidence_post_ids": wdf["post_id"].head(5).tolist()})
    burst = burst_bucket(propagation["buckets"])
    if burst:
        events.append({"t": burst["start"], "type": "AMPLIFICATION",
                       "description": f"Posting jumps to {burst['posts']} posts in 10 minutes "
                                      f"({burst['new_accounts']} new accounts)",
                       "evidence_post_ids": burst["post_ids"][:5]})
    for ph in narrative["phases"][1:]:
        events.append({"t": ph["first_seen"], "type": "NARRATIVE_SHIFT",
                       "description": f"Narrative shifts to {ph['phase']}: \"{ph['example_quote'][:90]}\"",
                       "evidence_post_ids": ph["evidence_post_ids"][:3]})
    mob = next((p for p in narrative["phases"] if p["phase"] == "MOBILIZATION"), None)
    if mob:
        events.append({"t": mob["first_seen"], "type": "MOBILIZATION_SIGNAL",
                       "description": f"First call to gather: \"{mob['example_quote'][:90]}\"",
                       "evidence_post_ids": mob["evidence_post_ids"][:1]})
    for m in offline["matches"]:
        events.append({"t": m["reported_at"], "type": "OFFLINE_MATCH",
                       "description": f"{m['incident_id']} ({m['confidence']}): {m['incident'][:110]}",
                       "evidence_post_ids": m["evidence_post_ids"][:3]})
    by_id = {t["id"]: t for t in triggers}
    for h in history:
        t = by_id[h["trigger_id"]]
        events.append({"t": h["entered_at"], "type": "STATE_CHANGE",
                       "description": f"State → {h['state']} ({h['trigger_id']}: {t['observed']})",
                       "evidence_post_ids": t["evidence_post_ids"][:3]})
    return sorted(events, key=lambda e: e["t"])


# ===========================================================================
# 10.4 What changed
# ===========================================================================

def build_what_changed(cur: dict, cdf: pd.DataFrame, previous: list[dict] | None) -> dict:
    out = {"previous_cutoff": None, "matched_previous": None, "is_new_campaign": previous is not None,
           "items": []}
    if previous is None:
        out["is_new_campaign"] = False  # no previous snapshot to compare against
        return out
    out["previous_cutoff"] = previous[0]["_snapshot_time"] if previous else None
    accounts = set(cur["_cluster"]["account_ids"])
    best, best_j = None, 0.0
    for prev in previous:
        pacc = set(prev["_cluster"]["account_ids"])
        j = len(accounts & pacc) / len(accounts | pacc)
        if j > best_j:
            best, best_j = prev, j
    if best is None or best_j < 0.3:
        return out
    out.update(matched_previous=best["campaign_id"], is_new_campaign=False,
               previous_cutoff=best["_snapshot_time"])
    items = out["items"]
    cdf = cdf.sort_values("timestamp")
    prev_posts = set(best["_cluster"]["post_ids"])
    new_rows = cdf[~cdf["post_id"].isin(prev_posts)]

    new_acc = accounts - set(best["_cluster"]["account_ids"])
    if new_acc:
        firsts = new_rows[new_rows["account_id"].isin(new_acc)].drop_duplicates("account_id")
        items.append({"kind": "new_accounts", "detail": f"{len(new_acc)} new accounts joined "
                      f"({len(best['_cluster']['account_ids'])} → {len(accounts)})",
                      "evidence_post_ids": firsts["post_id"].tolist()[:10]})
    if len(new_rows):
        items.append({"kind": "new_posts", "detail": f"{len(new_rows)} new posts "
                      f"({len(prev_posts)} → {len(cdf)})", "evidence_post_ids": new_rows["post_id"].tail(5).tolist()})
    for field, kind in (("hashtags", "new_hashtags"), ("urls", "new_urls"), ("media", "new_media")):
        old = set(best["_cluster"].get(field, []))
        new = [x for x in dict.fromkeys(x for xs in new_rows[field] for x in xs) if x not in old]
        if new:
            ev = [r.post_id for r in new_rows.itertuples() if set(getattr(r, field)) & set(new)]
            items.append({"kind": kind, "detail": ", ".join(new), "evidence_post_ids": ev[:5]})
    old_places = set(best["_places"])
    new_places = [p for p in cur["_places"] if p not in old_places]
    if new_places:
        ev = [r.post_id for r in new_rows.itertuples() if set(find_places(r.text)) & set(new_places)]
        items.append({"kind": "new_locations", "detail": "Now names " + ", ".join(new_places),
                      "evidence_post_ids": ev[:5]})
    cls = cur["_classification"]
    if best["label"] != cur["label"]:
        items.append({"kind": "label_change", "detail": f"{best['label']} → {cur['label']}",
                      "evidence_post_ids": [cls["evidence_post_id"]]})
    fired_before = {t["id"] for t in best["triggers"] if t["counts_toward_state"]}
    newly = [t for t in cur["triggers"] if t["counts_toward_state"] and t["id"] not in fired_before]
    if best["state"] != cur["state"]:
        top = next(t for t in cur["triggers"] if t["state"] == cur["state"])
        items.append({"kind": "state_change", "detail": f"{best['state']} → {cur['state']}",
                      "evidence_post_ids": top["evidence_post_ids"]})
    if newly:
        items.append({"kind": "new_signals", "detail": "Newly fired: " + ", ".join(
            f"{t['id']} {t['state']} ({t['observed']})" for t in newly),
            "evidence_post_ids": list(dict.fromkeys(p for t in newly for p in t["evidence_post_ids"]))[:5]})
    return out


# ===========================================================================
# 10.7 Action ladder
# ===========================================================================

_LADDER = {
    "DETECTED": ["Keep monitoring the hashtags and accounts of this cluster."],
    "COORDINATED": ["Alert the district cyber cell.",
                    "Send a data-preservation request to the platform for the evidence posts."],
    "AMPLIFYING": ["Send a takedown notice to the intermediary under IT Act §79(3)(b).",
                   "Publish a fact-check / counter-message from official police handles."],
    "ESCALATING": ["Request blocking under IT Act §69A through the designated officer.",
                   "Brief the district SP.",
                   "Consider an FIR under the suggested sections after legal review."],
    "MOBILIZATION": ["Deploy police at {place} before {time}.",
                     "For the district magistrate's consideration: a prohibitory order under BNSS §163 "
                     "(formerly CrPC §144).",
                     "Coordinate with the district administration."],
}


def build_actions(state: str, triggers: list[dict], planned: dict | None, classification: dict) -> list[dict]:
    by_state = {t["state"]: t for t in triggers}
    current = by_state[state]
    actions = []
    for s in STATES[: STATE_RANK[state] + 1]:
        t = by_state[s] if by_state[s]["counts_toward_state"] else current
        for step in _LADDER[s]:
            if "{place}" in step:
                place = (planned or {}).get("place") or classification.get("location_mentioned") or "the named place"
                if planned and planned["hours_from_snapshot"] < 0:
                    step = (f"Check {place} now: the called time {_fmt(_to_dt(planned['time']))} has passed; "
                            "keep police presence until the crowd disperses.")
                else:
                    when = _fmt(_to_dt(planned["time"])) if planned else (classification.get("time_mentioned")
                                                                          or "the called time")
                    step = step.format(place=place, time=when)
            ev = (planned or {}).get("evidence_post_ids") if s == "MOBILIZATION" and planned else None
            actions.append({"state": s, "step": step, "because": t["id"],
                            "evidence_post_ids": ev or t["evidence_post_ids"]})
    return actions


# ===========================================================================
# 10.8 Evidence index
# ===========================================================================

def collect_cited(obj: Any, out: set[str] | None = None) -> set[str]:
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("_"):
                continue
            if k == "evidence_post_ids" and isinstance(v, list):
                out.update(v)
            else:
                collect_cited(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_cited(v, out)
    return out


def build_evidence_index(post_ids: set[str], df: pd.DataFrame) -> dict:
    rows = df[df["post_id"].isin(post_ids)].sort_values("timestamp")
    return {r["post_id"]: {"handle": r["handle"], "timestamp": _iso(r["timestamp"]),
                           "text_masked": r["text_masked"], "sha256": post_sha256(r)}
            for _, r in rows.iterrows()}


# ===========================================================================
# Public API
# ===========================================================================

def build_campaign_intel(df: pd.DataFrame, clusters: list[dict], classifications: list[dict],
                         legal: list[list[dict]], incidents: list[dict], snapshot_time: Any,
                         previous: list[dict] | None = None, llm_mode: str = "auto",
                         violations: dict | None = None) -> list[dict]:
    """One schema-4.7 record per cluster, ids CMP-1, CMP-2... in cluster order.

    Keys starting with "_" are internal (used by what-changed, the UI and the MCP
    server) and are not part of the schema.
    """
    snapshot_dt = _to_dt(snapshot_time)
    campaigns = []
    for i, (cluster, cls) in enumerate(zip(clusters, classifications)):
        cdf = df[df["post_id"].isin(cluster["post_ids"])].sort_values("timestamp")
        if cdf.empty:
            continue
        dups = cluster.get("near_dup_groups", [])
        copies = _copies(cdf, dups)
        phases = phase_by_post(cdf, dups, violations)
        narrative = build_narrative(cdf, phases)
        propagation = build_propagation(cdf, cluster, copies, df)
        triggers = build_triggers(cdf, cluster, cls, phases, copies, propagation["buckets"], violations)
        state, history = state_from_triggers(triggers)
        offline = build_offline(cdf, cls, phases, incidents, snapshot_dt, violations)
        timeline = build_timeline(cdf, narrative, propagation, offline, triggers, history)
        main_tag = Counter(h for hs in cdf["hashtags"] for h in hs).most_common(1)
        main_tag = main_tag[0][0] if main_tag else cluster["cluster_id"]
        narrative["summary"], narrative["summary_source"] = _summary(
            narrative, cluster, cls, state, offline["planned_event"], main_tag, llm_mode)
        section_legal = legal[i] if i < len(legal) else []

        campaign = {
            "campaign_id": f"CMP-{i + 1}", "cluster_id": cluster["cluster_id"], "label": cls.get("label", "benign"),
            "state": state, "state_history": history, "triggers": triggers, "timeline": timeline,
            "propagation": propagation, "narrative": narrative, "what_changed": {}, "offline": offline,
            "actions": build_actions(state, triggers, offline["planned_event"], cls), "legal": section_legal,
            "evidence_index": {},
            # internal helpers (not schema)
            "_cluster": cluster, "_classification": cls, "_main_hashtag": main_tag,
            "_snapshot_time": _iso(snapshot_dt), "_phase_by_post": phases,
            "_places": list(dict.fromkeys(p for t in cdf["text"] for p in find_places(t))),
        }
        campaign["what_changed"] = build_what_changed(campaign, cdf, previous)
        cited = collect_cited(campaign)
        if cls.get("evidence_post_id"):
            cited.add(cls["evidence_post_id"])
        campaign["evidence_index"] = build_evidence_index(cited, df)
        campaigns.append(campaign)
    return campaigns


if __name__ == "__main__":
    import sys

    from threatlens.pipeline import analyze, load_sample

    sys.stdout.reconfigure(encoding="utf-8")
    df, incidents = load_sample()
    result = analyze(df, incidents, llm_mode="rules")
    for c in result["campaigns"]:
        print(f"{c['campaign_id']} {c['_main_hashtag']:<18} {c['label']:<14} {c['state']:<13} {c['narrative']['path']}")
        print("   fired:", ", ".join(t["id"] for t in c["triggers"] if t["fired"]),
              "| offline:", [(m["incident_id"], m["confidence"], m["time_delta_min"]) for m in c["offline"]["matches"]],
              "| planned:", c["offline"]["planned_event"] and
              (c["offline"]["planned_event"]["place"], c["offline"]["planned_event"]["time"]))
