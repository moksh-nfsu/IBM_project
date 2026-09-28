"""M5 campaign evolution (PLAN.md section 10)."""
from __future__ import annotations

from datetime import datetime

from threatlens.correlation import IST, parse_mentioned_time, tag_phase
from threatlens.schema import post_sha256
from threatlens.paths import SAMPLE_DATA

REF = datetime(2026, 9, 26, 14, 30, tzinfo=IST)  # a Saturday


def test_parse_mentioned_time():
    assert parse_mentioned_time("Sunday shaam 5 baje Ghanta Ghar chowk pahuncho", REF) == \
        datetime(2026, 9, 27, 17, 0, tzinfo=IST)
    assert parse_mentioned_time("abhi pahuncho", REF) == REF
    assert parse_mentioned_time("raat 8 baje se pehle", REF) == datetime(2026, 9, 26, 20, 0, tzinfo=IST)
    assert parse_mentioned_time("abhi bus stand, raat 8 baje se pehle niklo", REF).hour == 20
    assert parse_mentioned_time("aaj raat milte hain", REF).hour == 21
    assert parse_mentioned_time("रविवार शाम 5 बजे", REF) == datetime(2026, 9, 27, 17, 0, tzinfo=IST)
    assert parse_mentioned_time("nothing here", REF) is None


def test_tag_phase_order():
    assert tag_phase("Sunday 5 baje Ghanta Ghar chowk pahuncho, jawab dena padega", None, False) == "MOBILIZATION"
    assert tag_phase("Community B ko jawab dena padega", None, False) == "INFLAMMATORY"
    assert tag_phase("share karo", None, False) == "AMPLIFICATION"
    assert tag_phase("original claim", None, True) == "AMPLIFICATION"
    assert tag_phase("original claim", None, False) == "CLAIM"


def test_c1_story(by_group):
    c1 = by_group["C1"]
    assert c1["campaign_id"] == "CMP-1"
    assert c1["narrative"]["path"] == "CLAIM → AMPLIFICATION → INFLAMMATORY → MOBILIZATION"
    pe = c1["offline"]["planned_event"]
    assert pe["place"] == "Ghanta Ghar chowk" and pe["time"] == "2026-09-27T17:00:00+05:30"
    assert pe["hours_from_snapshot"] == 17.0
    inc01 = next(m for m in c1["offline"]["matches"] if m["incident_id"] == "INC-01")
    assert inc01["confidence"] == "HIGH" and inc01["time_delta_min"] < 0
    assert "distorts" in inc01["note"]


def test_c3_offline_outcome(by_group):
    m = next(m for m in by_group["C3"]["offline"]["matches"] if m["incident_id"] == "INC-02")
    assert m["confidence"] == "HIGH" and m["time_delta_min"] > 0 and "outcome" in m["note"]


def test_decoy_match_does_not_escalate(by_group):
    d1 = by_group["D1"]
    assert any(m["incident_id"] == "INC-05" for m in d1["offline"]["matches"])
    assert d1["state"] == "DETECTED"


def test_c2_has_no_place_time_call(by_group):
    t5 = next(t for t in by_group["C2"]["triggers"] if t["id"] == "T5")
    assert not t5["fired"] and by_group["C2"]["offline"]["planned_event"] is None


def test_what_changed_since_1410(by_group):
    wc = by_group["C1"]["what_changed"]
    assert wc["matched_previous"] and not wc["is_new_campaign"]
    kinds = {i["kind"]: i for i in wc["items"]}
    assert kinds["state_change"]["detail"] in ("AMPLIFYING → MOBILIZATION", "COORDINATED → MOBILIZATION")
    assert "Ghanta Ghar chowk" in kinds["new_locations"]["detail"]
    assert "new_accounts" in kinds
    assert by_group["C2"]["what_changed"]["is_new_campaign"]


def test_state_history_climbs(result):
    for c in result["campaigns"]:
        times = [h["entered_at"] for h in c["state_history"]]
        assert times == sorted(times)
        assert c["state_history"][-1]["state"] == c["state"]


def test_triggers_complete(result):
    for c in result["campaigns"]:
        assert [t["id"] for t in c["triggers"]] == ["T1", "T2", "T3", "T4", "T5"]
        for t in c["triggers"]:
            assert t["condition"] and t["threshold"] and t["observed"]
            assert (t["fired_at"] is not None) == t["fired"]


def test_actions_follow_the_ladder(by_group):
    c1 = by_group["C1"]
    assert {a["state"] for a in c1["actions"]} == {"DETECTED", "COORDINATED", "AMPLIFYING", "ESCALATING",
                                                   "MOBILIZATION"}
    deploy = next(a for a in c1["actions"] if a["step"].startswith("Deploy police"))
    assert "Ghanta Ghar chowk" in deploy["step"] and "17:00" in deploy["step"] and deploy["because"] == "T5"
    assert all(a["state"] == "DETECTED" for a in by_group["D1"]["actions"])


def test_evidence_hash_matches_original_record(result, df):
    import json, hashlib
    raw = {p["post_id"]: p for p in json.loads((SAMPLE_DATA / "posts.json").read_text(encoding="utf-8"))}
    c = result["campaigns"][0]
    for pid, e in c["evidence_index"].items():
        expected = hashlib.sha256(json.dumps(raw[pid], sort_keys=True, ensure_ascii=False,
                                             default=str).encode("utf-8")).hexdigest()
        assert e["sha256"] == expected
        assert e["sha256"] == post_sha256(df[df["post_id"] == pid].iloc[0])
