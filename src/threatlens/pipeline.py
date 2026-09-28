"""Pipeline (PLAN.md section 12).

1. Post-level analysis (IBM Bob, once per post up to the current cutoff): violations + BNS / IT Act.
2. For each snapshot: M2 coordination -> M3 campaign label (from the post analysis) -> M4 legal.
3. M5 for the previous snapshot, then for the current one compared with it.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from threatlens.classify import classify_cluster
from threatlens.coordination import build_clusters
from threatlens.correlation import STATE_RANK, build_campaign_intel
from threatlens.ingest import normalize, snapshot
from threatlens.legal import map_sections
from threatlens.paths import SAMPLE_DATA
from threatlens.schema import load_incidents, load_posts
from threatlens.violations import analyse_posts, summarise

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_PREVIOUS = "2026-09-26T14:10:00+05:30"
DEFAULT_CURRENT = "2026-09-26T23:59:00+05:30"
SAMPLES = {
    "demo_day": ("posts.json", "Full demo day — 516 posts, 26 Sep 2026"),
    "sample_100": ("sample_100_posts.json", "Sample — 100 posts"),
}


def load_sample(name: str = "demo_day") -> tuple[pd.DataFrame, list[dict]]:
    """A bundled fictional dataset: normalised posts + offline incidents."""
    return (normalize(load_posts(SAMPLE_DATA / SAMPLES[name][0])),
            load_incidents(SAMPLE_DATA / "offline_incidents.json"))


def default_cutoffs(df: pd.DataFrame) -> tuple[str, str]:
    """Sample data: 14:10 -> 23:59. Other data: the mid-point of the time range -> the last post."""
    first, last = df["timestamp"].min(), df["timestamp"].max()
    if first >= pd.Timestamp(DEFAULT_PREVIOUS[:10] + "T00:00:00+05:30") and last <= pd.Timestamp(DEFAULT_CURRENT):
        return DEFAULT_PREVIOUS, DEFAULT_CURRENT
    mid = first + (last - first) / 2
    return mid.isoformat(), last.isoformat()


def run_snapshot(df: pd.DataFrame, incidents: list[dict], cutoff: str, violations: dict) -> dict:
    """M2-M4 on posts up to *cutoff* (df already normalised)."""
    snap = snapshot(df, cutoff)
    t0 = time.perf_counter()
    clusters = build_clusters(snap)
    t1 = time.perf_counter()
    classifications = [classify_cluster(c, snap, violations) for c in clusters]
    legal = [map_sections(c, cls, snap, violations) for c, cls in zip(clusters, classifications)]
    t2 = time.perf_counter()
    return {"clusters": clusters, "classifications": classifications, "legal": legal, "snap_df": snap,
            "timings": {"m2_s": round(t1 - t0, 2), "m3_m4_s": round(t2 - t1, 2)}}


def analyze(df: pd.DataFrame, incidents: list[dict], previous_cutoff: str = DEFAULT_PREVIOUS,
            current_cutoff: str = DEFAULT_CURRENT, llm_mode: str = "auto", progress=None) -> dict:
    """Full analysis. llm_mode: auto (cache -> Bob -> rules) | bob | rules."""
    t0 = time.perf_counter()
    upto = snapshot(df, current_cutoff)
    violations, vmeta = analyse_posts(upto, llm_mode, progress)
    t_v = time.perf_counter()
    prev = run_snapshot(df, incidents, previous_cutoff, violations)
    previous = build_campaign_intel(prev["snap_df"], prev["clusters"], prev["classifications"], prev["legal"],
                                    incidents, previous_cutoff, previous=None, llm_mode="rules",
                                    violations=violations)
    cur = run_snapshot(df, incidents, current_cutoff, violations)
    campaigns = build_campaign_intel(cur["snap_df"], cur["clusters"], cur["classifications"], cur["legal"],
                                     incidents, current_cutoff, previous=previous, llm_mode=llm_mode,
                                     violations=violations)
    campaigns.sort(key=lambda c: (-STATE_RANK[c["state"]], -len(c["_cluster"]["post_ids"])))
    t_end = time.perf_counter()
    in_campaign = {p for c in campaigns for p in c["_cluster"]["post_ids"]}
    return {
        "campaigns": campaigns,
        "previous": previous,
        "violations": violations,
        "violation_meta": vmeta,
        "violation_summary": summarise(violations),
        "in_campaign": in_campaign,
        "previous_cutoff": previous_cutoff,
        "current_cutoff": current_cutoff,
        "snapshot_posts": len(upto),
        "snapshot_accounts": int(upto["account_id"].nunique()),
        "llm_sources": vmeta["sources"],
        "timings": {"post_analysis_s": round(t_v - t0, 2), "campaigns_s": round(t_end - t_v, 2),
                    "total_s": round(t_end - t0, 2)},
        "generated_at": datetime.now(IST).isoformat(timespec="seconds"),
    }
