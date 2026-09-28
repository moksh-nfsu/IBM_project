"""M3: Threat classification (PLAN.md section 8), driven by IBM Bob's post-level analysis.

Each post is analysed once by IBM Bob (see violations.py). A campaign's label is then aggregated
from its posts' violation categories, so the campaign view and the per-post legal mapping always
agree. If no post-level analysis is available, a deterministic lexicon classifier is used.

The lexicons, regexes and text helpers here are shared with M4, M5 and the rules fallback.
"""
from __future__ import annotations

import logging
import re
from collections import Counter

import pandas as pd


log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared lexicons (PLAN.md section 8). Matched on word boundaries, case-insensitive.
# ---------------------------------------------------------------------------

MOBILIZE: list[str] = ["pahuncho", "ikattha", "jama ho", "chalo", "niklo", "gather", "assemble",
                       "एकत्र", "पहुंचो", "पहुँचो"]
HOSTILE: list[str] = ["jawab dena", "sabak", "chup nahi baithenge", "consequences", "we know where",
                      "delete your report", "बदला"]
SHARE: list[str] = ["share karo", "forward karo", "sabko batao", "viral karo", "RT", "spread"]
ALARM: list[str] = ["crack", "chhupa raha", "hiding", "evacuate", "shehar chhodo", "breaking", "sach chhupa"]
INTIMIDATE: list[str] = ["we know where", "delete your report", "face consequences",
                         "face the consequences", "warna"]
FALSE_CLAIM: list[str] = ["fake", "paid journalist", "jhooth", "chhupa raha", "police chup",
                          "media chup", "koi action nahi", "sach chhupa"]

_WEEKDAYS_EN = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WEEKDAYS_HI = ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]

# Word boundary that also works for Devanagari (vowel signs are not \w in Python).
_L = r"(?<![\wऀ-ॿ])"
_R = r"(?![\wऀ-ॿ])"

TIME_RE: re.Pattern = re.compile(
    _L + r"(?:\d{1,2}\s?(?:baje|pm|am|बजे)"
    r"|(?:raat|shaam|subah)\s+\d{1,2}"
    r"|" + "|".join(_WEEKDAYS_EN + _WEEKDAYS_HI) +
    r"|abhi|turant|aaj raat|kal)" + _R,
    re.IGNORECASE,
)

# Place = 1-3 capitalised words followed by a place keyword ("Ghanta Ghar chowk",
# "Nandpur bus stand", "Keshav market"). The keyword itself is case-insensitive.
_PLACE_WORDS = r"chowk|maidan|gate|bazaar|market|station|bus\s+stand|chauraha|office"
PLACE_RE: re.Pattern = re.compile(
    r"\b((?:[A-Z][a-z]+\s+){1,3})(?i:(" + _PLACE_WORDS + r"))\b"
)
# Capitalised words that start sentences or are times, never part of a place name.
_NOT_PLACE = {"abhi", "turant", "sab", "sabhi", "saare", "suna", "yaad", "note", "breaking",
              "emergency", "forward", "share", "hum", "ab", "aaj", "raat", "shaam", "yeh", "her",
              "the", "we", "keep", "bhoolna", "bahut", "hadd", "sehan"} | set(_WEEKDAYS_EN)

_GROUP_RE = re.compile(r"\bCommunity [A-Z]\b")


def _compile(lexicon: list[str]) -> re.Pattern:
    alts = "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in lexicon)
    return re.compile(_L + "(?:" + alts + ")" + _R, re.IGNORECASE)


_LEX_RE: dict[int, re.Pattern] = {}


def lex_hit(text: str, lexicon: list[str]) -> str | None:
    """Return the first lexicon phrase found in *text* (word-boundary match), else None."""
    pat = _LEX_RE.setdefault(id(lexicon), _compile(lexicon))
    m = pat.search(text or "")
    return m.group(0) if m else None


def find_places(text: str) -> list[str]:
    """Return place mentions such as "Ghanta Ghar chowk" (leading filler words dropped)."""
    places = []
    for m in PLACE_RE.finditer(text or ""):
        words = m.group(1).split()
        while words and words[0].lower() in _NOT_PLACE:
            words = words[1:]
        if words:
            places.append(" ".join(words) + " " + re.sub(r"\s+", " ", m.group(2).lower()))
    return places


_TIME_PHRASE_RE = re.compile(
    r"(?:(?:" + "|".join(_WEEKDAYS_EN) + r")\s+)?(?:(?:shaam|raat|subah|aaj raat)\s+)?\d{1,2}\s?(?:baje|pm|am)"
    r"|(?:raat|shaam|subah)\s+\d{1,2}",
    re.IGNORECASE,
)


def find_time_phrase(text: str) -> str | None:
    """Return the most specific time phrase ("Sunday shaam 5 baje"), else any time word."""
    m = _TIME_PHRASE_RE.search(text or "")
    if m:
        return m.group(0)
    m = TIME_RE.search(text or "")
    return m.group(0) if m else None


def is_mobilization(text: str, need_both: bool = False) -> bool:
    """MOBILIZE hit AND place/time (PLAN 10.1); with need_both, place AND time (T5)."""
    if not lex_hit(text, MOBILIZE):
        return False
    place, when = bool(find_places(text)), bool(TIME_RE.search(text or ""))
    return (place and when) if need_both else (place or when)



# ---------------------------------------------------------------------------
# Rules fallback
# ---------------------------------------------------------------------------

def _sentence_with(text: str, phrase: str) -> str:
    """The sentence of *text* containing *phrase* (an exact substring), max 160 chars."""
    idx = text.lower().find(phrase.lower())
    if idx < 0:
        return text[:120]
    starts = [text.rfind(c, 0, idx) for c in ".!?"]
    start = max(starts) + 1
    ends = [e for e in (text.find(c, idx) for c in ".!?") if e >= 0]
    end = min(ends) + 1 if ends else len(text)
    return text[start:end].strip()[:160]


def classify_rules(cluster: dict, df: pd.DataFrame) -> dict:
    """Deterministic, explainable classification from the shared lexicons."""
    cdf = df[df["post_id"].isin(cluster["post_ids"])].sort_values("timestamp")
    rows = list(cdf[["post_id", "text", "mentions"]].itertuples(index=False))
    n = max(len(rows), 1)

    def posts_with(lexicon):
        return [(r.post_id, r.text, lex_hit(r.text, lexicon)) for r in rows if lex_hit(r.text, lexicon)]

    hostile, share, alarm = posts_with(HOSTILE), posts_with(SHARE), posts_with(ALARM)
    intimidate, false_claims = posts_with(INTIMIDATE), posts_with(FALSE_CLAIM)
    mobil = [(r.post_id, r.text) for r in rows if is_mobilization(r.text)]
    mentions = Counter(m for r in rows for m in (r.mentions or []))
    groups = Counter(g for r in rows for g in _GROUP_RE.findall(r.text))

    if mentions and (intimidate or len(false_claims) / n >= 0.3):
        label = "harassment"
    elif len(alarm) / n >= 0.15 and len(alarm) >= len(hostile):
        label = "misinformation"
    elif mobil and len(mobil) / n >= 0.1 or len(hostile) / n >= 0.1:
        label = "incitement"
    elif groups and len(share) / n >= 0.3:
        label = "misinformation"  # a group-targeted claim being pushed, no hostility yet
    else:
        label = "benign"

    target, target_type = None, None
    if label == "harassment":
        target, target_type = mentions.most_common(1)[0][0], "individual"
    elif label != "benign" and groups:
        target, target_type = groups.most_common(1)[0][0], "group"
    elif label != "benign":
        target_type = "public"

    # Evidence: the most telling post for the label.
    if label == "harassment" and intimidate:
        ev_id, ev_text, phrase = intimidate[0]
    elif label == "incitement" and mobil:
        ev_id, ev_text = mobil[0]
        phrase = lex_hit(ev_text, MOBILIZE)
    elif label == "incitement" and hostile:
        ev_id, ev_text, phrase = hostile[0]
    elif label == "misinformation" and alarm:
        ev_id, ev_text, phrase = alarm[0]
    elif label == "misinformation" and false_claims:
        ev_id, ev_text, phrase = false_claims[0]
    else:
        ev_id, ev_text, phrase = rows[0].post_id, rows[0].text, rows[0].text[:60]
    quote = _sentence_with(ev_text, phrase)

    mob_texts = [t for _, t in mobil] or [r.text for r in rows]
    places = Counter(p for t in mob_texts for p in find_places(t))
    times = Counter(tp for t in mob_texts if (tp := find_time_phrase(t)))
    rationale = {
        "incitement": f"{len(hostile)} hostile and {len(mobil)} mobilization posts"
                      + (f" aimed at {target}" if target else "") + ".",
        "harassment": f"{len(intimidate)} intimidating and {len(false_claims)} discrediting posts aimed at {target}.",
        "misinformation": f"{len(alarm) or len(false_claims)} posts push an unverified alarming claim"
                          + (f" about {target}" if target else "") + f", {len(share)} ask others to share it.",
        "benign": "No hostile, alarm, intimidation or mobilization language found.",
    }[label]
    hits = {"incitement": len(hostile) + len(mobil), "harassment": len(intimidate) + len(false_claims),
            "misinformation": len(alarm) + len(false_claims) + len(share), "benign": 0}[label]
    return {
        "label": label,
        "confidence": round(0.8 if label == "benign" else min(0.95, 0.55 + 0.4 * hits / n), 2),
        "target": target, "target_type": target_type,
        "evidence_quote": quote, "evidence_post_id": ev_id,
        "call_to_action": label != "benign" and bool(mobil),
        "location_mentioned": places.most_common(1)[0][0] if places and label != "benign" else None,
        "time_mentioned": times.most_common(1)[0][0] if times and mobil and label != "benign" else None,
        "false_claim": label != "benign" and bool(false_claims or alarm),
        "intimidation": bool(intimidate),
        "rationale": rationale,
        "source": "rules",
    }



# ---------------------------------------------------------------------------
# Campaign label from post-level violations (IBM Bob)
# ---------------------------------------------------------------------------

_LABEL_OF = {
    "hate_enmity": "incitement", "incitement_violence": "incitement", "unlawful_assembly_call": "incitement",
    "religious_insult": "incitement", "criminal_intimidation": "harassment", "defamation_harassment": "harassment",
    "doxxing_stalking": "harassment", "sexual_harassment_obscenity": "harassment",
    "misinformation": "misinformation", "impersonation_fraud": "misinformation",
}


def classify_from_violations(cluster: dict, df: pd.DataFrame, violations: dict[str, dict]) -> dict:
    """Schema-4.5 classification for a cluster, aggregated from its posts' violations."""
    cdf = df[df["post_id"].isin(cluster["post_ids"])].sort_values("timestamp")
    res = [violations[p] for p in cdf["post_id"] if p in violations]
    bad = [r for r in res if r["violation"]]
    source = Counter(r["source"] for r in res).most_common(1)[0][0] if res else "rules"
    if not res:
        return classify_rules(cluster, df)
    if len(bad) / len(res) < 0.2:
        first = cdf.iloc[0]
        return {"label": "benign", "confidence": round(1 - len(bad) / len(res), 2), "target": None,
                "target_type": None, "evidence_quote": first["text"][:120], "evidence_post_id": first["post_id"],
                "call_to_action": False, "location_mentioned": None, "time_mentioned": None, "false_claim": False,
                "intimidation": False, "source": source,
                "rationale": f"Only {len(bad)} of {len(res)} posts violate any law; treated as organic activity."}
    cats = Counter(c for r in bad for c in r["categories"])
    votes = Counter()
    for c, n in cats.items():
        votes[_LABEL_OF[c]] += n
    # A mobilising or violent campaign is incitement even when many posts only repeat a false claim.
    if cats["misinformation"] > cats["hate_enmity"] + cats["incitement_violence"] and votes["misinformation"]:
        label = "misinformation"
    elif cats["unlawful_assembly_call"] + cats["incitement_violence"] + cats["hate_enmity"] >= 3:
        label = "incitement"
    else:
        label = votes.most_common(1)[0][0]
    targets = Counter((r["target"], r["target_type"]) for r in bad if r.get("target"))
    target, ttype = targets.most_common(1)[0][0] if targets else (None, "public")
    sev_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    key = max(bad, key=lambda r: (sev_rank.get(r["severity"], 0),
                                  any(_LABEL_OF[c] == label for c in r["categories"])))
    key_pid = next(p for p in cdf["post_id"] if violations.get(p) is key)
    mob = [r for r in bad if "unlawful_assembly_call" in r["categories"]]
    places = Counter(r["location"] for r in mob if r.get("location")) or         Counter(p for t in cdf["text"] for p in find_places(t))
    times = Counter(r["time"] for r in mob if r.get("time"))
    return {
        "label": label,
        "confidence": round(len(bad) / len(res), 2),
        "target": target, "target_type": ttype,
        "evidence_quote": key["evidence_quote"], "evidence_post_id": key_pid,
        "call_to_action": bool(mob),
        "location_mentioned": places.most_common(1)[0][0] if places and mob else None,
        "time_mentioned": times.most_common(1)[0][0] if times else None,
        "false_claim": bool(cats["misinformation"] or cats["defamation_harassment"] or cats["hate_enmity"]),
        "intimidation": bool(cats["criminal_intimidation"]),
        "rationale": f"{len(bad)} of {len(res)} posts violate the law: "
                     + ", ".join(f"{c.replace('_', ' ')} ×{n}" for c, n in cats.most_common(4)) + ".",
        "source": source,
    }


def classify_cluster(cluster: dict, df: pd.DataFrame, violations: dict[str, dict] | None = None) -> dict:
    """Classify one schema-4.4 cluster (never raises)."""
    try:
        if violations:
            return classify_from_violations(cluster, df, violations)
        return classify_rules(cluster, df)
    except Exception as exc:
        log.exception("classification failed: %s", exc)
        return classify_rules(cluster, df)
