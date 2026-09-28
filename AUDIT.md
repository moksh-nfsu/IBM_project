# ThreatLens code audit (28 Sep 2026)

The first version was built quickly from `BOB_PROMPTS.md` by several parallel sessions. Its 32 tests passed,
but several of them had been loosened, and the app produced wrong results. This file lists what was
wrong and what changed. All fixes keep the PLAN.md section 4 schemas; new keys were only added.

## Results before and after (rules mode, default cutoffs 14:10 → 23:59)

| | Before | After |
|---|---|---|
| Campaigns found | 5, one of them a false alarm of 140 ordinary accounts | 4, one per real group |
| C2 harassment accounts found | 5 of 15 | 15 of 15 |
| State accuracy | 0.75 (C2 ended COORDINATED, not ESCALATING) | 1.00 |
| Mean account F1 | 0.853 | 1.00 |
| C1 narrative path | AMPLIFICATION → INFLAMMATORY → MOBILIZATION (CLAIM lost) | CLAIM → AMPLIFICATION → INFLAMMATORY → MOBILIZATION |
| C1 planned-event place | "baje Ghanta Ghar chowk" | "Ghanta Ghar chowk", Sun 27 Sep 17:00 |
| C1 "what changed" | no state change, no new location | AMPLIFYING → MOBILIZATION, new location, +11 accounts |
| Detection lag | always null | ~10 min |
| Tests | 32, with state accuracy untested, F1 ≥ 0.70, empty evidence allowed | 53, strict |

## Findings

### Data (`generate_mock.py`)
1. **Background posts reused 25 fixed sentences**, so unrelated accounts posted identical text and formed
   one false "coordinated" cluster of 140 accounts. Random background reposts and replies also chained
   accounts together. *Fix:* background text is built from slots and checked with the same TF-IDF
   similarity as M2; similar-text groups among ordinary accounts are capped at 3 accounts, and replies and
   reposts stay inside friend circles of 3. The background can no longer look coordinated.
2. C1 had 25 accounts in the answer key, but only 22 of them ever posted (recall capped at 0.88). The C1
   templates also mixed "Sunday" with "Aaj shaam" (two different gathering times), and a word swap
   replaced "chup nahi baithenge" with a phrase outside the lexicon. *Fixed.*
3. C2's intimidation posts were not connected to the rest of the campaign, so M2 saw only 5 accounts.
   *Fixed:* a single connected campaign of ~30 posts.
4. C3's mobilization templates used words outside the lexicon ("jaiye"), and "WhatsApp_forward" was not
   a valid platform value. *Fixed.*
5. PII masking was never exercised: no post contained a phone number or email. *Added 3 such posts.*

### M3 classify
6. **`llm_cache.json` held fake "Granite" results.** The entries were rules output labelled
   `"source": "granite"`: same rationale strings, and garbage places like "NandpurProblems Just had the
   best biryani…". No Granite call had ever succeeded. *Reset to `{}`.* Warm it with real keys before
   submitting.
7. Lexicons matched substrings: "RT" matched inside "party", and "kal" matched inside "nikal".
   *Fixed:* matching now uses word boundaries that also work for Devanagari.
8. PLACE_RE was case-insensitive, so it swallowed any preceding words ("baje Ghanta Ghar chowk").
   *Fixed:* 1–3 capitalised words plus a place keyword, with sentence-start and time words stripped.
9. The 10 s Granite "timeout" only measured time after the call had returned. *Fixed:* real thread
   timeout, and after one failure Granite is skipped for the rest of the session, so the demo never
   stalls. Also added: `.env` loading, the chat API with a `generate_text` fallback, stricter JSON
   validation, and the default model id `granite-13b-instruct-v2` (withdrawn) replaced.
10. Harassment intimidation was never detected for C2, so T4 could not fire. *Fixed* via data + lexicon.

### M4 legal
11. Every section cited the cluster's first 5 posts as evidence, whatever the rule. *Fixed:* each
    section cites the posts that satisfy its own rule, and the reason states real counts.

### M5 correlation
12. **Inverted near-duplicate test:** the *first* post of every copy group was tagged AMPLIFICATION.
    That is why C1 lost its CLAIM phase.
13. **`what_changed` never reported a state change:** it read `classification["_state"]`, which never
    exists. New locations, new media and newly fired triggers were missing too, and most items had
    empty evidence (a test explicitly allowed that).
14. T5 accepted place **or** time; PLAN requires place **and** time. T1 fired at `detected_at` instead of
    the 5th post.
15. Offline matching: evidence was arbitrary; OFFLINE_MATCH events were stamped at campaign start
    instead of incident time; MEDIUM matches fired on the posting accounts' home district alone. That
    linked the harassment campaign to the bus-stand panic. *Now:* the district must be named in the
    posts.
16. The planned-event parser returned "abhi" (now) for "abhi … raat 8 baje se pehle" and could not
    read "raat 8".
17. **Evidence SHA-256 covered only 5 re-formatted fields**, so the hash could not be checked against
    the original post. *Fixed:* the hash covers the full original record; a test recomputes it from
    `posts.json`.
18. Amplifier `reposts_received` and `copies_of_their_text` were the same number. Actions cited
    arbitrary posts instead of their trigger's evidence.

### M6, MCP, UI
19. `templates/brief.html` did not exist (the brief was hand-built f-strings). *Now a Jinja2 template*
    with autoescaping. Bob's text was previously inserted into the HTML unescaped.
20. The MCP server ignored the cutoffs Bob passed. It also crashes on the installed `mcp` 2.x, where
    FastMCP was renamed. *Fixed for both.*
21. UI: coordination scores and the contribution chart were never filled in. The network graph had no
    edges or first posters (the data was missing). Uploaded JSON skipped datetime parsing. Sliders
    showed raw minute counts. One error path printed a traceback, and the start screen loaded an
    external placeholder image. *All fixed.* The app now runs the sample analysis on first load.

## What the numbers do and do not show

The dataset is synthetic and built to exercise every rule, so perfect scores show that the pipeline
implements PLAN.md correctly. They do not show real-world accuracy. Honest limitations to state to
judges:

- The lexicons are tuned to this data, and Hinglish coverage is small.
- The thresholds (0.80 similarity, ≥ 60 score, ≥ 3 accounts) are untested on real traffic.
- Place extraction depends on capitalised place names.
- The coordination signals can be gamed by patient actors who use aged accounts and paraphrase.
- The analysis is one batch rather than a live stream.

## Still to do by the team
- Put real watsonx keys in `src/.env`, confirm `WATSONX_MODEL_ID`, and run the app once in `granite` mode.
  Then commit `llm_cache.json`: it must contain real Granite output before the docs claim it does.
- Register `src/mcp_server.py` in Bob and record the runtime brief flow (docs/bob-usage.md).
- Re-take the screenshots in `demo/screenshots/`; the current ones predate these fixes.

## Update (28 Sep 2026, v2): dynamic analysis with IBM Bob

- **Any upload.** JSON/CSV with only a `text` column. Common export columns are mapped, and inferred
  fields are shown (`schema.py`).
- **IBM Bob replaces Granite** as the reasoning engine (`bob_client.py`, `violations.py`). Every post
  gets violation types, severity, target, place/time, and BNS / IT Act sections, each with a "how it
  violates" explanation. Bob can only cite the 23 catalogue sections and sees their official text;
  other citations are rejected.
- **Legal KB from the official PDFs** (`law/`): all 358 BNS sections and 125 IT Act sections,
  verbatim, with page numbers. IT Act §66A is blocked.
- **Campaign labels and legal mapping** are now aggregated from the per-post results.
- **UI rebuilt.** Deploy and developer menus removed. New views: Overview, Violations (why each post
  violates, with the statute text), Campaigns, Legal reference, Data & sources.
- **100-post sample** (`sample_100_posts.json` / `.csv`) with six standalone violations: doxxing,
  OTP impersonation, a threat to an official, a health rumour, stalking, and a religious insult.
- **Results (Bob):** 4/4 campaigns and 6/6 standalone violations found, 0 of 387 ordinary posts
  flagged, 100 % label and state accuracy.
- **Security:** Bob Shell pre-approves tools in headless mode, so it runs in ask mode with every tool
  group disabled, in an empty temporary workspace, with the prompt on stdin. The API key lives only in
  the git-ignored `src/.env`.
