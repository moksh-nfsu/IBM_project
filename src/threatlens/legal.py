"""M4: Legal mapping for a campaign (BNS 2023 + IT Act 2000).

Post-level citations come from IBM Bob (violations.py): each post that violates the law carries
the sections it attracts and an explanation of how its words meet each section. For a campaign,
those citations are aggregated: each section keeps the number of posts, the strongest explanation
and the evidence posts.

Two sections depend on the campaign's structure rather than any single post, so they are added
by written rules:
  BNS 61  criminal conspiracy       non-benign AND coordination score >= 60 (M2 evidence of agreement)
  BNS 57  abetment by >10 persons   a call to act (mobilisation) spread by more than 10 accounts
Every item shows "Suggested — requires legal officer review". Section titles and page numbers come
from the official Gazette text (law/law_kb.json).
"""
from __future__ import annotations

from collections import Counter

import pandas as pd

from threatlens.law import section

DISCLAIMER = "Suggested — requires legal officer review"
_SEV = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _item(act: str, sec: str, reason: str, evidence: list[str], posts: int, source: str) -> dict:
    r = section(act, sec)
    return {"id": f"{act} {sec}", "act": act, "section": sec, "old_section": "",
            "offence": r["title"] if r else "", "reason": reason, "evidence_post_ids": evidence[:5],
            "posts": posts, "page": r["page"] if r else None, "statute_excerpt": (r["text"][:400] if r else ""),
            "basis": source, "disclaimer": DISCLAIMER}


def map_sections(cluster: dict, classification: dict, df: pd.DataFrame | None = None,
                 violations: dict[str, dict] | None = None) -> list[dict]:
    """Suggested sections for one campaign (benign -> [])."""
    if classification.get("label") == "benign":
        return []
    violations = violations or {}
    order = cluster["post_ids"]
    if df is not None:
        order = df[df["post_id"].isin(cluster["post_ids"])].sort_values("timestamp")["post_id"].tolist()
    hits: dict[tuple[str, str], list[tuple[str, dict, dict]]] = {}
    for pid in order:
        v = violations.get(pid)
        if not v or not v["violation"]:
            continue
        for s in v["sections"]:
            hits.setdefault((s["act"], s["section"]), []).append((pid, s, v))

    out = []
    for (act, sec), rows in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        best = max(rows, key=lambda x: (_SEV.get(x[2]["severity"], 0), len(x[1]["explanation"])))
        pid, s, v = best
        src = Counter(r[2]["source"] for r in rows).most_common(1)[0][0]
        reason = f"{len(rows)} post{'s' if len(rows) > 1 else ''} in this campaign. {s['explanation']} [{pid}]"
        out.append(_item(act, sec, reason, [p for p, _, _ in rows], len(rows), "IBM Bob" if src in ("bob", "cache")
                         else "rules fallback"))

    n_accounts = len(cluster.get("account_ids", []))
    score = cluster.get("coordination_score", 0)
    if score >= 60 and not any(i["section"] == "61" for i in out):
        dup = max(cluster.get("near_dup_groups", []) or [[]], key=len)
        out.append(_item("BNS", "61", f"Coordination score {score}/100: {n_accounts} accounts posted near-identical "
                         f"text ({len(dup)} copies) in a short window, which indicates an agreement to act "
                         "together (an ingredient of criminal conspiracy). Needs corroboration.",
                         dup or order, len(dup), "coordination rule"))
    mob = [p for p in order if "unlawful_assembly_call" in (violations.get(p) or {}).get("categories", [])]
    if mob and n_accounts > 10 and not any(i["section"] == "57" for i in out):
        out.append(_item("BNS", "57", f"The call to gather was pushed to the public by a group of {n_accounts} "
                         f"accounts ({len(mob)} posts), i.e. abetment by more than ten persons.",
                         mob, len(mob), "coordination rule"))
    return out
