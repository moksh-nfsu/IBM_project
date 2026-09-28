"""Generate mock sample data for ThreatLens (PLAN.md section 6).

Running this module writes three files next to it:
- ``posts.json``             (~500 posts, all on 2026-09-26 IST)
- ``offline_incidents.json`` (mock police control-room log)
- ``answer_key.json``        (ground truth for evaluate.py)

Usage (from src/)::

    python -m threatlens.sample_data.generate_mock

Seed 42. Everything is fictional: districts, communities, people, URLs (.example).

Design notes
------------
* Background posts are organic: every account writes its own sentences
  (built from slots, so two accounts never post the same text), organic
  replies/reposts only happen inside small friend circles of 3 accounts, and
  media files are personal photos. This keeps the background below every
  coordination threshold, so any cluster M2 finds is a real campaign.
* Campaign posts reuse 3-4 templates per phase with small word swaps, so they
  are near-copies (similar, not identical), as coordinated campaigns are.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))
_SEED = 42
_HERE = Path(__file__).parent.resolve()
_DAY = datetime(2026, 9, 26, tzinfo=_IST)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _at(hh: int, mm: int, ss: int = 0) -> datetime:
    return _DAY.replace(hour=hh, minute=mm, second=ss)


def _between(rng: random.Random, start: tuple[int, int], end: tuple[int, int]) -> datetime:
    """Random timestamp between two HH:MM times on the mock day."""
    a, b = _at(*start), _at(*end)
    return a + timedelta(seconds=rng.randint(0, int((b - a).total_seconds())))


def _old_created(rng: random.Random, min_years: float, max_years: float) -> str:
    days = int(rng.uniform(min_years, max_years) * 365)
    return (_at(9, 0) - timedelta(days=days)).isoformat()


def _fresh_created(rng: random.Random) -> str:
    """Burner account created 2026-09-23 .. 2026-09-25."""
    day = datetime(2026, 9, rng.randint(23, 25), tzinfo=_IST)
    return day.replace(hour=rng.randint(6, 23), minute=rng.randint(0, 59)).isoformat()


def _swap(text: str, rng: random.Random, swaps: dict[str, list[str]]) -> str:
    """Replace some phrases with synonyms. Swaps never remove lexicon words."""
    for word, alternatives in swaps.items():
        if word in text and rng.random() < 0.6:
            text = text.replace(word, rng.choice(alternatives), 1)
    return text


class _Ids:
    """Sequential post / account id allocator."""

    def __init__(self) -> None:
        self.post = 0
        self.account = 0

    def next_post(self) -> str:
        self.post += 1
        return f"P{self.post:04d}"

    def next_account(self) -> str:
        self.account += 1
        return f"A{self.account:04d}"


def _account(ids: _Ids, handle: str, created: str, followers: int,
             district: str, platform: str) -> dict:
    return {"account_id": ids.next_account(), "handle": handle,
            "account_created_at": created, "followers": followers,
            "district": district, "platform": platform}


def _post(ids: _Ids, acc: dict, text: str, ts: datetime, lang: str, *,
          hashtags=None, mentions=None, urls=None, media=None,
          reply_to=None, repost_of=None) -> dict:
    return {
        "post_id": ids.next_post(),
        "account_id": acc["account_id"],
        "handle": acc["handle"],
        "account_created_at": acc["account_created_at"],
        "followers": acc["followers"],
        "text": text,
        "lang": lang,
        "timestamp": ts.isoformat(),
        "hashtags": list(hashtags or []),
        "mentions": list(mentions or []),
        "urls": list(urls or []),
        "media": list(media or []),
        "reply_to": reply_to,
        "repost_of": repost_of,
        "district": acc["district"],
        "platform": acc["platform"],
    }


# ---------------------------------------------------------------------------
# Background (~370 posts, ~150 accounts)
# ---------------------------------------------------------------------------

_DISTRICTS = ["Nandpur", "Sitavali", "Keshavnagar", "Ambarpur", "Rudrakot"]
_PLATFORMS = ["X", "Instagram", "Facebook"]
_BG_HANDLE_WORDS = [
    "chai", "cricket", "foodie", "musafir", "desi", "kitaab", "filmy", "techie",
    "shayar", "rasoi", "ghumakkad", "yatri", "mausam", "bazaar", "gully",
    "sports", "photo", "cycle", "garden", "news",
]
_BG_HANDLE_SUFFIX = ["wala", "lover", "diaries", "adda", "talks", "vibes", "junction", "corner", "life", "notes"]

# Organic topics. Each is (lang, template, slot values). Slots make every
# account's sentence different.
_BG_TOPICS: list[tuple[str, str, dict[str, list[str]]]] = [
    ("en", "Traffic near {place} is {state} this {when}, {advice}.",
     {"state": ["crawling", "surprisingly light", "a total mess", "moving slowly"],
      "when": ["morning", "afternoon", "evening"],
      "advice": ["take the ring road", "leave ten minutes early", "avoid the flyover", "maybe walk instead"]}),
    ("hinglish", "{district} mein aaj {food} khaya, {verdict}!",
     {"food": ["kachori", "pav bhaji", "chole bhature", "masala dosa", "jalebi", "momos", "biryani"],
      "verdict": ["ekdum mast tha", "thoda teekha tha", "paisa vasool", "phir se jaana padega"]}),
    ("en", "{team} looked {form} in the {match}. {opinion}",
     {"team": ["Our district XI", "The college team", "Rudrakot Royals", "Sitavali Strikers"],
      "form": ["sharp", "rusty", "unstoppable", "nervous"],
      "match": ["practice game", "league opener", "local final", "friendly"],
      "opinion": ["Bowling needs work.", "Great fielding though.", "Openers were brilliant.", "Next week will be better."]}),
    ("hi", "{district} में आज {weather}, {advice}।",
     {"weather": ["हल्की बारिश हुई", "बहुत गर्मी है", "ठंडी हवा चल रही है", "धूप निकली है"],
      "advice": ["छाता साथ रखें", "पानी पीते रहें", "शाम को घूमना अच्छा रहेगा", "बच्चों का ध्यान रखें"]}),
    ("en", "Water supply in {district} {zone} will be {status} {when}.",
     {"zone": ["east zone", "ward 4", "old town", "sector 9"],
      "status": ["off for repairs", "restored", "reduced", "on a new schedule"],
      "when": ["tomorrow morning", "from Monday", "till evening", "this weekend"]}),
    ("hinglish", "Kal {movie} dekhi, {review}. {rating}",
     {"movie": ["nayi action film", "woh family drama", "animated movie", "purani classic"],
      "review": ["story kamzor thi", "music bahut accha tha", "interval ke baad boring", "acting zabardast"],
      "rating": ["3/5.", "Ek baar dekh sakte ho.", "Skip karo.", "Must watch!"]}),
    ("en", "Proud of {who} from {district} for {achievement}.",
     {"who": ["a young painter", "our school team", "a local nurse", "the chess club"],
      "achievement": ["winning a state award", "the clean-ward drive", "organising a blood camp", "topping the board exams"]}),
    ("hi", "{district} के बाज़ार में {item} के दाम {trend}।",
     {"item": ["टमाटर", "प्याज़", "दूध", "दाल"],
      "trend": ["फिर बढ़ गए", "थोड़े कम हुए", "स्थिर हैं", "आसमान छू रहे हैं"]}),
    ("en", "The new {facility} in {district} is {verdict}.",
     {"facility": ["library", "park", "bus shelter", "health centre", "sports ground"],
      "verdict": ["finally open", "beautifully done", "already crowded", "still unfinished"]}),
    ("hinglish", "Aaj {activity} kiya, {feeling}.",
     {"activity": ["subah ki cycling", "ghar ki safai", "naya recipe try", "purane doston se video call"],
      "feeling": ["mood fresh ho gaya", "thak gaya yaar", "bahut maza aaya", "weekend sorted"]}),
    ("en", "Municipal notice for {district}: {notice}.",
     {"notice": ["property tax camp on Friday", "road repair near the old gate next week",
                 "free eye check-up at the town hall", "new garbage pickup timings"]}),
    ("hinglish", "{district} ke {place} pe {event} ho raha hai, {invite}.",
     {"event": ["book fair", "food festival", "craft mela", "music night"],
      "invite": ["family ke saath jaana", "entry free hai", "stalls dekhne layak", "photos baad mein daalunga"]}),
]
_BG_PLACES = ["the old bus depot", "the railway crossing", "the main square", "the college road",
              "the river bridge", "the civil lines area", "the fruit market lane"]
_BG_TAGS = ["#NandpurLocal", "#SitavaliNews", "#KeshavnagarUpdates", "#AmbarpurVibes",
            "#RudrakotLife", "#Cricket2026", "#WeatherUpdate", "#LocalNews", "#FoodTales", "#WeekendMood"]
_BG_PII = [  # demonstrates M1 masking; fictional numbers / example addresses
    "Tiffin service now open in {district}, call 9876501234 for the menu.",
    "Lost a black wallet near the post office in {district}. If found please email finder.help@mail.example",
    "Tuition classes for class 10 maths in {district}, WhatsApp +91 9123405678.",
]


_BG_TAILS = [
    "Anyone else noticed?", "Kya kehte ho?", "Good day overall.", "Chalo, dekhte hain.",
    "Will post photos later.", "Thoda ajeeb laga.", "Sunday plans sorted.", "Bas itna hi.",
    "Kaafi time baad aisa hua.", "Happy with that.", "Mummy ne bhi yahi kaha.", "Office ke baad jaunga.",
    "Weekend hai toh chalta hai.", "Pata nahi kab badlega.", "Bachpan yaad aa gaya.", "Can't complain.",
]
_SIM_LIMIT = 0.70          # stricter than M2's 0.80, for margin
_MAX_ORGANIC_GROUP = 3     # organic similar-text groups never reach M2's 5-account minimum


def _bg_sentence(rng: random.Random, district: str) -> tuple[str, str]:
    lang, tpl, slots = rng.choice(_BG_TOPICS)
    values = {k: rng.choice(v) for k, v in slots.items()}
    values["district"] = district
    values["place"] = rng.choice(_BG_PLACES)
    text = tpl.format(**values)
    if rng.random() < 0.6:
        text += " " + rng.choice(_BG_TAILS)
    return lang, text


class _OrganicGuard:
    """Rejects background sentences that would let ordinary accounts look coordinated.

    Background accounts may post similar things (that happens organically), but a
    group of accounts linked by similar text is capped at 3, below M2's 5-account
    cluster minimum. Similarity uses the same char_wb TF-IDF as M2.
    """

    def __init__(self, pool: list[str]) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit(pool)
        self.rows = []          # accepted vectors
        self.owners: list[str] = []
        self.parent: dict[str, str] = {}

    def _find(self, a: str) -> str:
        self.parent.setdefault(a, a)
        while self.parent[a] != a:
            a = self.parent[a]
        return a

    def _size(self, root: str) -> int:
        return sum(1 for a in self.parent if self._find(a) == root)

    def link(self, a: str, b: str) -> None:
        self.parent[self._find(a)] = self._find(b)

    def accept(self, account_id: str, text: str) -> bool:
        from scipy.sparse import vstack
        v = self.vec.transform([text])
        linked = set()
        if self.rows:
            sims = (vstack(self.rows) @ v.T).toarray().ravel()
            linked = {self.owners[i] for i in range(len(sims))
                      if sims[i] >= _SIM_LIMIT and self.owners[i] != account_id}
        roots = {self._find(a) for a in linked} | {self._find(account_id)}
        if sum(self._size(r) for r in roots) > _MAX_ORGANIC_GROUP:
            return False
        for a in linked:
            self.link(account_id, a)
        self.rows.append(v)
        self.owners.append(account_id)
        return True


def _make_background(rng: random.Random, ids: _Ids) -> list[dict]:
    accounts = []
    for _ in range(150):
        handle = f"{rng.choice(_BG_HANDLE_WORDS)}_{rng.choice(_BG_HANDLE_SUFFIX)}"
        if rng.random() < 0.5:
            handle += f"_{rng.choice(['nd', 'sv', 'kn', 'ap', 'rk'])}"
        accounts.append(_account(ids, handle, _old_created(rng, 1, 6), rng.randint(50, 20000),
                                 rng.choice(_DISTRICTS), rng.choice(_PLATFORMS)))
    # Handles must be unique: append a letter on collision.
    seen: dict[str, int] = {}
    for a in accounts:
        n = seen.get(a["handle"], 0)
        seen[a["handle"]] = n + 1
        if n:
            a["handle"] += "abcdefghij"[n % 10]

    # Friend circles of 3 (organic replies / reposts happen only inside a circle).
    circles = [accounts[i:i + 3] for i in range(0, 60, 3)]
    guard = _OrganicGuard([_bg_sentence(random.Random(i), d)[1] for i in range(2000) for d in _DISTRICTS[:1]])
    for circle in circles:
        for other in circle[1:]:
            guard.link(circle[0]["account_id"], other["account_id"])

    posts: list[dict] = []
    for acc in accounts:
        for _ in range(rng.choice([1, 2, 2, 3, 3, 4])):
            for _attempt in range(200):
                lang, text = _bg_sentence(rng, acc["district"])
                if guard.accept(acc["account_id"], text):
                    break
            else:
                continue  # could not find a sufficiently different sentence; skip this post
            ts = _between(rng, (6, 0), (23, 50))
            media = [f"media/{acc['handle']}_{rng.randint(1, 99)}.jpg"] if rng.random() < 0.12 else []
            tags = rng.sample(_BG_TAGS, rng.choice([0, 0, 1, 1, 2]))
            posts.append(_post(ids, acc, text, ts, lang, hashtags=tags, media=media))

    # A few posts with phone numbers / emails (PII masking demo).
    for tpl in _BG_PII:
        acc = rng.choice(accounts)
        posts.append(_post(ids, acc, tpl.format(district=acc["district"]),
                           _between(rng, (9, 0), (20, 0)), "en"))

    # Organic replies / reposts inside friend circles of 3 accounts (max component = 3).
    by_account: dict[str, list[dict]] = {}
    for p in posts:
        by_account.setdefault(p["account_id"], []).append(p)
    replies = ["Bilkul sahi baat!", "Agreed, same here.", "Thanks for sharing this.",
               "Haha, true.", "Where exactly?", "Nice one!"]
    for circle in circles:
        a, b = rng.sample(circle, 2)
        if a["account_id"] not in by_account:
            continue
        target = rng.choice(by_account[a["account_id"]])
        t0 = datetime.fromisoformat(target["timestamp"])
        ts = min(t0 + timedelta(minutes=rng.randint(3, 90)), _at(23, 55))
        if rng.random() < 0.7:
            reply = rng.choice(replies)
            if guard.accept(b["account_id"], reply):
                posts.append(_post(ids, b, reply, ts, "en", reply_to=target["post_id"]))
        else:
            posts.append(_post(ids, b, target["text"], ts, target["lang"],
                               hashtags=target["hashtags"], repost_of=target["post_id"]))
    return posts


# ---------------------------------------------------------------------------
# C1 Incitement  #NandpurJaago  (25 fresh accounts, ~45 posts, 13:50-14:40)
# ---------------------------------------------------------------------------

C1_TAG = "#NandpurJaago"
C1_URL = "https://nandpur-jaago.example/call"
C1_MEDIA = "media/c1_poster_a.jpg"

_C1_CLAIM = [
    "Keshav market mein Community B ke logon ne dukaanein todi, police chup hai. Yeh kab tak chalega? #NandpurJaago",
    "Keshav market mein aaj Community B ke logon ne kai dukaanein tod di aur police chup baithi hai. #NandpurJaago",
    "Suna hai Keshav market ki dukaanein Community B walon ne todi hain, prashasan kuch nahi bol raha. #NandpurJaago",
]
_C1_AMPL = [
    "Share karo, sabko batao! Keshav market mein dukaanein todi gayi aur police chup hai. #NandpurJaago",
    "Sabko batao, share karo! Keshav market ki dukaanein todi gayi, koi action nahi hua. #NandpurJaago",
    "Share karo sab log, sabko batao ki Keshav market mein kya hua, media chup hai. #NandpurJaago",
    "Yeh khabar sabko batao, share karo jaldi! Keshav market ki dukaanein toot gayi. #NandpurJaago",
]
_C1_AMPL_SWAPS = {"sab log": ["bhaiyon", "doston"], "jaldi": ["abhi ke abhi", "turant"],
                  "media chup hai": ["TV wale chup hain", "koi nahi dikha raha"]}
_C1_INFL = [
    "Ab chup nahi baithenge! Community B ko jawab dena padega. #NandpurJaago",
    "Bahut ho gaya, ab chup nahi baithenge. Community B ko jawab dena padega. #NandpurJaago",
    "Community B ko sabak sikhana padega, ab chup nahi baithenge! #NandpurJaago",
    "Hum ab chup nahi baithenge, Community B ko iska jawab dena padega. #NandpurJaago",
]
_C1_INFL_SWAPS = {"Bahut ho gaya": ["Hadd ho gayi", "Sehan nahi hoga"], "Hum ab": ["Hum log ab", "Ab hum"]}
_C1_MOB = [
    "Sunday shaam 5 baje Ghanta Ghar chowk pahuncho, sab ikattha ho! #NandpurJaago",
    "Sab log Sunday shaam 5 baje Ghanta Ghar chowk pahuncho, ikattha ho jao! #NandpurJaago",
    "Sunday shaam 5 baje sab Ghanta Ghar chowk pahuncho. Ek saath ikattha ho! #NandpurJaago",
    "Yaad rakho: Sunday shaam 5 baje Ghanta Ghar chowk pahuncho, sab ikattha ho. #NandpurJaago",
]
_C1_MOB_SWAPS = {"Sab log": ["Sabhi bhai", "Saare saathi"], "Yaad rakho": ["Bhoolna mat", "Note karo"]}


def _make_c1(rng: random.Random, ids: _Ids) -> tuple[list[dict], dict[str, str]]:
    accounts = [_account(ids, f"veer_{rng.randint(1000, 9999)}", _fresh_created(rng),
                         rng.randint(5, 59), "Keshavnagar", rng.choice(["X", "Facebook"]))
                for _ in range(25)]
    posts: list[dict] = []
    phase: dict[str, str] = {}

    def add(acc, text, ts, ph, **kw):
        p = _post(ids, acc, text, ts, "hinglish", hashtags=[C1_TAG], **kw)
        posts.append(p)
        phase[p["post_id"]] = ph
        return p

    # CLAIM 13:50-13:58, 2 seed accounts (3 posts)
    seeds = accounts[:2]
    claims = [add(seeds[0], _C1_CLAIM[0], _at(13, 50, 12), "CLAIM", media=[C1_MEDIA]),
              add(seeds[1], _C1_CLAIM[1], _at(13, 53, 40), "CLAIM", media=[C1_MEDIA]),
              add(seeds[0], _C1_CLAIM[2], _at(13, 57, 5), "CLAIM", media=[C1_MEDIA])]

    # AMPLIFICATION 14:00-14:12, 12 accounts: 6 reposts of the seeds + 10 near-copies
    ampl_accs = accounts[2:14]
    for i, acc in enumerate(ampl_accs[:6]):
        orig = claims[i % len(claims)]
        add(acc, orig["text"], _between(rng, (14, 0), (14, 6)), "AMPLIFICATION",
            media=[C1_MEDIA], repost_of=orig["post_id"])
    for i in range(10):
        acc = ampl_accs[(i + 6) % len(ampl_accs)]
        text = _swap(_C1_AMPL[i % len(_C1_AMPL)], rng, _C1_AMPL_SWAPS)
        add(acc, text, _between(rng, (14, 1), (14, 11)), "AMPLIFICATION",
            media=[C1_MEDIA] if rng.random() < 0.8 else [])

    # INFLAMMATORY 14:12-14:25, 8 accounts (10 posts)
    infl_accs = accounts[14:22]
    for i in range(10):
        text = _swap(_C1_INFL[i % len(_C1_INFL)], rng, _C1_INFL_SWAPS)
        add(infl_accs[i % len(infl_accs)], text, _between(rng, (14, 12), (14, 24)), "INFLAMMATORY")

    # MOBILIZATION 14:25-14:40, 10 accounts (12 posts): seeds, 5 inflammatory, 3 new
    mob_accs = seeds + infl_accs[:5] + accounts[22:25]
    for i in range(12):
        text = _swap(_C1_MOB[i % len(_C1_MOB)], rng, _C1_MOB_SWAPS)
        add(mob_accs[i % len(mob_accs)], text, _between(rng, (14, 25), (14, 40)), "MOBILIZATION",
            urls=[C1_URL], media=[C1_MEDIA])
    return posts, phase


# ---------------------------------------------------------------------------
# C2 Harassment  #ExposeMeera  (15 fresh accounts, ~30 posts, 16:00-16:40)
# ---------------------------------------------------------------------------

C2_TAG = "#ExposeMeera"
C2_TARGET = "@meera_reports"
C2_MEDIA = "media/c2_edited_screenshot.jpg"

_C2_CLAIM = [
    "@meera_reports ki report fake hai, paid journalist hai yeh. #ExposeMeera",
    "@meera_reports ki poori report fake hai, sab jaante hain paid journalist hai. #ExposeMeera",
    "Her report is fake, @meera_reports is a paid journalist. #ExposeMeera",
]
_C2_AMPL = [
    "Share karo! @meera_reports ki fake report sabko batao, paid journalist hai. #ExposeMeera",
    "Sabko batao aur share karo, @meera_reports ki report fake hai. #ExposeMeera",
    "Share karo yeh thread, @meera_reports paid journalist hai, sabko batao. #ExposeMeera",
]
_C2_INTIM = [
    "@meera_reports we know where you work. Delete your report or face consequences. #ExposeMeera",
    "@meera_reports we know where your office is. Delete your report or face consequences. #ExposeMeera",
    "We know where you work @meera_reports, delete your report or face the consequences. #ExposeMeera",
]
_C2_SWAPS = {"paid journalist": ["bika hua journalist", "paid reporter"], "yeh thread": ["yeh post", "yeh screenshot"]}


def _make_c2(rng: random.Random, ids: _Ids) -> tuple[list[dict], dict[str, str]]:
    accounts = [_account(ids, f"sach_{rng.randint(100, 9999)}", _fresh_created(rng),
                         rng.randint(3, 60), rng.choice(["Nandpur", "Sitavali"]), "X")
                for _ in range(15)]
    posts: list[dict] = []
    phase: dict[str, str] = {}

    def add(acc, text, ts, ph, lang="hinglish", **kw):
        p = _post(ids, acc, text, ts, lang, hashtags=[C2_TAG], mentions=[C2_TARGET], **kw)
        posts.append(p)
        phase[p["post_id"]] = ph
        return p

    # CLAIM 16:00-16:08 (3 accounts, 4 posts)
    claims = [add(accounts[0], _C2_CLAIM[0], _at(16, 0, 30), "CLAIM", media=[C2_MEDIA]),
              add(accounts[1], _C2_CLAIM[1], _at(16, 3, 10), "CLAIM", media=[C2_MEDIA]),
              add(accounts[2], _C2_CLAIM[2], _at(16, 5, 45), "CLAIM", "en", media=[C2_MEDIA]),
              add(accounts[0], _swap(_C2_CLAIM[1], rng, _C2_SWAPS), _at(16, 7, 55), "CLAIM", media=[C2_MEDIA])]

    # AMPLIFICATION 16:08-16:22 (10 accounts, 14 posts: 5 reposts + 9 near-copies)
    ampl_accs = accounts[3:13]
    for i in range(5):
        orig = claims[i % 3]
        add(ampl_accs[i], orig["text"], _between(rng, (16, 8), (16, 14)), "AMPLIFICATION",
            media=[C2_MEDIA], repost_of=orig["post_id"])
    for i in range(9):
        add(ampl_accs[(i + 5) % len(ampl_accs)], _swap(_C2_AMPL[i % 3], rng, _C2_SWAPS),
            _between(rng, (16, 10), (16, 22)), "AMPLIFICATION", media=[C2_MEDIA] if rng.random() < 0.7 else [])

    # INTIMIDATION 16:22-16:40 (7 accounts, 12 posts) - no place+time call to action
    intim_accs = accounts[8:15]
    for i in range(12):
        add(intim_accs[i % len(intim_accs)], _C2_INTIM[i % 3],
            _between(rng, (16, 22), (16, 40)), "INFLAMMATORY", "en")
    return posts, phase


# ---------------------------------------------------------------------------
# C3 Misinformation  #NandpurDamAlert  (20 accounts, ~35 posts, 18:30-19:10)
# ---------------------------------------------------------------------------

C3_TAG = "#NandpurDamAlert"
C3_URL = "https://nandpur-alert.example/dam"
C3_MEDIA = "media/c3_dam_crack.jpg"

_C3_CLAIM = [
    "Nandpur dam mein crack aa gaya hai, prashasan chhupa raha hai! #NandpurDamAlert",
    "Nandpur dam mein bada crack hai aur prashasan yeh baat chhupa raha hai. #NandpurDamAlert",
    "Breaking: Nandpur dam mein crack, prashasan sach chhupa raha hai! #NandpurDamAlert",
]
_C3_AMPL = [
    "Forward karo! Nandpur dam mein crack hai, prashasan chhupa raha hai. #NandpurDamAlert",
    "Sab forward karo, Nandpur dam ka crack prashasan chhupa raha hai! #NandpurDamAlert",
    "Forward karo sabko, Nandpur dam mein crack hai, parivaar ko batao. #NandpurDamAlert",
]
_C3_MOB = [
    "Abhi Nandpur bus stand pahuncho, raat 8 baje se pehle shehar chhodo! #NandpurDamAlert",
    "Sab abhi Nandpur bus stand pahuncho aur raat 8 baje se pehle shehar chhodo! #NandpurDamAlert",
    "Turant Nandpur bus stand pahuncho, raat 8 baje se pehle shehar chhodo. #NandpurDamAlert",
]
_C3_SWAPS = {"parivaar ko batao": ["ghar walon ko batao", "padosiyon ko batao"], "Sab abhi": ["Sab log abhi", "Abhi sab"]}


def _make_c3(rng: random.Random, ids: _Ids) -> tuple[list[dict], dict[str, str]]:
    accounts = []
    for i in range(20):
        if i < 12:
            accounts.append(_account(ids, f"alert_{rng.randint(100, 9999)}", _fresh_created(rng),
                                     rng.randint(5, 80), "Nandpur", rng.choice(["X", "Facebook"])))
        else:  # older, genuinely worried accounts that got pulled in
            accounts.append(_account(ids, f"nandpur_{rng.choice(['mom', 'teacher', 'dost', 'kisan'])}_{rng.randint(1, 99)}",
                                     _old_created(rng, 0.5, 3), rng.randint(150, 5000), "Nandpur",
                                     rng.choice(_PLATFORMS)))
    posts: list[dict] = []
    phase: dict[str, str] = {}

    def add(acc, text, ts, ph, **kw):
        p = _post(ids, acc, text, ts, "hinglish", hashtags=[C3_TAG], **kw)
        posts.append(p)
        phase[p["post_id"]] = ph
        return p

    # CLAIM 18:30-18:38 (3 accounts)
    claims = [add(accounts[i], _C3_CLAIM[i], _at(18, 30 + 3 * i, 20), "CLAIM",
                  urls=[C3_URL], media=[C3_MEDIA]) for i in range(3)]
    # AMPLIFICATION 18:38-18:55 (14 accounts, 20 posts: 7 reposts + 13 near-copies)
    ampl_accs = accounts[3:17]
    for i in range(7):
        orig = claims[i % 3]
        add(ampl_accs[i], orig["text"], _between(rng, (18, 38), (18, 46)), "AMPLIFICATION",
            urls=[C3_URL], media=[C3_MEDIA], repost_of=orig["post_id"])
    for i in range(13):
        add(ampl_accs[(i + 7) % len(ampl_accs)], _swap(_C3_AMPL[i % 3], rng, _C3_SWAPS),
            _between(rng, (18, 40), (18, 55)), "AMPLIFICATION",
            urls=[C3_URL] if rng.random() < 0.6 else [], media=[C3_MEDIA] if rng.random() < 0.6 else [])
    # MOBILIZATION 18:55-19:10 (6 accounts, 10 posts)
    mob_accs = accounts[:2] + accounts[16:20]
    for i in range(10):
        add(mob_accs[i % len(mob_accs)], _swap(_C3_MOB[i % 3], rng, _C3_SWAPS),
            _between(rng, (18, 55), (19, 10)), "MOBILIZATION", urls=[C3_URL])
    return posts, phase


# ---------------------------------------------------------------------------
# D1 Benign decoy  #IndiaWins  (25 old accounts, 21:00-21:20)
# ---------------------------------------------------------------------------

_D1_TEXTS = [
    "What a match! India smashed it tonight #IndiaWins",
    "Team India ne kya jadoo dikhaya, historic jeet! #IndiaWins",
    "Best squad in years, no doubt about it. #IndiaWins",
    "Every single player gave 100 percent today #IndiaWins",
    "Celebrating with the whole mohalla, so proud #IndiaWins",
    "Yaar kya batting thi, last over mein chhakke! #IndiaWins",
    "The stadium went wild, goosebumps all over #IndiaWins",
    "Finally a trophy! Waited so long for this #IndiaWins #Cricket",
    "Bowlers deserve all the credit for this one #IndiaWins",
    "Poora desh aaj ek saath khush hai #IndiaWins",
    "Cricket is not a game here, it is an emotion #IndiaWins",
    "Congratulations Team India, you made a billion people smile #IndiaWins",
    "मेरी तरफ से टीम इंडिया को ढेरों बधाई! #IndiaWins",
    "Unbelievable finish, my heart is still racing #IndiaWins",
    "Whole family glued to the TV till the end #IndiaWins",
    "History made tonight, kids will remember this forever #IndiaWins",
    "Jab India jeetta hai toh sab dost ek ho jaate hain #IndiaWins",
    "Best sporting moment of 2026 for sure #IndiaWins",
    "That catch at deep midwicket was pure magic #IndiaWins",
    "Watching with college friends, the celebration was epic #IndiaWins",
    "आज की जीत कभी नहीं भूलेंगे #IndiaWins",
    "Such a clinical chase, world beaters #IndiaWins",
    "Raat bhar celebration chalega aaj #IndiaWins",
    "True champions, nothing more to say #IndiaWins",
    "Fireworks lighting up the sky in Ambarpur tonight #IndiaWins",
]


def _make_d1(rng: random.Random, ids: _Ids) -> tuple[list[dict], dict[str, str]]:
    posts, phase = [], {}
    for text in _D1_TEXTS:
        acc = _account(ids, f"cricket_{rng.choice(['premi', 'junoon', 'dil', 'fan'])}_{rng.randint(10, 99)}",
                       _old_created(rng, 1, 5), rng.randint(500, 50000),
                       rng.choice(["Nandpur", "Sitavali", "Ambarpur", "Rudrakot"]), rng.choice(["X", "Instagram"]))
        tags = ["#IndiaWins"] if "#Cricket" not in text else ["#IndiaWins", "#Cricket"]
        p = _post(ids, acc, text, _between(rng, (21, 0), (21, 20)), rng.choice(["en", "hinglish"]), hashtags=tags)
        posts.append(p)
        phase[p["post_id"]] = "CLAIM"
    return posts, phase


# ---------------------------------------------------------------------------
# S1 Individual (non-coordinated) violations - one account, one post each
# ---------------------------------------------------------------------------

# (handle, followers, district, time, text, expected categories). All names and numbers fictional.
_INDIVIDUAL = [
    ("rakshak_7781", 12, "Nandpur", (11, 20),
     "Yeh hai us reporter ka ghar ka pata: 14 Lake View Colony, Nandpur, number 9876543210. "
     "Sab jaake milo isse aur sabak sikhao.", ["doxxing_stalking", "criminal_intimidation"]),
    ("nandpur_police_help", 40, "Nandpur", (12, 5),
     "OFFICIAL NOTICE: Nandpur Police verification ke liye apna Aadhaar OTP is number pe bhejein 9123456780, "
     "warna aapka account block hoga.", ["impersonation_fraud"]),
    ("gussa_kisan_12", 230, "Sitavali", (15, 30),
     "Collector saab, agar kal tak Sitavali road nahi bani toh aapka office jala denge, yaad rakhna.",
     ["criminal_intimidation"]),
    ("sehat_alert_24", 18, "Ambarpur", (17, 10),
     "Ambarpur civil hospital ka paani zeher hai, 50 bachche mar gaye aur sarkar chhupa rahi hai! "
     "Forward karo sabko.", ["misinformation"]),
    ("dilwala_x9", 7, "Rudrakot", (20, 15),
     "@priya_sings tu kal stage pe dikhi toh dekh lena, har jagah tera peecha karenge, bach ke rehna.",
     ["criminal_intimidation", "doxxing_stalking"]),
    ("sach_bolo_44", 25, "Keshavnagar", (22, 40),
     "Community A ke tyohaar bakwaas hain, unki aastha ka mazaak udao sab log.", ["religious_insult"]),
]


def _make_individual(rng: random.Random, ids: _Ids) -> tuple[list[dict], dict[str, list[str]]]:
    posts, expected = [], {}
    for handle, followers, district, (hh, mm), text, cats in _INDIVIDUAL:
        acc = _account(ids, handle, _fresh_created(rng) if followers < 50 else _old_created(rng, 1, 3),
                       followers, district, rng.choice(_PLATFORMS))
        mentions = [w for w in text.split() if w.startswith("@")]
        p = _post(ids, acc, text, _at(hh, mm, rng.randint(0, 59)), "hinglish", mentions=mentions)
        posts.append(p)
        expected[p["post_id"]] = cats
    return posts, expected


def _sample_100(all_posts: list[dict], groups: dict, individual: list[dict], rng: random.Random) -> list[dict]:
    """100-post sample: every phase of every campaign, the individual violations, organic background."""
    chosen: list[dict] = list(individual)
    quota = {"C1": 26, "C2": 16, "C3": 18, "D1": 12}
    for g, n in quota.items():
        posts, phase = groups[g]
        by_phase: dict[str, list[dict]] = {}
        for p in posts:
            by_phase.setdefault(phase.get(p["post_id"], "CLAIM"), []).append(p)
        picked = []
        for ph_posts in by_phase.values():  # proportional per phase, earliest posts kept
            k = max(2, round(n * len(ph_posts) / len(posts)))
            picked += ph_posts[:k]
        chosen += picked[:n]
    ids = {p["post_id"] for p in chosen}
    background = [p for p in all_posts if p["post_id"] not in ids and p["post_id"] not in
                  {q["post_id"] for posts, _ in groups.values() for q in posts}]
    pii = [p for p in background if "[" not in p["text"] and ("@mail" in p["text"] or "98765" in p["text"]
                                                             or "91234" in p["text"])]
    rest = [p for p in background if p not in pii and not p["reply_to"] and not p["repost_of"]]
    chosen += pii + rng.sample(rest, 100 - len(chosen) - len(pii))
    return sorted(chosen, key=lambda p: (p["timestamp"], p["post_id"]))


# ---------------------------------------------------------------------------
# Offline incidents (mock police control-room log)
# ---------------------------------------------------------------------------

_INCIDENTS = [
    {"incident_id": "INC-01", "reported_at": _at(12, 40).isoformat(), "district": "Keshavnagar",
     "location": "Keshav market", "category": "clash",
     "description": "Minor dispute between two shopkeepers, 2 injured, situation controlled",
     "source": "Mock police control-room log"},
    {"incident_id": "INC-02", "reported_at": _at(19, 25).isoformat(), "district": "Nandpur",
     "location": "Nandpur bus stand", "category": "panic",
     "description": "Large crowd and traffic jam at the bus stand; people trying to leave after a dam rumour; normalised after police announcement",
     "source": "Mock police control-room log"},
    {"incident_id": "INC-04", "reported_at": _at(10, 15).isoformat(), "district": "Sitavali",
     "location": "Sitavali highway", "category": "accident",
     "description": "Two-vehicle road accident, 1 minor injury",
     "source": "Mock police control-room log"},
    {"incident_id": "INC-05", "reported_at": _at(21, 35).isoformat(), "district": "Ambarpur",
     "location": "Ambarpur central ground", "category": "celebration",
     "description": "Celebration crowd after the cricket win, no law-and-order issue",
     "source": "Mock police control-room log"},
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate(out_dir: Path | None = None) -> dict:
    """Write posts.json, offline_incidents.json and answer_key.json; return counts."""
    rng = random.Random(_SEED)
    out_dir = out_dir or _HERE
    ids = _Ids()

    background = _make_background(rng, ids)
    groups = {"C1": _make_c1(rng, ids), "C2": _make_c2(rng, ids),
              "C3": _make_c3(rng, ids), "D1": _make_d1(rng, ids)}

    individual, expected_individual = _make_individual(rng, ids)

    all_posts = background + individual + [p for posts, _ in groups.values() for p in posts]
    all_posts.sort(key=lambda p: (p["timestamp"], p["post_id"]))
    sample = _sample_100(all_posts, groups, individual, rng)

    meta = {
        "C1": ("incitement", "MOBILIZATION", ["INC-01"]),
        "C2": ("harassment", "ESCALATING", []),
        "C3": ("misinformation", "MOBILIZATION", ["INC-02"]),
        "D1": ("benign", "DETECTED", ["INC-05"]),
    }
    answer_key = {}
    for g, (posts, phase) in groups.items():
        label, state, incs = meta[g]
        answer_key[g] = {
            "type": label,
            "account_ids": list(dict.fromkeys(p["account_id"] for p in posts)),
            "post_ids": [p["post_id"] for p in posts],
            "expected_state": state,
            "expected_incidents": incs,
            "phases": phase if g != "D1" else {},
        }

    def dump(name: str, obj) -> Path:
        path = out_dir / name
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    answer_key["S1"] = {"type": "individual", "account_ids": [p["account_id"] for p in individual],
                        "post_ids": [p["post_id"] for p in individual], "expected_state": None,
                        "expected_incidents": [], "expected_categories": expected_individual}
    written = [dump("posts.json", all_posts), dump("offline_incidents.json", _INCIDENTS),
               dump("answer_key.json", answer_key), dump("sample_100_posts.json", sample)]
    csv_path = out_dir / "sample_100_posts.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        import csv
        w = csv.DictWriter(fh, fieldnames=list(sample[0]))
        w.writeheader()
        for p in sample:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else ("" if v is None else v)
                        for k, v in p.items()})
    written.append(csv_path)

    counts = {"total": len(all_posts), "background": len(background)}
    print(f"Total posts: {len(all_posts)} | background: {len(background)} "
          f"from {len({p['account_id'] for p in background})} accounts")
    for g, (posts, phase) in groups.items():
        per_phase: dict[str, int] = {}
        for ph in phase.values():
            per_phase[ph] = per_phase.get(ph, 0) + 1
        counts[g] = len(posts)
        print(f"  {g} {meta[g][0]:<14} {len(posts):>3} posts, "
              f"{len(answer_key[g]['account_ids']):>2} accounts  phases: {per_phase if g != 'D1' else '-'}")
    for path in written:
        print(f"Written: {path}")
    return counts


if __name__ == "__main__":
    generate()
