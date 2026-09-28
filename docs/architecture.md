# Architecture

## Component diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Analyst laptop / server  (no cloud required)               │
│                                                             │
│  ┌─────────────────────┐      ┌──────────────────────────┐  │
│  │  Streamlit UI        │      │  IBM Bob (MCP client)    │  │
│  │  app.py             │      │  threatlens-analyst mode │  │
│  └────────┬────────────┘      └──────────┬───────────────┘  │
│           │  run_snapshot / analyze       │  stdio MCP       │
│           ▼                              ▼                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                 pipeline.py                            │ │
│  │  M1 ingest → M2 cluster → M3 classify → M4 legal       │ │
│  │              → M5 correlate → M6 brief                 │ │
│  └────────────────────────┬───────────────────────────────┘ │
│                           │                                  │
│           ┌───────────────┼───────────────┐                  │
│           ▼               ▼               ▼                  │
│  ┌──────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │ sample_data/ │ │ llm_cache   │ │ outputs/ (briefs)   │   │
│  │ posts.json   │ │ .json       │ │ TB-*.html           │   │
│  │ incidents    │ └─────────────┘ └─────────────────────┘   │
│  │ answer_key   │                                           │
│  └──────────────┘                                           │
│                                                             │
│  Optional (if API key set):                                 │
│  ┌───────────────────────────────┐                          │
│  │  IBM watsonx.ai               │                          │
│  │  Granite instruct model       │                          │
│  │  (classify_cluster, M5 narr.) │                          │
│  └───────────────────────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

## Data flow

```
posts.json / uploaded CSV
        │
        ▼
 M1: load_posts → normalize → snapshot(df, cutoff)
        │ clean DataFrame (500 rows, PII-masked)
        ▼
 M2: build_clusters(df)
        │ list of clusters (schema 4.4)
        ▼
 M3: classify_cluster(cluster, df, mode="auto")
        │ LLM cache hit?  yes → return cached
        │ no → try Granite (10s timeout)
        │ fail → rules fallback
        │ classification (schema 4.5)
        ▼
 M4: map_sections(cluster, classification)
        │ list of legal suggestions (schema 4.6)
        ▼
 M5: build_campaign_intel(df, clusters, classifications, legal, incidents, t)
        │ campaign intelligence list (schema 4.7)
        │  • narrative phases (CLAIM/AMPLIFICATION/INFLAMMATORY/MOBILIZATION)
        │  • propagation buckets
        │  • timeline events
        │  • what changed vs previous snapshot
        │  • online–offline correlation
        │  • campaign state via T1–T5 triggers
        │  • action ladder
        │  • evidence index (handle, text, sha256)
        ▼
 M6: render_brief(intel, analyst, analyst_assessment)
        │ self-contained HTML (12 sections, inline CSS, @media print)
        │ saved to src/outputs/TB-<id>-<HHMM>.html
        ▼
 MCP: Bob reads intel → writes ≤150-word cited assessment → embeds in brief
```

## File map

| Path | Purpose |
|---|---|
| `src/app.py` | Streamlit UI — calls pipeline, renders tabs |
| `src/mcp_server.py` | MCP server (FastMCP, stdio) — 4 tools for Bob |
| `src/threatlens/schema.py` | M1: load_posts, load_incidents |
| `src/threatlens/ingest.py` | M1: normalize, snapshot |
| `src/threatlens/coordination.py` | M2: build_clusters, score_cluster |
| `src/threatlens/classify.py` | M3: classify_cluster, lexicons, regexes |
| `src/threatlens/legal.py` | M4: map_sections |
| `src/threatlens/correlation.py` | M5: build_campaign_intel, parse_mentioned_time |
| `src/threatlens/brief.py` | M6: render_brief |
| `src/threatlens/pipeline.py` | run_snapshot, analyze (orchestration) |
| `src/threatlens/evaluate.py` | evaluate (F1, state accuracy, detection lag) |
| `src/threatlens/paths.py` | pathlib constants (PKG_DIR, SAMPLE_DATA, etc.) |
| `src/threatlens/sample_data/` | Mock posts, incidents, answer key, LLM cache |
| `src/bob/threatlens-analyst.md` | Bob custom-mode instructions |
| `src/templates/brief.html` | Jinja2 brief template |
| `src/outputs/` | Generated HTML briefs |
| `src/tests/` | 32 pytest tests |

## Key design properties

- **In-memory only**: pandas DataFrames. No database, no Docker.
- **Offline-capable**: committed `llm_cache.json` means judges see Granite outputs without API keys.
- **Reproducible**: `random.seed(42)` in `generate_mock.py`, deterministic M4, deterministic M5 triggers.
- **Auditable**: every state transition cites evidence post IDs and SHA-256 hashes.
- **Path-independent**: all paths built with `pathlib` relative to the package — `cd src && pytest` and `cd src && streamlit run app.py` both work.
