# Devgarh test dataset (fictional)

An upload test that the app has never seen: a different district, a different date (Mon 5 Oct 2026)
and a different format (an X/Twitter-style export, UTC timestamps).

| File | What |
|---|---|
| `devgarh_posts.csv` | 64 posts. Columns: `tweet_id, screen_name, user_id, full_text, created_at, followers_count, user_created_at, retweeted_status_id, in_reply_to_status_id, source` |
| `devgarh_incidents.csv` | 3 offline incidents (optional upload) |
| `make_devgarh.py` | regenerates both files |

Everything is invented: people, handles, phone numbers, "Community X / Y", and the `.example` URLs.

## How to test
App → **Upload JSON / CSV** → choose `devgarh_posts.csv` (and `devgarh_incidents.csv`) → **Analyse**.

## What you should see (checked with IBM Bob)

**22 ordinary posts, none flagged.** These include deliberate traps: "we are going to destroy them tonight"
(cricket), "MLA ne ek road nahi banayi, vote soch ke dena" (lawful criticism), a news report of an arrest
for online threats, and a peaceful candle march at a named place and time.

**Campaign #DevgarhJago** (14 new accounts, 10:02–10:40):
- The state reaches **MOBILIZATION**, and the narrative runs CLAIM → AMPLIFICATION → INFLAMMATORY → MOBILIZATION.
- Planned gathering: **Purana Qila gate, Tue 6 Oct 10:00**, about 13.7 h after the snapshot.
- It matches incident DG-01 (temple-road clash): the campaign distorts a real incident.
- Sections: BNS 196, 353, 192, 189, 57, 352.

**Campaign #DevgarhPaniAlert** (8 accounts, fake water-poisoning rumour):
- Labelled misinformation, **BNS 353**, and linked to DG-02, the Civil Hospital panic.
- Its state stays at DETECTED. Half of its accounts are old and it has no place + time call, so the
  coordination triggers don't fire.

**Six standalone violations:**
| Handle | Expected |
|---|---|
| @sbi_care_helpdesk | fake bank KYC / OTP → BNS 319, IT Act 66C, 66D |
| @devgarh_police_official | fake police challan link → BNS 319, IT Act 66C, 66D |
| @bhola_gussa | threat to a doctor → BNS 351 |
| @expose_karo_dg | a girl's number and route posted + "sabak sikhao" → BNS 78, 79, 351 |
| @dukaan_rival | "milawati atta, chor hai" about a named shop → BNS 356 |
| @troll_king_dg | mocking Community Y's faith → BNS 299, 196 |
