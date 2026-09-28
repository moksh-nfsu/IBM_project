"""Law KB, Bob output validation, rules fallback, flexible loading and campaign legal mapping."""
from __future__ import annotations

import io

import pytest

from threatlens import bob_client
from threatlens.classify import TIME_RE, SHARE, MOBILIZE, classify_rules, find_places, find_time_phrase, lex_hit
from threatlens.law import CANDIDATES, CATEGORIES, EXCLUDED, load_kb, section
from threatlens.pipeline import analyze, load_sample
from threatlens.schema import load_posts
from threatlens.violations import rules_analyse, validate


# --- legal knowledge base (official text) ---------------------------------------------------

def test_kb_has_every_section_from_the_official_pdfs():
    kb = load_kb()
    assert sum(1 for a, _ in kb if a == "BNS") == 358
    assert ("IT Act", "66D") in kb and ("IT Act", "69A") in kb
    assert section("BNS", "196")["text"].startswith("196.(1) Whoever")
    assert "criminal intimidation" in section("BNS", "351")["text"]
    assert section("Bharatiya Nyaya Sanhita", "Section 353(1)(b)")["section"] == "353"


def test_candidates_and_categories_resolve():
    for act, sec in CANDIDATES:
        assert section(act, sec), f"{act} {sec} missing from KB"
    for cat in CATEGORIES.values():
        assert set(cat["sections"]) <= set(CANDIDATES)
    assert ("IT Act", "66A") in EXCLUDED and ("IT Act", "66A") not in CANDIDATES


# --- validation of Bob's answers -------------------------------------------------------------

def test_validate_rejects_ungrounded_citations():
    text = "Sab log Sunday 5 baje Ghanta Ghar chowk pahuncho, Community B ko sabak sikhana hai"
    raw = {"violation": True, "categories": ["unlawful_assembly_call", "made_up"], "severity": "CRITICAL",
           "evidence_quote": "not in the post", "target": "Community B", "target_type": "group",
           "sections": [{"act": "BNS", "section": "189", "explanation": "calls five or more to assemble"},
                        {"act": "IT Act", "section": "66A", "explanation": "offensive message"},
                        {"act": "BNS", "section": "302(1)", "explanation": ""},
                        {"act": "IPC", "section": "153A", "explanation": "old code"}]}
    v = validate(raw, text)
    assert v["categories"] == ["unlawful_assembly_call"] and v["severity"] == "critical"
    assert [(s["act"], s["section"]) for s in v["sections"]] == [("BNS", "189")]
    assert v["sections"][0]["title"] == "Unlawful assembly" and v["sections"][0]["page"]
    assert "IT Act 66A" in v["rejected_sections"] and "IPC 153A" in v["rejected_sections"]
    assert v["evidence_quote"] in text


def test_validate_non_violation_is_clean():
    v = validate({"violation": False, "sections": [{"act": "BNS", "section": "196", "explanation": "x"}]}, "hello")
    assert not v["violation"] and v["sections"] == [] and v["severity"] is None


def test_extract_json_tolerates_chatter():
    assert bob_client.extract_json('Here you go:\n```json\n{"results": [{"id": "T1"}]}\n```')["results"][0]["id"] == "T1"


# --- rules fallback --------------------------------------------------------------------------

def test_rules_fallback_examples():
    assert "unlawful_assembly_call" in rules_analyse("Sunday shaam 5 baje Ghanta Ghar chowk pahuncho")["categories"]
    assert "criminal_intimidation" in rules_analyse("@x we know where you work, delete your report")["categories"]
    assert "impersonation_fraud" in rules_analyse("Verification ke liye apna OTP bhejein")["categories"]
    assert not rules_analyse("What a win for India tonight")["violation"]
    for s in rules_analyse("We know where you live @x")["sections"]:
        assert (s["act"], s["section"]) in CANDIDATES and s["explanation"]


def test_lexicon_matching_uses_word_boundaries():
    assert lex_hit("RT karo sab", SHARE) and not lex_hit("apartment party", SHARE)
    assert not TIME_RE.search("nikal jao") and TIME_RE.search("kal milte hain")
    assert lex_hit("सब लोग पहुंचो", MOBILIZE)
    assert find_places("Abhi Nandpur bus stand pahuncho") == ["Nandpur bus stand"]
    assert find_time_phrase("Sunday shaam 5 baje Ghanta Ghar chowk") == "Sunday shaam 5 baje"


# --- flexible loading ------------------------------------------------------------------------

def test_loader_accepts_minimal_csv():
    f = io.BytesIO(b"content,username,created_at\nhi #tag @a https://x.example/1,ravi,2026-01-02 10:00\nbye,sita,"
                   b"2026-01-02 11:00\n")
    f.name = "posts.csv"
    df = load_posts(f)
    assert list(df["post_id"]) == ["P0001", "P0002"] and df["hashtags"][0] == ["#tag"]
    assert df["mentions"][0] == ["@a"] and str(df["timestamp"][0].tzinfo)
    assert any("text" in x for x in df.attrs["inferred"])


def test_loader_rejects_files_without_text():
    f = io.BytesIO(b'[{"id": 1, "user": "x"}]')
    f.name = "p.json"
    with pytest.raises(ValueError, match="text"):
        load_posts(f)


# --- campaign classification and legal mapping (rules mode) ---------------------------------

def test_campaign_labels_and_sections(by_group):
    assert {g: c["label"] for g, c in by_group.items()} == {
        "C1": "incitement", "C2": "harassment", "C3": "misinformation", "D1": "benign"}
    secs = {g: {l["id"] for l in c["legal"]} for g, c in by_group.items()}
    assert {"BNS 196", "BNS 189"} <= secs["C1"]
    assert "BNS 351" in secs["C2"] and "BNS 353" in secs["C3"] and secs["D1"] == set()
    for c in by_group.values():
        for l in c["legal"]:
            assert l["evidence_post_ids"] and l["reason"] and l["offence"]
            assert (l["act"], l["section"]) in CANDIDATES


def test_rules_classifier_without_post_analysis(by_group, df):
    assert classify_rules(by_group["C2"]["_cluster"], df)["label"] == "harassment"


# --- cached IBM Bob results (committed cache; skipped if absent) -------------------------------

def test_bob_cache_flags_every_standalone_violation(answer_key):
    df, incidents = load_sample("sample_100")
    r = analyze(df, incidents, llm_mode="auto")
    if r["llm_sources"].get("cache", 0) < len(df):
        pytest.skip("Bob answer cache not warmed for the 100-post sample")
    for pid, expected in answer_key["S1"]["expected_categories"].items():
        v = r["violations"][pid]
        assert v["violation"] and set(expected) & set(v["categories"]), pid
        assert all(s["explanation"] for s in v["sections"])
    benign = [p for p in answer_key["D1"]["post_ids"] if p in r["violations"]]
    assert not any(r["violations"][p]["violation"] for p in benign)
