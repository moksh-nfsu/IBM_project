# Setup Guide

## Requirements

- Python 3.10 or newer (tested on 3.11 and 3.13)
- No database, no Docker, no cloud account required for basic use
- Optional: IBM watsonx.ai credentials for live Granite classification (a warmed LLM cache is committed, so the demo runs without keys)

---

## 1. Clone the repository

```bash
git clone https://github.com/moksh-nfsu/IBM_project.git
cd IBM_project
```

---

## 2. Create a virtual environment

```bash
cd src
python -m venv .venv
```

Activate it:

**Windows (PowerShell)**
```powershell
.venv\Scripts\Activate.ps1
```

**macOS / Linux**
```bash
source .venv/bin/activate
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

The `requirements.txt` contains:
```
streamlit pandas numpy scikit-learn networkx plotly pyvis jinja2 python-dotenv ibm-watsonx-ai mcp pytest
```

---

## 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
# Required only for live Granite classification
WATSONX_API_KEY=your-api-key-here
WATSONX_PROJECT_ID=your-project-id-here
WATSONX_URL=https://eu-de.ml.cloud.ibm.com
WATSONX_MODEL_ID=ibm/granite-3-8b-instruct

# LLM mode: auto | granite | rules
# auto = try LLM cache → Granite → rules fallback
# rules = fully offline, no API calls
LLM_MODE=auto
```

> **Tip:** Leave `LLM_MODE=auto` (the default). The committed `llm_cache.json` already contains warmed Granite outputs for all five sample clusters, so the full demo runs offline with no credentials.

---

## 5. Run the Streamlit app

```bash
# Make sure you are in src/
streamlit run app.py
```

Open http://localhost:8501 in your browser.

**Default workflow:**
1. Leave "Sample data" selected in the sidebar.
2. Set previous snapshot to `14:10` and current snapshot to `23:59` (the defaults).
3. Click **Run analysis**.
4. Four campaigns appear. Select `#NandpurJaago` (CMP-1) to explore the MOBILIZATION campaign.

---

## 6. Run tests

```bash
# From src/
pytest tests/ -v
```

Expected: **32 tests pass** in ~3 seconds.

---

## 7. Regenerate mock data (optional)

The committed `posts.json`, `offline_incidents.json`, and `answer_key.json` are already present. To regenerate them (seed 42, 500 posts):

```bash
# From src/
python -m threatlens.sample_data.generate_mock
```

---

## 8. Run the MCP server (for Bob integration)

```bash
# From src/
python mcp_server.py
```

The server speaks MCP over stdio. Register it in Bob's MCP settings:

```json
{
  "mcpServers": {
    "threatlens": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "<absolute-path-to-repo>/src"
    }
  }
}
```

See `docs/bob-usage.md` for full Bob integration instructions.

---

## 9. Running fully offline

Set `LLM_MODE=rules` in `.env` (or in the sidebar) to bypass all network calls. All 32 tests also run offline:

```bash
LLM_MODE=rules pytest tests/ -v
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: threatlens` | Run from `src/` not the repo root |
| Streamlit shows a Python traceback | Check the sidebar — set LLM mode to `rules` |
| `ibm_watsonx_ai` import error | `pip install ibm-watsonx-ai` (or use `LLM_MODE=rules`) |
| Granite timeout | The app automatically falls back to rules; increase `WATSONX_TIMEOUT` in classify.py if needed |
| pyvis graph not rendering | Ensure the browser allows `<iframe>` srcdoc; try Chrome |
