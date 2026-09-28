"""Tests for M1 (schema.py, ingest.py) and the generated mock data.

Run from src/::

    pytest tests/test_schema.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from threatlens.paths import SAMPLE_DATA
from threatlens.schema import load_posts, load_incidents
from threatlens.ingest import normalize, snapshot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def posts_df():
    """Load and normalise the generated posts.json."""
    df = load_posts(SAMPLE_DATA / "posts.json")
    return normalize(df)


@pytest.fixture(scope="module")
def answer_key() -> dict:
    path = SAMPLE_DATA / "answer_key.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def incidents() -> list[dict]:
    return load_incidents(SAMPLE_DATA / "offline_incidents.json")


# ---------------------------------------------------------------------------
# Section 1: Required fields exist in the loaded DataFrame
# ---------------------------------------------------------------------------

class TestRequiredFields:
    REQUIRED = [
        "post_id", "account_id", "handle", "account_created_at",
        "followers", "text", "lang", "timestamp",
        "hashtags", "mentions", "urls", "media",
        "reply_to", "repost_of", "district", "platform",
    ]
    NORMALISED = ["text_masked", "hashtags_lower", "account_age_days"]

    def test_raw_required_columns_exist(self, posts_df):
        for col in self.REQUIRED:
            assert col in posts_df.columns, f"Missing column: {col}"

    def test_normalised_columns_exist(self, posts_df):
        for col in self.NORMALISED:
            assert col in posts_df.columns, f"Missing normalised column: {col}"


# ---------------------------------------------------------------------------
# Section 2: Post count is within the expected range (450–550)
# ---------------------------------------------------------------------------

class TestPostCount:
    def test_post_count_in_range(self, posts_df):
        n = len(posts_df)
        assert 450 <= n <= 550, f"Expected 450–550 posts, got {n}"


# ---------------------------------------------------------------------------
# Section 3: Every answer-key post_id exists in the loaded DataFrame
# ---------------------------------------------------------------------------

class TestAnswerKeyPostIds:
    def test_all_answer_key_post_ids_present(self, posts_df, answer_key):
        loaded_ids = set(posts_df["post_id"].tolist())
        for group_key, group in answer_key.items():
            for pid in group["post_ids"]:
                assert pid in loaded_ids, (
                    f"Answer key post {pid} (group {group_key}) not in posts.json"
                )


# ---------------------------------------------------------------------------
# Section 4: Every incident parses correctly
# ---------------------------------------------------------------------------

class TestIncidentParsing:
    REQUIRED_INCIDENT_FIELDS = [
        "incident_id", "reported_at", "district",
        "location", "category", "description", "source",
    ]

    def test_all_incidents_have_required_fields(self, incidents):
        for inc in incidents:
            for field in self.REQUIRED_INCIDENT_FIELDS:
                assert field in inc, f"Incident {inc.get('incident_id')} missing {field}"

    def test_reported_at_is_tz_aware(self, incidents):
        from datetime import datetime
        for inc in incidents:
            reported_at = inc["reported_at"]
            assert isinstance(reported_at, datetime), (
                f"Incident {inc['incident_id']}: reported_at should be datetime, got {type(reported_at)}"
            )
            assert reported_at.tzinfo is not None, (
                f"Incident {inc['incident_id']}: reported_at should be tz-aware"
            )

    def test_expected_incident_ids_present(self, incidents):
        inc_ids = {i["incident_id"] for i in incidents}
        for expected in ("INC-01", "INC-02", "INC-04", "INC-05"):
            assert expected in inc_ids, f"Expected incident {expected} not found"


# ---------------------------------------------------------------------------
# Section 5: C1 contains posts of all 4 narrative phases
# ---------------------------------------------------------------------------

class TestC1NarrativePhases:
    """Verify that posts in answer_key C1 cover all four narrative phases."""

    def _has_claim(self, text: str) -> bool:
        return any(w in text for w in [
            "dukaanein todi", "tod di", "shops tod", "tod-phod",
        ])

    def _has_amplification(self, text: str) -> bool:
        t = text.lower()
        return any(w in t for w in [
            "share karo", "forward karo", "sabko batao", "viral karo", "rt karo",
        ])

    def _has_inflammatory(self, text: str) -> bool:
        return any(w in text for w in [
            "chup nahi baithenge", "jawab dena", "ab nahi rukenge", "chup nahi",
            "sabak", "seedhe seedhe nahi",
        ])

    def _has_mobilization(self, text: str) -> bool:
        return any(w in text for w in [
            "pahuncho", "ikattha ho", "ikattha",
        ])

    def test_c1_has_all_four_phases(self, posts_df, answer_key):
        c1_pids = set(answer_key["C1"]["post_ids"])
        c1_rows = posts_df[posts_df["post_id"].isin(c1_pids)]

        texts = c1_rows["text"].tolist()

        has_claim = any(self._has_claim(t) for t in texts)
        has_amplification = any(self._has_amplification(t) for t in texts)
        has_inflammatory = any(self._has_inflammatory(t) for t in texts)
        has_mobilization = any(self._has_mobilization(t) for t in texts)

        assert has_claim, "C1: No CLAIM-phase posts found"
        assert has_amplification, "C1: No AMPLIFICATION-phase posts found"
        assert has_inflammatory, "C1: No INFLAMMATORY-phase posts found"
        assert has_mobilization, "C1: No MOBILIZATION-phase posts found"


# ---------------------------------------------------------------------------
# Section 6: Additional sanity checks
# ---------------------------------------------------------------------------

class TestDataSanity:
    def test_timestamps_are_tz_aware(self, posts_df):
        for ts in posts_df["timestamp"].head(20):
            assert ts.tzinfo is not None, "timestamp must be tz-aware"

    def test_account_created_at_tz_aware(self, posts_df):
        for ts in posts_df["account_created_at"].head(20):
            assert ts.tzinfo is not None, "account_created_at must be tz-aware"

    def test_list_columns_are_lists(self, posts_df):
        for col in ("hashtags", "mentions", "urls", "media"):
            for val in posts_df[col].head(50):
                assert isinstance(val, list), f"{col}: expected list, got {type(val)}"

    def test_hashtags_lower_are_lowercase(self, posts_df):
        for tags in posts_df["hashtags_lower"].head(50):
            for tag in tags:
                assert tag == tag.lower(), f"hashtags_lower contains uppercase: {tag}"

    def test_account_age_days_non_negative(self, posts_df):
        assert (posts_df["account_age_days"] >= 0).all(), "account_age_days has negative values"

    def test_snapshot_filters_correctly(self, posts_df):
        cutoff = "2026-09-26T14:10:00+05:30"
        snapped = snapshot(posts_df, cutoff)
        from datetime import datetime, timezone, timedelta
        _IST = timezone(timedelta(hours=5, minutes=30))
        cutoff_dt = datetime.fromisoformat(cutoff)
        assert len(snapped) < len(posts_df), "Snapshot should reduce post count"
        for ts in snapped["timestamp"]:
            assert ts <= cutoff_dt, f"Snapshot returned post after cutoff: {ts}"

    def test_text_masked_replaces_email(self, posts_df):
        # Inject a test row in memory only
        from threatlens.ingest import _mask_pii
        text_with_email = "Contact me at test.user@example.com for details"
        masked = _mask_pii(text_with_email)
        assert "[EMAIL]" in masked, "Email should be replaced by [EMAIL]"
        assert "test.user@example.com" not in masked

    def test_text_masked_replaces_phone(self):
        from threatlens.ingest import _mask_pii
        text_with_phone = "Call 9876543210 for more info"
        masked = _mask_pii(text_with_phone)
        assert "[PHONE]" in masked, "Phone should be replaced by [PHONE]"
        assert "9876543210" not in masked

    def test_c1_answer_key_has_all_groups(self, answer_key):
        for group in ("C1", "C2", "C3", "D1"):
            assert group in answer_key, f"Answer key missing group {group}"

    def test_answer_key_has_expected_states(self, answer_key):
        assert answer_key["C1"]["expected_state"] == "MOBILIZATION"
        assert answer_key["C2"]["expected_state"] == "ESCALATING"
        assert answer_key["C3"]["expected_state"] == "MOBILIZATION"
        assert answer_key["D1"]["expected_state"] == "DETECTED"
