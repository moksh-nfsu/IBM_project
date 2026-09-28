# Presentation

The slide deck (`ThreatLens_TBSM4L.pptx`) covers:

1. **Problem** — coordinated social-media campaigns preceding offline communal incidents; no early-warning tool exists.
2. **Solution** — ThreatLens: 6-module pipeline, explicit trigger model, IBM Granite + IBM Bob integration.
3. **Architecture** — M1→M6 data flow, MCP server, offline-capable LLM cache.
4. **Demo** — sample run: 4 campaigns, 2 in MOBILIZATION, cricket decoy stays DETECTED.
5. **IBM Bob integration** — build-time (every module written through Bob) + runtime (MCP tools, analyst assessment).
6. **Evaluation** — Mean account F1 = 1.00, label accuracy 100%, state accuracy 100%, 0 false-alarm campaigns, mean detection lag ~10 min, D1 decoy not escalated (rules mode, sample data).
7. **Ethics & safeguards** — fictional data, PII masking, explicit triggers, human approval required.
8. **Limitations & future work** — real social-media API integration, multi-language NLP, live streaming mode.

