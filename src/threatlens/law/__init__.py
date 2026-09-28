"""Legal knowledge base: BNS 2023 and IT Act 2000, text taken verbatim from the official PDFs.

law_kb.json is produced by build_kb.py from law/sources/*.pdf. This module exposes:
  section(act, number)   -> the official record (title, text, page, source)
  CANDIDATES             -> offence sections that online posts can plausibly attract, which is the
                            only list the AI may choose from
  CATEGORIES             -> the violation taxonomy with the sections each category usually maps to
  EXCLUDED               -> sections that must never be suggested, with the reason
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

KB_PATH = Path(__file__).parent / "law_kb.json"
SOURCES_DIR = Path(__file__).parent / "sources"


@lru_cache(maxsize=1)
def load_kb() -> dict[tuple[str, str], dict]:
    return {(r["act"], r["section"]): r for r in json.loads(KB_PATH.read_text(encoding="utf-8"))}


def norm_act(act: str) -> str:
    a = (act or "").lower().replace(".", "").strip()
    if a in ("bns", "bharatiya nyaya sanhita", "bharatiya nyaya sanhita 2023") or "nyaya" in a:
        return "BNS"
    if a in ("it act", "it", "ita", "information technology act") or "information technology" in a or a.startswith("it"):
        return "IT Act"
    return act


def norm_section(sec: str) -> str:
    """'Section 196(1)(a)' -> '196', '66 D' -> '66D'."""
    m = re.search(r"(\d{1,3})\s*([A-Z]{0,2})", str(sec).upper().replace("SECTION", ""))
    return (m.group(1) + m.group(2)) if m else str(sec)


def section(act: str, number: str) -> dict | None:
    return load_kb().get((norm_act(act), norm_section(number)))


# Offence sections relevant to online content. The AI may only cite these.
CANDIDATES: list[tuple[str, str]] = [
    ("BNS", "57"), ("BNS", "61"), ("BNS", "75"), ("BNS", "78"), ("BNS", "79"), ("BNS", "189"),
    ("BNS", "192"), ("BNS", "196"), ("BNS", "197"), ("BNS", "294"), ("BNS", "299"), ("BNS", "302"),
    ("BNS", "319"), ("BNS", "351"), ("BNS", "352"), ("BNS", "353"), ("BNS", "356"),
    ("IT Act", "66C"), ("IT Act", "66D"), ("IT Act", "66E"), ("IT Act", "67"), ("IT Act", "67A"),
    ("IT Act", "67B"),
]

EXCLUDED = {
    ("IT Act", "66A"): "Struck down by the Supreme Court in Shreya Singhal v. Union of India (2015); "
                       "never cite it.",
}

# Violation taxonomy: id -> (label, what it means, usual sections).
CATEGORIES: dict[str, dict] = {
    "hate_enmity": {"label": "Hate / promoting enmity",
                    "desc": "promotes hatred, disharmony or ill-will against a religious, caste, regional, "
                            "language or community group, including false accusations against a group",
                    "sections": [("BNS", "196"), ("BNS", "197")]},
    "religious_insult": {"label": "Insulting religious beliefs",
                         "desc": "deliberately insults or mocks a religion or religious feelings",
                         "sections": [("BNS", "299"), ("BNS", "302")]},
    "incitement_violence": {"label": "Incitement to violence / retaliation",
                            "desc": "urges or provokes violence, retaliation or an offence against a group or person",
                            "sections": [("BNS", "192"), ("BNS", "353"), ("BNS", "196")]},
    "unlawful_assembly_call": {"label": "Call to gather / mobilise",
                               "desc": "calls people to assemble at a place and/or time with a hostile or unlawful "
                                       "purpose, or to act collectively (e.g. 'reach X chowk at 5')",
                               "sections": [("BNS", "189"), ("BNS", "57")]},
    "criminal_intimidation": {"label": "Threat / criminal intimidation",
                              "desc": "threatens injury to a person, their reputation or property, or says "
                                      "'we know where you live/work', 'or face consequences'",
                              "sections": [("BNS", "351")]},
    "defamation_harassment": {"label": "Defamation / targeted harassment",
                              "desc": "makes damaging imputations about an identifiable person (e.g. 'fake', "
                                      "'paid', 'corrupt') or targets them with abuse",
                              "sections": [("BNS", "356"), ("BNS", "352")]},
    "misinformation": {"label": "Misinformation causing public alarm",
                       "desc": "spreads a false or unverified rumour likely to cause fear or alarm to the public "
                               "(fake disaster, fake attack, fake health scare)",
                       "sections": [("BNS", "353")]},
    "doxxing_stalking": {"label": "Doxxing / stalking",
                         "desc": "publishes someone's phone, address or whereabouts to expose or pursue them, "
                                 "or repeatedly follows/monitors a woman online",
                         "sections": [("BNS", "78"), ("BNS", "351")]},
    "impersonation_fraud": {"label": "Impersonation / online fraud",
                            "desc": "pretends to be an official, company or another person, or asks for OTP, "
                                    "passwords or money under a false identity",
                            "sections": [("IT Act", "66D"), ("IT Act", "66C"), ("BNS", "319")]},
    "sexual_harassment_obscenity": {"label": "Sexual harassment / obscene content",
                                    "desc": "sexually coloured remarks, insults to a woman's modesty, or obscene material",
                                    "sections": [("BNS", "79"), ("BNS", "75"), ("IT Act", "67"), ("BNS", "294")]},
}

SEVERITIES = ["low", "medium", "high", "critical"]


def candidate_catalogue(max_chars: int = 320) -> str:
    """Candidate sections with their official title and opening text, for the AI prompt."""
    lines = []
    for act, sec in CANDIDATES:
        r = section(act, sec)
        if r:
            body = re.sub(r"^\S+\s*", "", r["text"])[:max_chars]
            lines.append(f"- {act} {sec} — {r['title']}: {body}…")
    return "\n".join(lines)


def source_files() -> list[dict]:
    """The official PDFs with their SHA-256, for the data-sources page."""
    import hashlib
    out = []
    for p in sorted(SOURCES_DIR.glob("*.pdf")):
        out.append({"file": p.name, "bytes": p.stat().st_size,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    return out
