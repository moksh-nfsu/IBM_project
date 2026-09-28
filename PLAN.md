# ThreatLens: Coordinated Threat Early-Warning Engine
IBM Bob AI Hackathon, Problem 06. Build time: 4 hours. **All code is written through IBM Bob.** At runtime, IBM Granite (watsonx.ai) classifies threats, and IBM Bob (via an MCP server) writes the analyst assessment in the final brief.

> **Every Bob session must read this file first.** Do not change the schemas in section 4 without telling the whole team.

---

## 1. What we are building

A Streamlit app plus an MCP server. The app loads a batch of mock social media posts and a mock offline-incident log, then runs six modules:

| # | Module | Output |
|---|---|---|
| M1 | Ingest & normalise | clean DataFrame, PII-masked text |
| M2 | Coordination detection | clusters of accounts acting together + coordination score with per-signal breakdown |
| M3 | Threat classification (Granite, rules fallback) | label, evidence quote, call to action, place, time |
| M4 | Legal mapping | suggested BNS / IPC sections with reasons |
| M5 | **Threat correlation & campaign evolution** | campaign timeline, propagation, narrative evolution, what changed, online–offline correlation, **campaign state** and explicit escalation triggers, all linked to evidence posts |
| M6 | Threat brief | HTML brief (printable to PDF). Bob writes the analyst assessment through MCP tools; a deterministic fallback exists |

**There is no numeric risk score.** M2's coordination score explains *how coordinated* a cluster is. How dangerous a campaign is comes only from M5's descriptive state:
`DETECTED → COORDINATED → AMPLIFYING → ESCALATING → MOBILIZATION`

## 2. Submission template rules (non-negotiable)

The repo is created from `drijesh-ppatel/bob-ai-hackathon-submission-template` using **"Use this template"** (not Fork), named `bob-ai-hackathon-<team-name>`, and set to **Public**.

- **All source code lives in `src/`.** The top-level structure stays as in the template.
- **Do not delete or rename** any template file: `README.md`, `submission.yaml`, `CONTRIBUTING.md`, `docs/*.md`, `demo/*`, `presentation/README.md`, `.github/workflows/validate.yml` (never edit this file), `.gitignore`.
- The template's `.gitignore` ignores **any folder named `data/`**, `logs/` and `*.log`. **Never create a folder called `data`.** Our sample files go in `src/threatlens/sample_data/`.
- Env vars go in `src/.env.example` using the template's names: `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL`. We add `WATSONX_MODEL_ID` and `LLM_MODE`. Remove the template's unused DATABASE/SLACK/APP lines.
- The CI check (`validate.yml`) fails if: `submission.yaml` required fields are empty, `team.track` is not one of `AI|DevOps|Sustainability|Open`, `src/` has no code, `demo/demo-video-link.txt` still holds the placeholder URL, or `README.md` still contains `[Your Project Title Here]` or `[Your Team Name]`.
- Deliverables the judges expect: filled `submission.yaml`, `README.md`, the 4 docs, **3+ screenshots** `demo/screenshots/01-*.png…`, a **3–5 min demo video link**, `presentation/slides.pdf`, `demo/live-demo-url.txt` (write `NOT DEPLOYED — run locally using docs/setup-guide.md`).
- Judging (100 pts): technical quality 25, innovation 25, problem depth 15, working demo 15, **IBM Bob integration 10 (must be load-bearing, not name-dropped)**, docs & reproducibility 10. Judges **read the code in `src/`**, and honest limitations are rewarded.

## 3. Hard engineering rules

- Python 3.10+. Streamlit UI. No React, no database, no Docker.
- Everything in memory (pandas). Files only for sample data, the legal KB, the LLM cache and generated briefs.
- `src/requirements.txt`: `streamlit pandas numpy scikit-learn networkx plotly pyvis jinja2 python-dotenv ibm-watsonx-ai mcp pytest`
- All data is fictional: districts, communities, people, URLs (`.example` domain only).
- **Works with no internet:** `LLM_MODE=auto` → cache → Granite → rules. The warmed cache `src/threatlens/sample_data/llm_cache.json` **is committed**, so judges see real Granite outputs without keys.
- Every legal suggestion shows "Suggested — requires legal officer review".
- Timestamps are ISO 8601 with IST offset `+05:30`. All paths are built with `pathlib` relative to the package, so `cd src && streamlit run app.py` and `cd src && pytest` both work.
- **Every finding M5 produces must carry `evidence_post_ids` (at least one real post_id).** A test enforces this.

## 4. Shared schemas (the contract between modules)

### 4.1 Post — `sample_data/posts.json` (list of objects)
| field | type | example |
|---|---|---|
| post_id | str | `"P0001"` |
| account_id | str | `"A0001"` |
| handle | str | `"veer_4471"` |
| account_created_at | ISO str | `"2026-09-24T10:00:00+05:30"` |
| followers | int | `12` |
| text | str | Hinglish / Hindi (Devanagari) / English |
| lang | str | `"en"` / `"hi"` / `"hinglish"` |
| timestamp | ISO str | `"2026-09-26T14:03:11+05:30"` |
| hashtags | list[str] | `["#NandpurJaago"]` (keep `#`) |
| mentions | list[str] | `["@meera_reports"]` |
| urls | list[str] | `["https://nandpur-jaago.example/call"]` |
| media | list[str] | `["media/c1_poster_a.jpg"]` (same filename = same image reused) |
| reply_to | str or null | post_id |
| repost_of | str or null | post_id |
| district | str | `"Nandpur"` |
| platform | str | `"X"` / `"Instagram"` / `"Facebook"` |

### 4.2 Offline incident — `sample_data/offline_incidents.json`
```json
{"incident_id": "INC-01", "reported_at": "2026-09-26T12:40:00+05:30", "district": "Keshavnagar",
 "location": "Keshav market", "category": "clash|crowd_gathering|panic|accident|celebration|suspicious_activity",
 "description": "Minor dispute between two shopkeepers, 2 injured, situation controlled",
 "source": "Mock police control-room log"}
```

### 4.3 Answer key — `sample_data/answer_key.json`
```json
{"C1": {"type": "incitement", "account_ids": [], "post_ids": [], "expected_state": "MOBILIZATION", "expected_incidents": ["INC-01"]},
 "C2": {"type": "harassment", "...": "...", "expected_state": "ESCALATING", "expected_incidents": []},
 "C3": {"type": "misinformation", "...": "...", "expected_state": "MOBILIZATION", "expected_incidents": ["INC-02"]},
 "D1": {"type": "benign", "...": "...", "expected_state": "DETECTED", "expected_incidents": ["INC-05"]}}
```

### 4.4 Cluster — M2 output (`coordination.py`)
```python
{"cluster_id": "K1", "account_ids": [...], "post_ids": [...],
 "first_posters": [account_id, ...],            # max 3
 "top_amplifiers": [account_id, ...],           # max 5
 "hashtags": [...], "urls": [...], "media": [...], "districts": {"Nandpur": 31},
 "start": iso, "end": iso, "detected_at": iso,   # detected_at = 5th coordinated post
 "near_dup_groups": [[post_id, ...], ...],      # groups of near-copied posts
 "edges": [[acc_a, acc_b, ["similar","repost","url","burst"]], ...],
 "signals": {"text_similarity": 0-1, "time_sync": 0-1, "fresh_accounts": 0-1, "shared_url": 0-1, "amplification": 0-1},
 "contributions": {"text_similarity": pts, ...},
 "coordination_score": 0-100}
```

### 4.5 Classification — M3 output (`classify.py`)
```python
{"label": "incitement"|"harassment"|"misinformation"|"benign", "confidence": 0.0-1.0,
 "target": "Community B"|"@meera_reports"|None, "target_type": "group"|"individual"|"public"|None,
 "evidence_quote": "exact substring of one post", "evidence_post_id": "P0123",
 "call_to_action": bool, "location_mentioned": "Ghanta Ghar chowk"|None, "time_mentioned": "Sunday shaam 5 baje"|None,
 "false_claim": bool, "intimidation": bool, "rationale": "one sentence", "source": "granite"|"rules"|"cache"}
```

### 4.6 Legal — M4 output (`legal.py`): list of
```python
{"id": "enmity", "act": "BNS", "section": "196", "old_section": "IPC 153A", "offence": "...",
 "reason": "one sentence citing evidence", "evidence_post_ids": [...]}
```

### 4.7 Campaign intelligence — M5 output (`correlation.py`), one per cluster
```python
{
 "campaign_id": "CMP-1", "cluster_id": "K1", "label": "incitement",
 "state": "MOBILIZATION",
 "state_history": [{"state": "DETECTED", "entered_at": iso, "trigger_id": "T1"}, ...],
 "triggers": [{"id": "T5", "state": "MOBILIZATION", "condition": "human-readable rule",
               "threshold": "≥3 accounts", "observed": "7 accounts", "fired": True, "fired_at": iso,
               "evidence_post_ids": [...]}],
 "timeline": [{"t": iso, "type": "FIRST_POST|COORDINATION_BURST|AMPLIFICATION|NARRATIVE_SHIFT|MOBILIZATION_SIGNAL|OFFLINE_MATCH|STATE_CHANGE",
               "description": "...", "evidence_post_ids": [...]}],
 "propagation": {"buckets": [{"start": iso, "posts": n, "new_accounts": n, "cum_accounts": n, "cum_posts": n,
                              "new_hashtags": [...], "new_urls": [...], "new_media": [...], "reposts": n}],
                 "peak_bucket": iso, "first_posters": [{"account_id","handle","first_post_id","t"}],
                 "amplifiers": [{"account_id","handle","reposts_received","copies_of_their_text","followers","evidence_post_ids"}],
                 "potential_reach": int},             # sum of followers of all cluster accounts
 "narrative": {"phases": [{"phase": "CLAIM|AMPLIFICATION|INFLAMMATORY|MOBILIZATION", "first_seen": iso,
                           "post_count": n, "example_quote": "...", "evidence_post_ids": [...]}],
               "path": "CLAIM → AMPLIFICATION → INFLAMMATORY → MOBILIZATION",
               "summary": "2 sentences", "summary_source": "granite"|"rules"|"cache"},
 "what_changed": {"previous_cutoff": iso|None, "matched_previous": "CMP-x"|None, "is_new_campaign": bool,
                  "items": [{"kind": "new_accounts|new_posts|new_hashtags|new_urls|new_locations|label_change|state_change|new_signals",
                             "detail": "...", "evidence_post_ids": [...]}]},
 "offline": {"matches": [{"incident_id","confidence": "HIGH|MEDIUM","match": "location+time|location",
                          "time_delta_min": int, "note": "...", "evidence_post_ids": [...]}],
             "planned_event": {"place": "Ghanta Ghar chowk", "time": iso, "hours_from_snapshot": float,
                               "evidence_post_ids": [...]} | None},
 "actions": [{"step": "...", "because": "T5", "evidence_post_ids": [...]}],
 "legal": [...],                                      # passed through from M4
 "evidence_index": {post_id: {"handle","timestamp","text_masked","sha256"}}   # every post_id cited anywhere above
}
```

## 5. Repo layout (inside the template)
```
<repo root>
├── PLAN.md  BOB_PROMPTS.md              # ours (extra top-level files are allowed)
├── README.md  submission.yaml  CONTRIBUTING.md  .gitignore  .github/   # template, keep
├── docs/  problem-statement.md  solution-overview.md  architecture.md  setup-guide.md  (+ bob-usage.md)
├── demo/  demo-video-link.txt  live-demo-url.txt  screenshots/01-*.png ...
├── presentation/  slides.pdf
└── src/
    ├── README.md  .env.example  requirements.txt
    ├── app.py                           # Streamlit UI
    ├── mcp_server.py                    # M6: tools Bob calls at runtime
    ├── bob/threatlens-analyst.md        # Bob custom-mode / rules text for the analyst role
    ├── templates/brief.html
    ├── outputs/                         # generated briefs (commit 1 example brief)
    ├── tests/test_*.py
    └── threatlens/
        ├── __init__.py  paths.py        # pathlib constants for sample_data, templates, outputs
        ├── schema.py  ingest.py         # M1
        ├── coordination.py              # M2
        ├── classify.py                  # M3
        ├── legal.py                     # M4
        ├── correlation.py               # M5
        ├── brief.py                     # M6 renderer
        ├── pipeline.py  evaluate.py  fixtures.py
        └── sample_data/  generate_mock.py  posts.json  offline_incidents.json  answer_key.json  legal_kb.json  llm_cache.json
```

## 6. M1: Mock data (`sample_data/generate_mock.py`) and ingest

`random.seed(42)`, **~500 posts**, all on **2026-09-26 (IST)**. Fictional districts: Nandpur, Sitavali, Keshavnagar, Ambarpur, Rudrakot. Groups: "Community A", "Community B". Keep all language non-graphic: no slurs, no weapons detail, no sexual content.

- **Background (~370 posts, ~150 accounts):** accounts 1–6 years old, followers 50–20,000, natural handles; cricket, local news, food, traffic, movies, mild politics; mixed en/hi/hinglish; varied hashtags; occasional organic replies/reposts; a few unique media files.
- **C1 Incitement (~45 posts, 25 fresh accounts, created 2026-09-23..25, followers < 60, handles like `veer_4471`), `#NandpurJaago`, URL `https://nandpur-jaago.example/call`, media `media/c1_poster_a.jpg`. Staged narrative:**
  - 13:50–13:58 **CLAIM** (2 seed accounts): exaggerated false claim about the real Keshav market dispute, e.g. *"Keshav market mein Community B ke logon ne dukaanein todi, police chup hai"*.
  - 14:00–14:12 **AMPLIFICATION** (~12 accounts): reposts of the seeds + near-copies "share karo, sabko batao".
  - 14:12–14:25 **INFLAMMATORY** (~8 accounts): "ab chup nahi baithenge, Community B ko jawab dena padega".
  - 14:25–14:40 **MOBILIZATION** (~10 accounts): *"Sunday shaam 5 baje Ghanta Ghar chowk pahuncho, sab ikattha ho"*.
- **C2 Harassment (~30 posts, 15 fresh accounts) 16:00–16:40, `#ExposeMeera`, mentions `@meera_reports` (fictional journalist):** CLAIM "her report is fake, paid journalist" → AMPLIFICATION → INTIMIDATION "we know where you work", "delete your report or face consequences". **No place + time call to action.**
- **C3 Misinformation (~35 posts, 20 accounts, mix of fresh and older) 18:30–19:10, `#NandpurDamAlert`, URL `https://nandpur-alert.example/dam`, media `media/c3_dam_crack.jpg`:** CLAIM "Nandpur dam mein crack, prashasan chhupa raha hai" → AMPLIFICATION "forward karo" → MOBILIZATION *"abhi Nandpur bus stand pahuncho, raat 8 baje se pehle shehar chhodo"* (≥4 accounts).
- **D1 Benign decoy (~25 posts, 25 old high-follower accounts) 21:00–21:20, `#IndiaWins`:** diverse, non-copied cricket celebration, no reposts, no URLs.
- **Offline incidents (`offline_incidents.json`):** INC-01 12:40 Keshav market, Keshavnagar, clash (precursor that C1 distorts); INC-02 19:25 Nandpur bus stand, panic crowd/traffic jam (outcome of C3); INC-04 10:15 Sitavali highway accident (noise); INC-05 21:35 Ambarpur, celebration crowd (matches the benign D1).
- **Answer key** as in 4.3.

**Ingest (`schema.py`, `ingest.py`):** `load_posts(path)` accepts JSON list or CSV, parses tz-aware datetimes, keeps lists as lists, validates the required fields. `normalize(df)` adds `text_masked` (phones → `[PHONE]`, emails → `[EMAIL]`), lowercase hashtag copies for matching, `account_age_days` at post time. `load_incidents(path)` does the same for incidents. `snapshot(df, cutoff)` returns posts with `timestamp <= cutoff`.

## 7. M2: Coordination detection (`coordination.py`)

Undirected **account graph** (networkx) with edges from:
1. **Text similarity:** TF-IDF `analyzer="char_wb", ngram_range=(3,5)`, cosine ≥ **0.80** between posts of different accounts.
2. **Repost / reply** → the author of `repost_of` / `reply_to`.
3. **Shared URL or shared media:** same URL or media file posted by ≥ **5** accounts within **30 min**.
4. **Time-synced hashtag:** same hashtag by ≥ **8** distinct accounts within a **10-min** sliding window.

Clusters = connected components with **≥ 5 accounts**. Mentions are **not** edges (the victim must not join the attacker cluster).

| signal | definition | weight |
|---|---|---|
| text_similarity | share of cluster posts with a ≥0.80 near-duplicate from another account | 25 |
| time_sync | share of cluster posts inside the densest 10-min window | 20 |
| fresh_accounts | share of accounts with age < 30 days AND followers < 100; +0.2 (cap 1) if >50% of handles match `^[a-z]+_?\d{3,}$` | 20 |
| shared_url | share of cluster posts containing the cluster's most common URL or media | 15 |
| amplification | min(1, repost+reply edges inside cluster / cluster posts) | 20 |

`coordination_score = round(Σ weight × signal)`. `first_posters`: earliest authors of `repost_of` targets or of near-duplicate groups (max 3). `top_amplifiers`: top 5 by reposts received + copies of their text. `detected_at`: timestamp of the 5th post that is in a near-duplicate group or burst window. Cluster ids K1, K2… by start time.

## 8. M3: Classification (`classify.py`)

- **Per cluster:** send Granite the 8 most representative posts (earliest + most copied + the latest 2) with post_ids.
- `ibm_watsonx_ai` `Credentials(url=WATSONX_URL, api_key=WATSONX_API_KEY)` + `ModelInference(model_id=WATSONX_MODEL_ID, project_id=WATSONX_PROJECT_ID)`, temperature 0, ~400 max tokens. `WATSONX_MODEL_ID` = a Granite instruct model available in our watsonx project (confirm the exact id in the project's model list).
- Prompt: label definitions, every output field, 4 short fictional few-shot examples (one per label, incl. benign cricket), then posts. **JSON only.** Robust parse: first `{...}` block, validate, clamp confidence. `evidence_quote` must be an exact substring of a provided post, else first 120 chars of the evidence post.
- `LLM_MODE`: `granite` | `rules` | `auto` (default: cache → Granite with 10 s timeout → rules on any error). Cache key = sha256 of sorted post_ids + task name, file `sample_data/llm_cache.json`.
- **Rules fallback** (must classify C1, C2, C3, D1 correctly on its own). Shared lexicons live in `classify.py` and are reused by M5:
  - `MOBILIZE`: pahuncho, ikattha, jama ho, chalo, niklo, gather, assemble, एकत्र, पहुंचो
  - `HOSTILE`: jawab dena, sabak, chup nahi baithenge, consequences, we know where, delete your report, बदला
  - `SHARE`: share karo, forward karo, sabko batao, viral karo, RT, spread
  - `ALARM/FALSE`: crack, chhupa raha, hiding, evacuate, shehar chhodo, breaking, sach
  - time regex: `\b\d{1,2}\s?(baje|pm|am|बजे)\b`, weekday names (English + Hindi), `abhi|turant|aaj raat|kal`
  - place regex: `\b([A-Z][\w]*(?: [A-Z][\w]*)*) (chowk|maidan|gate|bazaar|market|station|bus stand|chauraha|office)\b` (case-insensitive fallback)
  - `call_to_action` = MOBILIZE hit AND (place or time).

## 9. M4: Legal mapping (`legal_kb.json`, `legal.py`)

Deterministic; **depends only on M2 + M3** (not on state). Each suggestion's reason cites evidence and lists `evidence_post_ids`.

| id | offence | BNS | old | suggest when |
|---|---|---|---|---|
| enmity | Promoting enmity between groups | 196 | IPC 153A | label incitement or misinformation AND target_type = group |
| integration | Imputations prejudicial to national integration | 197 | IPC 153B | incitement against a group AND false_claim |
| mischief | Statements conducing to public mischief | 353 | IPC 505 | misinformation; or incitement with call_to_action |
| abetment_public | Abetting offence by public / >10 persons | 57 | IPC 117 | call_to_action AND cluster > 10 accounts |
| conspiracy | Criminal conspiracy | 61 | IPC 120B | non-benign AND coordination_score ≥ 60 |
| intimidation | Criminal intimidation | 351 | IPC 503/506 | intimidation = true |
| defamation | Defamation | 356 | IPC 499/500 | harassment AND false_claim |
| evidence | Electronic-record certificate for evidence | BSA 63 | Evidence Act 65B | any non-benign (evidence handling note) |

Benign → `[]`. IT Act §79(3)(b), §69A and BNSS §163 are **actions**, so they live in M5's action ladder, not here.

## 10. M5: Threat correlation & campaign evolution (`correlation.py`)

`build_campaign_intel(df, clusters, classifications, legal, incidents, snapshot_time, previous=None) -> list[dict]` (schema 4.7). `previous` = the list M5 returned for an earlier snapshot, or None. All logic is rule-based and explainable. Granite is used only for the optional 2-sentence narrative summary (cached, with a template fallback).

**10.1 Narrative phase per post** (first match wins, lexicons from M3):
1. `MOBILIZATION`: MOBILIZE hit AND (place or time)
2. `INFLAMMATORY`: HOSTILE hit
3. `AMPLIFICATION`: `repost_of` set, OR SHARE hit, OR the post is a near-duplicate of an earlier post
4. `CLAIM`: everything else

Phases are listed in first-seen order. `path` joins them with " → ". Each phase keeps its count, an example quote and up to 5 evidence post_ids. Each first appearance of a new phase is a `NARRATIVE_SHIFT` timeline event.

**10.2 Propagation:** 10-min buckets from campaign start to end with the fields in 4.7. Amplifiers are the top 5 by reposts received + copies of their text. `potential_reach` = sum of followers of cluster accounts.

**10.3 Timeline events:** `FIRST_POST` (earliest post), `COORDINATION_BURST` (densest 10-min window start, from M2), `AMPLIFICATION` (first bucket where posts ≥ 2× previous bucket and ≥ 8 posts), `NARRATIVE_SHIFT` (10.1), `MOBILIZATION_SIGNAL` (first MOBILIZATION post), `OFFLINE_MATCH` (10.5), `STATE_CHANGE` (from 10.6). Sorted by time, each with evidence post_ids.

**10.4 What changed** (only when `previous` is given): match each current campaign to a previous one by account Jaccard ≥ 0.3. Unmatched = `is_new_campaign`. For matched campaigns, report new accounts (with each one's first post id), post count delta, new hashtags / URLs / media, new locations mentioned, label change, state change, and triggers that are newly fired.

**10.5 Online–offline correlation:**
- For each campaign, collect place mentions (place regex + `location_mentioned`) and time mentions. Parse time mentions to absolute datetimes with `parse_mentioned_time(text, ref_dt)`: weekday → next occurrence on/after the post date; "N baje" + shaam/raat → PM; `abhi/turant` → post time; `aaj raat` → 21:00 same day.
- Match against incidents: **HIGH** = place string matches incident location (case-insensitive, token overlap ≥ 1 non-generic word) AND incident time within −3 h … +6 h of the campaign's posts; **MEDIUM** = same district AND within ±6 h. Record `time_delta_min` (positive = incident after first post). Note if the incident happened *before* the campaign ("campaign references/distorts a real incident") or *after* ("possible offline outcome").
- `planned_event`: the latest parsed future datetime + place from MOBILIZATION posts, with `hours_from_snapshot`. This is the early-warning window.
- Correlation for a benign campaign is reported but never escalates the state.

**10.6 Campaign state: explicit triggers.** State = the highest state whose trigger fired. States 4–5 require a non-benign label. Benign campaigns are capped at COORDINATED.

| id | state | condition | fired_at |
|---|---|---|---|
| T1 | DETECTED | M2 cluster with ≥ 5 accounts | 5th post of the cluster |
| T2 | COORDINATED | coordination_score ≥ 60 AND ≥ 2 signals ≥ 0.5 | M2 `detected_at` |
| T3 | AMPLIFYING | (reposts + near-copies) ≥ 30% of posts AND a 10-min bucket with ≥ 2× the previous bucket's posts and ≥ 8 posts | start of that bucket |
| T4 | ESCALATING | label ≠ benign AND (≥ 3 INFLAMMATORY posts OR intimidation = true) | 3rd inflammatory post (or first intimidation post) |
| T5 | MOBILIZATION | label ≠ benign AND ≥ 3 distinct accounts post MOBILIZATION content naming a place and a time | post of the 3rd such account |

Every trigger (fired or not) is output with its condition, threshold, observed value and evidence post_ids. A HIGH offline match is shown as a **supporting flag**, not a trigger.

**10.7 Action ladder** (cumulative by state; every action cites its trigger id and evidence):
- DETECTED: keep monitoring the hashtags and accounts.
- COORDINATED: alert the district cyber cell; send a data-preservation request to the platform for the evidence posts.
- AMPLIFYING: takedown notice to the intermediary under IT Act §79(3)(b); publish a fact-check / counter-message from official handles.
- ESCALATING: request blocking under IT Act §69A through the designated officer; brief the district SP; consider an FIR under the suggested sections after legal review.
- MOBILIZATION: deploy police at `{place}` before `{time}`; for the district magistrate's consideration, a prohibitory order under BNSS §163 (formerly CrPC §144); coordinate with the district administration.

**10.8 Evidence index:** every post_id cited anywhere in the campaign → handle, timestamp, masked text, sha256 of `json.dumps(original_post, sort_keys=True, ensure_ascii=False, default=str)`.

## 11. M6: Threat brief (`brief.py`, `templates/brief.html`, `mcp_server.py`, `bob/threatlens-analyst.md`)

**Deterministic renderer:** `render_brief(intel: dict, analyst: str, analyst_assessment: str | None = None) -> (brief_id, html, path)`. Self-contained HTML (inline CSS, `@media print`, A4). Sections in order:
1. Header: Brief ID `TB-20260926-<campaign_id>-<HHMM IST>`, generated-at (IST), analyst, "RESTRICTED — FOR OFFICIAL USE".
2. BLUF (3 deterministic lines: what, where, current state + planned event countdown).
3. **Analyst assessment**: Bob's text if provided (labelled "Drafted by IBM Bob from campaign intelligence; reviewed by <analyst>"), otherwise a template paragraph.
4. Campaign state ladder (5 boxes, current highlighted) + trigger table.
5. Timeline. 6. Propagation (bucket table, first posters, amplifiers, reach). 7. Narrative evolution. 8. What changed. 9. Online–offline correlation + planned event. 10. Suggested legal sections + disclaimer. 11. Recommended actions. 12. Evidence table (post_id, handle, time, masked text, sha256; max 20 rows).
Footer: "Generated by ThreatLens. Human review required before any action." Saves to `src/outputs/<brief_id>.html`.

**Bob at runtime (load-bearing integration):** `mcp_server.py` uses the `mcp` Python SDK (`FastMCP`, stdio) and exposes:
- `list_campaigns(previous_cutoff: str = "2026-09-26T14:10", current_cutoff: str = "2026-09-26T23:59")` → id, label, state, main hashtag, planned event
- `get_campaign_intel(campaign_id)` → the full schema-4.7 dict
- `get_posts(post_ids: list[str])` → evidence rows
- `render_threat_brief(campaign_id, analyst, analyst_assessment)` → brief_id + file path

`bob/threatlens-analyst.md` holds instructions to paste into a Bob custom mode / rules: "Act as a police OSINT analyst. For any campaign: call get_campaign_intel, write a ≤150-word assessment that only states facts present in the intel, cite post_ids in brackets for every claim, never add legal sections that M4 did not suggest, never name real communities, then call render_threat_brief." `docs/bob-usage.md` documents both uses of Bob: building the code, and generating briefs at runtime.

## 12. Pipeline, evaluation, UI

**`pipeline.py`:** `run_snapshot(df, incidents, cutoff, llm_mode) -> {"clusters","classifications","legal"}` (M1–M4). `analyze(df, incidents, previous_cutoff, current_cutoff, llm_mode) -> {"campaigns": [...M5 intel...], "previous": [...], "timings": {...}, "generated_at": iso}` runs `run_snapshot` for both cutoffs, then M5 for the previous snapshot (no previous) and the current one (with previous). Campaigns are sorted by state order, then by post count. Defaults: previous `2026-09-26T14:10+05:30`, current `2026-09-26T23:59+05:30`.

**`evaluate.py`:** per answer-key campaign: account precision / recall / F1 (best-overlap cluster), predicted vs true label, predicted vs expected state, expected incidents found (yes/no), detection lag (min) = `detected_at − first campaign post`. Overall: mean F1, label accuracy, state accuracy, "D1 decoy not escalated".

**`app.py` (Streamlit, wide layout, title "ThreatLens — Coordinated Threat Early-Warning"):**
- Sidebar: data source (sample data / upload posts JSON or CSV + optional incidents JSON), **previous & current snapshot time sliders** (default 14:10 and 23:59), LLM mode, analyst name, **Run analysis**. Results live in `st.session_state`.
- KPI row: posts, accounts, campaigns, highest state (colour chip), nearest planned event countdown.
- Campaign table: id, hashtag, label, **state chip**, accounts, coordination score, "NEW" / "CHANGED" badge. A selectbox picks a campaign.
- Tabs for the selected campaign:
  1. **Overview**: BLUF, 5-step state ladder (current highlighted), trigger table (fired / not fired, observed vs threshold, evidence ids), coordination-score contribution bar.
  2. **Timeline & narrative**: Plotly posts-per-minute with event markers + vertical line at detected_at ("Detected T+X min"); phase strip coloured by narrative phase; phase table with example quotes.
  3. **Propagation**: cumulative accounts / posts line chart; pyvis network (first posters red and larger, amplifiers orange, others grey); amplifier table with reach.
  4. **What changed & offline**: what-changed cards (previous vs current); offline matches table; planned-event card with countdown.
  5. **Legal & actions**: legal suggestions with reasons + disclaimer; action ladder with the current state highlighted.
  6. **Evidence & brief**: evidence table with hashes; **Generate brief** (deterministic, optional analyst text box; paste Bob's assessment here if not using MCP) → HTML preview + download; Approve / Escalate / Dismiss buttons logging to an in-session action log.
- Expanders: "Evaluation vs answer key", "Safeguards & ethics".
- Colour chips: DETECTED grey, COORDINATED blue, AMPLIFYING yellow, ESCALATING orange, MOBILIZATION red. Never show a Python traceback: wrap failures in `st.error`.

## 13. Ethics & safeguards (README, docs, one slide)
Fictional data only; PII masked in all displays; no profiling by religion/caste/identity (we flag coordinated behaviour, not people or groups); every finding links to posts; states come from published, explicit triggers rather than a black-box score; a human must approve before any action; legal output is a suggestion; Bob's text may only restate facts in the intel and cites post_ids; the benign decoy test guards against false positives; SHA-256 hashes preserve chain of custody.

## 14. Team split and 4-hour timeline
| Time | P1 | P2 | P3 | P4 |
|---|---|---|---|---|
| 0:00–0:20 | Create repo from template, **Prompt 0** (skeleton + M1 + mock data), push | Get watsonx keys + model id | Pull, read PLAN.md | Fill `submission.yaml` team fields, start slide outline |
| 0:20–1:10 | **Prompt 1**: M2 | **Prompt 2**: M3 + M4 | **Prompt 3**: M5 (on fixtures) | **Prompt 5**: UI (on fixtures) |
| 1:10–2:00 | **Prompt 4**: M6 brief + MCP + Bob mode | Prompt 2 (cont.), then help P3 with tests | Prompt 3 (cont.) | Prompt 5 (cont.) |
| 2:00–2:40 | **Prompt 6: integration** (P1 drives, everyone runs the app) | | | |
| **2:40** | **Feature freeze** | | | |
| 2:40–3:20 | **Prompt 7**: hardening, warm Granite cache, commit it | Run Bob runtime demo via MCP, screenshot it | **Prompt 8**: docs + README + submission.yaml | Screenshots 01–05, slides → `presentation/slides.pdf` |
| 3:20–3:50 | Record 3–5 min demo video (screen + voice), upload unlisted, paste link | | | |
| 3:50–4:00 | Push, confirm **✅ Validate Submission** is green, repo Public, submit form | | | |

## 15. Demo script (3.5 min video)
1. (20 s) Problem: in 2020 and 2022 coordinated hashtag campaigns preceded communal violence; police had no early-warning tool.
2. (20 s) Load the sample batch, previous snapshot 14:10, current 23:59, Run → 4 campaigns, 2 in MOBILIZATION, the cricket decoy stays DETECTED.
3. (60 s) Open CMP for `#NandpurJaago`: state ladder and fired triggers with evidence → timeline + narrative path CLAIM → AMPLIFICATION → INFLAMMATORY → MOBILIZATION → **What changed since 14:10**: AMPLIFYING → MOBILIZATION, new location Ghanta Ghar chowk, +N accounts → offline match: the campaign distorts the real Keshav market incident → **planned event Sunday 17:00, ~X h away**.
4. (30 s) `#NandpurDamAlert`: online rumour → offline panic at Nandpur bus stand 20 min later (INC-02).
5. (40 s) **Bob in action:** in Bob, "Generate a threat brief for CMP-1" → Bob calls the ThreatLens MCP tools → writes a cited assessment → brief rendered. Open it and print to PDF.
6. (20 s) Evaluation table (F1, state accuracy, detection lag) + safeguards. End with 5 s of the Bob build sessions.
