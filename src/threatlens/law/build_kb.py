"""Build the legal knowledge base from the official Acts (run once; output is committed).

Sources (copied unchanged into law/sources/):
  bns_2023_gazette.pdf     The Bharatiya Nyaya Sanhita, 2023 (Act No. 45 of 2023), Gazette of India
                           Extraordinary, Part II Section 1, No. 53, 25 Dec 2023 (CG-DL-E-25122023-250883),
                           Ministry of Law and Justice (Legislative Department).
  it_act_2000_updated.pdf  The Information Technology Act, 2000 (Act No. 21 of 2000), updated text as
                           published on India Code / by the Legislative Department.

Usage (from src/):  python -m threatlens.law.build_kb
Writes law/law_kb.json: one record per section {act, section, title, text, page, source}.
Section text is taken verbatim from the PDF; only page headers, footers and the BNS marginal
notes are removed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pypdf

HERE = Path(__file__).parent
SOURCES = HERE / "sources"
OUT = HERE / "law_kb.json"

BNS_PDF = SOURCES / "bns_2023_gazette.pdf"
IT_PDF = SOURCES / "it_act_2000_updated.pdf"
BNS_SOURCE = ("The Bharatiya Nyaya Sanhita, 2023 (No. 45 of 2023), Gazette of India Extraordinary, "
              "Part II Sec. 1, No. 53, 25 Dec 2023, CG-DL-E-25122023-250883")
IT_SOURCE = "The Information Technology Act, 2000 (No. 21 of 2000), updated text, Legislative Department / India Code"

# BNS gazette prints section headings as marginal notes, which pypdf cannot reliably align with
# section numbers. Titles are therefore taken from the official "marginal note" wording for the
# sections ThreatLens uses; every other section is titled by its opening words.
BNS_TITLES = {
    "57": "Abetting commission of offence by public or by more than ten persons",
    "61": "Criminal conspiracy",
    "75": "Sexual harassment",
    "78": "Stalking",
    "79": "Word, gesture or act intended to insult modesty of a woman",
    "189": "Unlawful assembly",
    "191": "Rioting",
    "192": "Wantonly giving provocation with intent to cause riot",
    "196": "Promoting enmity between different groups on grounds of religion, race, place of birth, "
           "residence, language, etc., and doing acts prejudicial to maintenance of harmony",
    "197": "Imputations, assertions prejudicial to national integration",
    "294": "Sale, etc., of obscene books, etc.",
    "299": "Deliberate and malicious acts, intended to outrage religious feelings of any class by "
           "insulting its religion or religious beliefs",
    "302": "Uttering words, etc., with deliberate intent to wound religious feelings of any person",
    "319": "Cheating by personation",
    "351": "Criminal intimidation",
    "352": "Intentional insult with intent to provoke breach of peace",
    "353": "Statements conducing to public mischief",
    "356": "Defamation",
}

_NOISE = re.compile(r"THE GAZETTE OF INDIA EXTRAORDINARY|^_{5,}|^Sec\. \d\]|^\d+\s*$|\[Part II")


def _pages(path: Path) -> list[str]:
    return [p.extract_text() or "" for p in pypdf.PdfReader(str(path)).pages]


def _clean_bns(block: str) -> str:
    """Drop page furniture and marginal notes (runs of short lines) from a BNS section."""
    lines = [l.rstrip() for l in block.splitlines()]
    lines = [l for l in lines if l.strip() and not _NOISE.search(l)]
    out, run = [], []
    for l in lines:
        if len(l) <= 22 and not re.match(r"^\(?[a-z0-9]+\)", l.strip()):
            run.append(l)
            continue
        if len(run) < 2:
            out.extend(run)
        run = []
        out.append(l)
    if len(run) < 2:
        out.extend(run)
    text = " ".join(out)
    return re.sub(r"\s+", " ", text).strip()


def parse_bns() -> list[dict]:
    pages = _pages(BNS_PDF)
    joined, offsets = "", []
    for i, p in enumerate(pages):
        offsets.append((len(joined), i + 1))
        joined += "\n" + p
    starts, expected = [], 1
    for m in re.finditer(r"\n(\d{1,3})\.\s?(?=\(1\)|[A-Z“(])", joined):
        n = int(m.group(1))
        if n == expected:
            starts.append((n, m.start()))
            expected += 1
    records = []
    for idx, (n, pos) in enumerate(starts):
        end = starts[idx + 1][1] if idx + 1 < len(starts) else len(joined)
        text = _clean_bns(joined[pos:end])
        page = max(pg for off, pg in offsets if off <= pos)
        sec = str(n)
        title = BNS_TITLES.get(sec) or re.sub(r"^\d+\.\s*(\(1\)\s*)?", "", text)[:90].rstrip(",;:") + "…"
        records.append({"act": "BNS", "section": sec, "title": title, "text": text[:6000],
                        "page": page, "source": BNS_SOURCE})
    return records


def parse_it_act() -> list[dict]:
    pages = _pages(IT_PDF)
    toc = "\n".join(pages[:4])
    titles = {m.group(1): m.group(2).strip() for m in
              re.finditer(r"^\s*(\d{1,2}[A-Z]{0,2})\.\s+(.+?)\s*$", toc, re.M)}
    body, offsets = "", []
    for i, p in enumerate(pages[4:], start=5):
        offsets.append((len(body), i))
        body += "\n" + p
    records, cursor = [], 0
    order = list(titles)
    positions = []
    for sec in order:
        m = re.compile(r"\n\s*(?:\d+\[)?" + re.escape(sec) + r"\.\s").search(body, cursor)
        if m:
            positions.append((sec, m.start()))
            cursor = m.end()
    for idx, (sec, pos) in enumerate(positions):
        end = positions[idx + 1][1] if idx + 1 < len(positions) else len(body)
        raw = body[pos:end]
        raw = re.split(r"\n\s*_{5,}|\n\s*1\.\s+(?:Ins|Subs|Omitted)", raw)[0]
        text = re.sub(r"\s+", " ", raw).strip()
        page = max(pg for off, pg in offsets if off <= pos)
        records.append({"act": "IT Act", "section": sec, "title": titles[sec].rstrip("."), "text": text[:6000],
                        "page": page, "source": IT_SOURCE})
    return records


def build() -> list[dict]:
    kb = parse_bns() + parse_it_act()
    OUT.write_text(json.dumps(kb, ensure_ascii=False, indent=1), encoding="utf-8")
    return kb


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    kb = build()
    bns = [r for r in kb if r["act"] == "BNS"]
    it = [r for r in kb if r["act"] == "IT Act"]
    print(f"BNS sections: {len(bns)} (last {bns[-1]['section']}) | IT Act sections: {len(it)} -> {OUT}")
