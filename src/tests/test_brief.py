"""M6 brief and the MCP tools Bob calls (PLAN.md section 11)."""
from __future__ import annotations

import re

import pytest

from threatlens.brief import render_brief


def test_brief_contents(by_group):
    c1 = by_group["C1"]
    brief_id, html, path = render_brief(c1, "Inspector Demo")
    assert re.fullmatch(r"TB-20260926-CMP-1-\d{4}", brief_id)
    assert path.exists() and path.read_text(encoding="utf-8") == html
    assert brief_id in html and "RESTRICTED" in html and "MOBILIZATION" in html
    assert re.search(r"\b[0-9a-f]{64}\b", html)
    assert "Suggested — requires legal officer review" in html
    assert "Human review required before any action" in html
    assert "Drafted by IBM Bob" not in html
    path.unlink()


def test_brief_with_bob_assessment_is_labelled_and_escaped(by_group):
    _, html, path = render_brief(by_group["C2"], "Inspector Demo", "Harassment of @meera_reports [P0458] <b>x</b>")
    assert "Drafted by IBM Bob from campaign intelligence; reviewed by Inspector Demo" in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html
    path.unlink()


def test_mcp_tools_callable():
    mcp_server = pytest.importorskip("mcp_server")
    rows = mcp_server.list_campaigns("2026-09-26T14:10", "2026-09-26T23:59")
    assert rows[0]["campaign_id"] == "CMP-1" and rows[0]["state"] == "MOBILIZATION"
    intel = mcp_server.get_campaign_intel("CMP-1")
    assert intel["state"] == "MOBILIZATION" and "cluster_facts" in intel
    assert not any(k.startswith("_") for k in intel)
    assert "error" in mcp_server.get_campaign_intel("CMP-99")
    posts = mcp_server.get_posts(intel["triggers"][4]["evidence_post_ids"][:2])
    assert all(len(p["sha256"]) == 64 for p in posts)
    out = mcp_server.render_threat_brief("CMP-1", "Inspector Demo", "Test [P0421].")
    assert out["assessment_source"] == "IBM Bob"
    from pathlib import Path
    Path(out["path"]).unlink()
    early = mcp_server.list_campaigns("14:10", "15:00")
    assert early[0]["planned_event"]["hours_from_snapshot"] == 26.0
