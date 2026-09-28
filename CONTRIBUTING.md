# Contributing to ThreatLens

Thank you for your interest in ThreatLens! This project was built for the IBM Bob AI Hackathon (Problem 06).

## Ground rules

- **All code lives in `src/`.** The top-level template files (`README.md`, `submission.yaml`, `CONTRIBUTING.md`, `docs/`, `demo/`, `presentation/`, `.github/`) must not be deleted or renamed.
- **Never edit `.github/workflows/validate.yml`.**
- **Never create a folder named `data/`** — the `.gitignore` ignores it. Sample files belong in `src/threatlens/sample_data/`.
- All data must remain fictional. No real PII, no real communities, no slurs.
- `LLM_MODE=rules` must work fully offline (no watsonx credentials required).

## Development setup

```bash
cd src
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # macOS / Linux
pip install -r requirements.txt
cp .env.example .env
```

## Running the app

```bash
cd src
streamlit run app.py
```

## Running tests

```bash
cd src
pytest tests/ -v
```

All 32 tests must pass before opening a pull request.

## Code style

- Python 3.10+. Type hints on all public functions.
- Simple, readable code. No extra libraries beyond `src/requirements.txt`.
- Follow the schemas in `PLAN.md` section 4 exactly — do not change field names or types without updating all modules.

## Module boundaries

| Module | File | Contract |
|---|---|---|
| M1 | `schema.py`, `ingest.py` | DataFrame schema per PLAN.md 4.1 |
| M2 | `coordination.py` | Cluster schema per PLAN.md 4.4 |
| M3 | `classify.py` | Classification schema per PLAN.md 4.5 |
| M4 | `legal.py` | Legal schema per PLAN.md 4.6 |
| M5 | `correlation.py` | Campaign intel schema per PLAN.md 4.7 |
| M6 | `brief.py` | HTML brief + `render_brief` signature |

## Submitting changes

1. Branch from `main`.
2. Keep commits small and scoped to one module.
3. Run `pytest tests/ -v` and ensure all tests pass.
4. Open a pull request with a brief description of what changed and why.
