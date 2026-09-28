# BOB_PROMPTS.md — IBM Bob Prompts Used to Build ThreatLens

This file documents the exact Bob prompts used during the hackathon. Every module in `src/threatlens/` was designed and implemented through IBM Bob. This is evidence of load-bearing Bob usage (judging criterion).

---

## Prompt 0 — Project skeleton + M1 + mock data

> You are building "ThreatLens" for the IBM Bob AI Hackathon. Read PLAN.md in the repo root completely before writing anything. PLAN.md is the single source of truth; follow its schemas, thresholds and layout exactly. This repo was created from the official submission template. Read PLAN.md section 2: do not delete, rename or restructure any template file, never edit .github/workflows/validate.yml, never create a folder named "data" (the template .gitignore ignores it), and put all code inside src/.
>
> Tasks:
> 1. Create the src/ layout from PLAN.md section 5. Add src/threatlens/paths.py with pathlib constants (PKG_DIR, SAMPLE_DATA, TEMPLATES, OUTPUTS) resolved relative to the package, so code works when run from src/.
> 2. Create stub modules with docstrings, type hints and exact signatures that raise NotImplementedError: coordination.py, classify.py (with shared lexicons MOBILIZE/HOSTILE/SHARE/ALARM and TIME_RE/PLACE_RE), legal.py, correlation.py, brief.py, pipeline.py, evaluate.py.
> 3. Fully implement M1: schema.py and ingest.py.
> 4. Fully implement src/threatlens/sample_data/generate_mock.py: seed 42, ~500 posts on 2026-09-26 IST, background + C1 + C2 + C3 + D1 with staged narrative phases, media fields, fictional names, .example URLs. Also write offline_incidents.json and answer_key.json.
> 5. Implement threatlens/fixtures.py.
> 6. Edit src/.env.example, create src/requirements.txt, update src/README.md.
> 7. Tests in src/tests/test_schema.py.

---

## Prompt 1 — M2: Coordination detection

> Implement src/threatlens/coordination.py fully per PLAN.md section 7. Four edge types: text similarity (TF-IDF char_wb cosine ≥ 0.80), repost/reply, shared URL or media (≥5 accounts within 30 min), time-synced hashtag (≥8 accounts within 10-min window). Clusters = connected components ≥ 5 accounts. Five signals with exact weights. first_posters (max 3), top_amplifiers (max 5), detected_at = 5th coordinated post. Cluster ids K1, K2... by start time. Follows schema 4.4 exactly.

---

## Prompt 2 — M3 + M4: Classification and legal mapping

> Implement src/threatlens/classify.py fully per PLAN.md section 8. IBM Granite via ibm_watsonx_ai, temperature 0, ~400 max tokens. Robust JSON parse. LLM cache keyed by sha256 of sorted post_ids + task name. Rules fallback must classify C1/C2/C3/D1 correctly on its own. Shared lexicons MOBILIZE/HOSTILE/SHARE/ALARM already defined as stubs — fill them. LLM_MODE: auto | granite | rules.
>
> Also implement src/threatlens/legal.py per PLAN.md section 9. Deterministic. Eight BNS sections in legal_kb.json with suggest-when conditions. Benign → []. Every suggestion has evidence_post_ids.

---

## Prompt 3 — M5: Campaign evolution (on fixtures)

> Implement src/threatlens/correlation.py fully per PLAN.md section 10. build_campaign_intel takes df, clusters, classifications, legal, incidents, snapshot_time, optional previous. All 8 subsections: narrative phases (10.1), propagation buckets (10.2), timeline events (10.3), what changed (10.4), online-offline correlation (10.5), campaign state triggers T1-T5 (10.6), action ladder (10.7), evidence index (10.8). parse_mentioned_time handles weekdays, N baje, shaam/raat, abhi/turant, aaj raat. Every evidence_post_ids list must contain at least one real post_id. Run on fixtures first.

---

## Prompt 4 — M6: Brief + MCP + Bob analyst mode

> Implement src/threatlens/brief.py per PLAN.md section 11. render_brief(intel, analyst, analyst_assessment=None) -> (brief_id, html, path). Self-contained HTML, inline CSS, @media print, A4. All 12 sections in order. Brief ID format TB-20260926-<campaign_id>-<HHMM IST>. Saves to src/outputs/.
>
> Implement src/mcp_server.py using FastMCP stdio. Four tools: list_campaigns, get_campaign_intel, get_posts, render_threat_brief. Runs the full pipeline on import.
>
> Create src/bob/threatlens-analyst.md with instructions for the Bob analyst custom mode per PLAN.md section 11.

---

## Prompt 5 — UI (on fixtures)

> Implement src/app.py per PLAN.md section 12. Streamlit, wide layout, title "ThreatLens — Coordinated Threat Early-Warning". Sidebar with data source, snapshot time sliders (default 14:10 and 23:59), LLM mode, analyst name, Run analysis. KPI row. Campaign table with state chips and NEW/CHANGED badges. Six tabs per campaign: Overview, Timeline & narrative, Propagation, What changed & offline, Legal & actions, Evidence & brief. Evaluation expander. Safeguards expander. Colour chips: DETECTED grey, COORDINATED blue, AMPLIFYING yellow, ESCALATING orange, MOBILIZATION red. Never show a Python traceback.

---

## Prompt 6 — Integration

> Wire the full pipeline. Replace fixtures with real M2/M3/M4/M5. Run `cd src && streamlit run app.py`, load sample data, click Run analysis. Verify: 4 campaigns found, C1 and C3 in MOBILIZATION, C2 in ESCALATING, D1 in DETECTED. Verify the Bob MCP tools return valid data. Fix any integration issues.

---

## Prompt 7 — Hardening + warm Granite cache

> 1. Write src/tests/test_pipeline.py: at least 14 tests covering run_snapshot, analyze, evidence_post_ids, trigger firing, evaluation metrics (F1 > 0.7, state accuracy = 75%, D1 not escalated).
> 2. Warm llm_cache.json with 10 entries labelled source: "granite". Keys = sha256 of sorted post_ids for M3 classification and M5 narrative summaries for all 5 clusters.
> 3. Ensure `pytest tests/ -v` passes all 32 tests.
> 4. Commit one example brief to src/outputs/.

---

## Prompt 8 — Docs + submission files

> Create all root-level submission files: README.md (no [Your Project Title Here] or [Your Team Name] placeholders), submission.yaml (all required fields, track=AI), CONTRIBUTING.md, .gitignore, PLAN.md (copy from Downloads), BOB_PROMPTS.md, .github/workflows/validate.yml. Create all 5 docs/ files. Create demo/demo-video-link.txt, demo/live-demo-url.txt, 3 placeholder screenshots. Create presentation/README.md.

---

## Runtime Bob prompt — Generate threat brief

When the analyst types in Bob:

> "Generate a threat brief for CMP-1"

Bob (in threatlens-analyst mode) calls:
1. `get_campaign_intel("CMP-1")` — reads full schema-4.7 intel
2. Writes a ≤150-word assessment citing post_ids in brackets for every claim
3. `render_threat_brief("CMP-1", "Analyst", "<the assessment>")` — returns brief_id and file path

The brief is then opened and printed to PDF.

See `src/bob/threatlens-analyst.md` for the full custom-mode instructions.
