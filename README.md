# ThreatLens — Coordinated Threat Early-Warning Engine

> IBM Bob AI Hackathon · Problem 06 · Team ThreatLens

ThreatLens detects coordinated social-media campaigns that may precede offline communal incidents, classifies the threat level using IBM Granite (watsonx.ai), and generates analyst briefs through IBM Bob MCP tools — all from a simple Streamlit interface with no database required.

---

## 👥 Team

| Field | Value |
|---|---|
| **Team Name** | ThreatLens |
| **Track** | AI |
| **Team Lead** | Apoorva Karambelkar — apoorvaknk@gmail.com |
| **Members** | Moksh Jain, Saksham Jain |

---

## Demo

| | |
|---|---|
| **Demo video** | `demo/demo-video-link.txt` |
| **Live demo** | `demo/live-demo-url.txt` (local — see setup guide) |
| **Screenshots** | `demo/screenshots/` |
| **Presentation** | `presentation/ThreatLens_TBSM4L.pptx` |

---

## Problem

In 2020 and 2022, coordinated hashtag campaigns on social media preceded communal violence in several Indian districts. Police and district administrations had no early-warning tool to distinguish organic discourse from coordinated escalation campaigns in time to intervene. ThreatLens addresses this gap.

---

## Solution

Six chained modules process a batch of social-media posts:

| # | Module | What it does |
|---|---|---|
| M1 | Ingest & normalise | Clean DataFrame, PII-masked text |
| M2 | Coordination detection | Clusters accounts acting together; scores coordination |
| M3 | Threat classification | IBM Granite (watsonx.ai) with rules fallback |
| M4 | Legal mapping | Suggests BNS / IPC sections with evidence citations |
| M5 | Campaign evolution | Timeline, narrative phases, online–offline correlation, campaign state |
| M6 | Threat brief | HTML brief; IBM Bob writes the analyst assessment via MCP |

**Campaign states:** `DETECTED → COORDINATED → AMPLIFYING → ESCALATING → MOBILIZATION`

Each state transition is driven by explicit, auditable triggers — never a black-box score.

---

## IBM Bob Integration (load-bearing)

Bob is used in **two distinct, load-bearing ways**:

1. **Building the code** — every module in `src/threatlens/` was designed and written through IBM Bob during the hackathon (see `BOB_PROMPTS.md`).

2. **Analyst assessment at runtime** — Bob connects to `src/mcp_server.py` over MCP (stdio transport) and calls `get_campaign_intel` → `render_threat_brief` to write a cited, evidence-grounded analyst assessment directly into the HTML brief. The assessment may only state facts present in the campaign intelligence and must cite `post_id`s for every claim. See `docs/bob-usage.md` and `src/bob/threatlens-analyst.md`.

---

## Quick start

```bash
git clone https://github.com/moksh-nfsu/IBM_project.git
cd IBM_project/src
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Optional: edit .env with watsonx credentials (not required — cache works offline)

streamlit run app.py
```

Then open http://localhost:8501, click **Run analysis**, and explore.

For full setup instructions see `docs/setup-guide.md`.

---

## Repository layout

```
<repo root>
├── README.md               ← this file
├── PLAN.md                 ← engineering spec (single source of truth)
├── BOB_PROMPTS.md          ← Bob prompts used to build the project
├── submission.yaml         ← hackathon submission metadata
├── CONTRIBUTING.md
├── .gitignore
├── .github/             ← CI validation (template) + unit tests
├── docs/
│   ├── problem-statement.md
│   ├── solution-overview.md
│   ├── architecture.md
│   ├── setup-guide.md
│   └── bob-usage.md
├── demo/
│   ├── demo-video-link.txt
│   ├── live-demo-url.txt
│   └── screenshots/
│       ├── 01-dashboard.png
│       ├── 02-timeline.png
│       └── 03-brief.png
├── presentation/
│   └── ThreatLens_TBSM4L.pptx
└── src/                    ← all code here (see src/README.md)
```

---

## Ethics & safeguards

- All data is **fictional**: districts, communities, people, URLs (`.example` domain only).
- PII is masked (`[PHONE]`, `[EMAIL]`) in every display.
- States come from published, explicit triggers — not a black-box score.
- Every finding links to evidence posts with SHA-256 hashes (chain of custody).
- A human must approve before any action is taken.
- Legal output carries "Suggested — requires legal officer review".
- The benign cricket-celebration decoy (`D1 / #IndiaWins`) validates the system does not over-flag.

---

## Judging criteria

| Criterion | Notes |
|---|---|
| Technical quality (25 pts) | M1–M6 pipeline, tests, typed code |
| Innovation (25 pts) | Explicit trigger model, narrative phase detection, online–offline correlation |
| Problem depth (15 pts) | Real scenario grounding, BNS legal mapping |
| Working demo (15 pts) | Runs locally, offline-capable with warmed LLM cache |
| IBM Bob integration (10 pts) | Load-bearing MCP runtime + Bob-built codebase |
| Docs & reproducibility (10 pts) | This README, `docs/`, `src/README.md`, tests |
