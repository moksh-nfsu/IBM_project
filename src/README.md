# ThreatLens — source

ThreatLens checks social-media posts against the **Bharatiya Nyaya Sanhita, 2023** and the
**Information Technology Act, 2000**. It uses **IBM Bob** as the reasoning engine, then detects
**coordinated campaigns** and how far they have escalated toward offline action.

## Run

```bash
cd src
pip install -r requirements.txt
copy .env.example .env        # then put your BOB_API_KEY in src/.env
streamlit run app.py          # the 100-post sample is analysed on first load
pytest -q                     # 57 tests, offline (uses the committed Bob answer cache)
python mcp_server.py          # MCP tools so IBM Bob can draft briefs at runtime
```

IBM Bob is called through **Bob Shell**, its official headless CLI (`bob run --format json`).
Bob has no plain HTTP API. Install Bob Shell with
`powershell -c "irm -Uri https://bob.ibm.com/download/bobshell.ps1 | iex"` (needs Node.js 24+).
Without Bob, the app switches to offline lexicon rules and says so on screen.

## What happens to an upload

1. **Load (M1).** Accepts a JSON list or CSV; only a `text` column is required. Common export
   column names are mapped automatically, and anything inferred is listed on screen. Each post is
   hashed (SHA-256) exactly as uploaded.
2. **Violations (IBM Bob).** Posts are sent in batches of 20, and identical texts are sent only once.
   For each post, Bob returns:
   - the violation types, severity, target, and place/time;
   - the BNS / IT Act sections it attracts, with a 1–2 sentence explanation of how the post's own
     words meet each section.

   Bob may only cite the 23 offence sections in `law.CANDIDATES`, and it is shown their official text.
   Any other citation (IPC, IT Act §66A, unknown sections) is rejected. Answers are cached in
   `sample_data/llm_cache.json`.
3. **Coordination (M2, no AI).** Accounts are linked by near-identical text, reposts, shared
   links/images and hashtag bursts; each group of 5+ accounts gets a 0–100 score.
4. **Campaign label & legal (M3, M4).** Bob's per-post results are aggregated per campaign. BNS 61
   and BNS 57 are added by rule from the coordination evidence.
5. **Escalation (M5, no AI).** Each campaign gets a state, DETECTED → … → MOBILIZATION, from explicit
   triggers, plus its timeline, narrative, what changed, offline-incident matches, the planned
   gathering and an action ladder.
6. **Brief (M6).** A printable HTML brief; IBM Bob can draft its assessment through `mcp_server.py`.

## Data sources

| Data | Source | Status |
|---|---|---|
| BNS 2023 text | Gazette of India Extraordinary, Part II Sec. 1, No. 53, 25 Dec 2023 (CG-DL-E-25122023-250883) — `threatlens/law/sources/bns_2023_gazette.pdf` | Official; 358 sections extracted verbatim into `law/law_kb.json` |
| IT Act 2000 text | Act No. 21 of 2000, updated text (Legislative Department / India Code) — `threatlens/law/sources/it_act_2000_updated.pdf` | Official; §66A flagged as struck down (*Shreya Singhal*, 2015) |
| Bundled posts, incident log | `threatlens/sample_data/generate_mock.py` (seed 42): `sample_100_posts.json/.csv`, `posts.json` (522 posts) | **Synthetic** — invented people, places and URLs; real users' posts are not redistributed |
| Your data | Upload in the app | Hashed on load; nothing stored except the Bob answer cache |

Rebuild the legal KB from the PDFs with `python -m threatlens.law.build_kb`.

## Layout

```
app.py                      Streamlit UI (.streamlit/config.toml hides deploy/dev menus)
mcp_server.py               MCP tools for IBM Bob: list_campaigns, get_campaign_intel, get_posts, list_violations, render_threat_brief
templates/brief.html        Jinja2 brief (A4, print to PDF)
threatlens/
  law/                      official PDFs, build_kb.py, law_kb.json, candidate sections + violation taxonomy
  bob_client.py             IBM Bob Shell runner (sandboxed: ask mode, tools disabled, empty workspace, stdin prompt)
  violations.py             per-post analysis via Bob, validation against the KB, rules fallback
  schema.py, ingest.py      M1 flexible loader, PII masking, snapshots, hashing
  coordination.py           M2   classify.py  M3   legal.py  M4   correlation.py  M5   brief.py  M6
  pipeline.py, evaluate.py
  sample_data/              generator, samples, incidents, answer key, llm_cache.json
```

## Results on the bundled data (IBM Bob, cached)

| | 522-post demo day | 100-post sample |
|---|---|---|
| Campaigns found / false alarms | 4 / 0 | 4 / 0 |
| Campaign label & state accuracy | 100 % / 100 % | 100 % / 100 % |
| Standalone violations found | 6 of 6 | 6 of 6 |
| Ordinary posts wrongly flagged | 0 of 387 | 0 |
| Bob calls / cost (first run) | 19 / 0.35 bobcoins, 88 s | 4 / 0.10 bobcoins, 50 s |

The bundled data is synthetic and was built to exercise every rule, so these scores show that the
logic works. They do not measure real-world accuracy. Legal output is a suggestion for a legal officer.
