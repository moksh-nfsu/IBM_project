"""End-to-end: full analyze() in rules mode with the default cutoffs (PLAN.md sections 3, 10, 12)."""
from __future__ import annotations

from threatlens.correlation import STATE_RANK
from threatlens.evaluate import evaluate

SCHEMA_47 = ["campaign_id", "cluster_id", "label", "state", "state_history", "triggers", "timeline",
             "propagation", "narrative", "what_changed", "offline", "actions", "legal", "evidence_index"]


def _evidence_lists(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("_") or k == "evidence_index":
                continue
            if k == "evidence_post_ids":
                yield path, v
            else:
                yield from _evidence_lists(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _evidence_lists(v, f"{path}[{i}]")


def test_expected_states(by_group):
    assert {g: c["state"] for g, c in by_group.items()} == {
        "C1": "MOBILIZATION", "C2": "ESCALATING", "C3": "MOBILIZATION", "D1": "DETECTED"}


def test_evaluation_scores(result, answer_key):
    o = evaluate(result, answer_key)["overall"]
    assert o["mean_f1"] >= 0.8
    assert o["label_accuracy"] == 1.0
    assert o["state_accuracy"] == 1.0
    assert o["incidents_found"] == 1.0
    assert o["d1_decoy_not_escalated"]
    assert o["false_alarm_campaigns"] == [], "background accounts must not form a campaign"


def test_detection_lag_is_measured(result, answer_key):
    for row in evaluate(result, answer_key)["per_group"]:
        assert row["detection_lag_min"] is not None and 0 <= row["detection_lag_min"] <= 30


def test_schema_and_sorting(result):
    states = [STATE_RANK[c["state"]] for c in result["campaigns"]]
    assert states == sorted(states, reverse=True)
    for c in result["campaigns"]:
        for key in SCHEMA_47:
            assert key in c, f"{c['campaign_id']} missing {key}"


def test_every_finding_has_real_evidence(result, df):
    real = set(df["post_id"])
    for c in result["campaigns"] + result["previous"]:
        lists = list(_evidence_lists(c))
        assert lists
        for path, ids in lists:
            assert ids, f"{c['campaign_id']}{path} has no evidence_post_ids"
            assert set(ids) <= real, f"{c['campaign_id']}{path} cites unknown posts"
            assert set(ids) <= set(c["evidence_index"]), f"{c['campaign_id']}{path} not in evidence_index"


def test_benign_never_escalates(result):
    for c in result["campaigns"]:
        if c["label"] == "benign":
            assert STATE_RANK[c["state"]] <= STATE_RANK["COORDINATED"]
            assert c["legal"] == []


def test_legal_items_carry_disclaimer(result):
    for c in result["campaigns"]:
        for item in c["legal"]:
            assert item["disclaimer"] == "Suggested — requires legal officer review"
