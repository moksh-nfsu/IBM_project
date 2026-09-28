"""M2 coordination detection (PLAN.md section 7)."""
from __future__ import annotations

from threatlens.coordination import build_clusters
from threatlens.ingest import snapshot


def _best(clusters, accounts):
    return max(clusters, key=lambda c: len(set(c["account_ids"]) & accounts))


def test_campaigns_found_with_high_overlap(df, answer_key):
    clusters = build_clusters(df)
    for g in ("C1", "C2", "C3"):
        acc = set(answer_key[g]["account_ids"])
        best = _best(clusters, acc)
        assert len(set(best["account_ids"]) & acc) / len(acc) >= 0.8, g
        assert best["coordination_score"] >= 60, g


def test_decoy_is_weakly_coordinated(df, answer_key):
    d1 = _best(build_clusters(df), set(answer_key["D1"]["account_ids"]))
    assert d1["coordination_score"] < 45
    assert sum(v >= 0.5 for v in d1["signals"].values()) < 2


def test_no_background_cluster(df, answer_key):
    campaign_accounts = {a for g in answer_key.values() for a in g["account_ids"]}
    for c in build_clusters(df):
        assert set(c["account_ids"]) <= campaign_accounts, "organic background accounts formed a cluster"


def test_contributions_sum_to_score(df):
    for c in build_clusters(df):
        assert abs(sum(c["contributions"].values()) - c["coordination_score"]) <= 1
        assert len(c["first_posters"]) <= 3 and len(c["top_amplifiers"]) <= 5


def test_partial_snapshot_still_finds_c1(df, answer_key):
    acc = set(answer_key["C1"]["account_ids"])
    clusters = build_clusters(snapshot(df, "2026-09-26T14:10:00+05:30"))
    assert clusters and len(set(_best(clusters, acc)["account_ids"]) & acc) >= 5


def test_victim_not_in_attacker_cluster(df, answer_key):
    """Mentions are not edges: the harassed journalist's handle never joins C2."""
    c2 = _best(build_clusters(df), set(answer_key["C2"]["account_ids"]))
    handles = set(df[df["account_id"].isin(c2["account_ids"])]["handle"])
    assert "meera_reports" not in handles
