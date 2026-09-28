# Solution Overview

## What ThreatLens does

ThreatLens is a **coordinated threat early-warning engine** that processes a batch of social-media posts and produces:

- A set of **campaign clusters** — groups of accounts acting together
- A **classification** of each cluster (incitement / harassment / misinformation / benign)
- **BNS legal section suggestions** with evidence citations
- A **campaign state** on a five-level ladder with explicit, auditable triggers
- A **narrative evolution path** (CLAIM → AMPLIFICATION → INFLAMMATORY → MOBILIZATION)
- An **online–offline correlation** against a police incident log
- A **planned-event warning** with place, time, and countdown
- A **printable HTML brief** written partly by IBM Bob

## Key design decisions

### Explicit trigger model (no black-box score)

Campaign state is determined by five explicit triggers (T1–T5). Each trigger has a named condition, a threshold, an observed value, and evidence post IDs. Analysts can audit exactly why a campaign reached MOBILIZATION. There is no opaque "risk score".

### Narrative phase detection

Each post is classified into one of four narrative phases (CLAIM, AMPLIFICATION, INFLAMMATORY, MOBILIZATION) using lexicons defined in `classify.py`. The *path* a campaign takes (e.g., CLAIM → AMPLIFICATION → MOBILIZATION — skipping INFLAMMATORY) tells an analyst different things about the campaign's origin and intent.

### Online–offline correlation

The system extracts place and time mentions from posts, parses them to absolute datetimes (handling "shaam 5 baje", weekday names, "abhi/turant"), and cross-references them against offline police-log incidents. A HIGH match requires token overlap on location *and* time proximity (−3 h … +6 h). This surfaces both "campaign distorts a real incident" and "possible offline outcome".

### Offline-capable LLM

`LLM_MODE=auto` tries: (1) a committed LLM cache keyed by SHA-256 of post IDs, (2) IBM Granite on watsonx.ai, (3) deterministic rules fallback. Judges can see real Granite outputs without API keys.

### Benign decoy validation

Campaign D1 (`#IndiaWins`, cricket celebration) tests that the system does not escalate organic activity. It is capped at COORDINATED regardless of coordination score because the label is "benign".

## Module summary

```
M1  schema.py / ingest.py       Clean DataFrame, PII masking, snapshot
M2  coordination.py             Account graph, 4 edge types, 5 signals, clusters
M3  classify.py                 Granite classification + rules fallback + cache
M4  legal.py                    8 BNS sections, deterministic, evidence-cited
M5  correlation.py              Campaign state, triggers, timeline, narrative,
                                propagation, what changed, offline correlation
M6  brief.py + mcp_server.py    HTML brief; Bob writes analyst assessment via MCP
```

## IBM Bob integration

Bob is used at two levels:

1. **Build-time**: Every module was designed and written through IBM Bob (see `BOB_PROMPTS.md`).
2. **Runtime**: Bob connects via MCP (stdio), calls `get_campaign_intel` to read the full campaign intelligence, writes a ≤150-word evidence-grounded analyst assessment citing post IDs, then calls `render_threat_brief` to embed it in the HTML brief.

The assessment is labelled "Drafted by IBM Bob from campaign intelligence; reviewed by `<analyst>`" in the brief.
