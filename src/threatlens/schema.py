"""M1: load and validate posts and incidents from JSON or CSV (paths or uploaded files).

Only ``text`` is mandatory. Other PLAN 4.1 fields are mapped from common export column names
(e.g. ``content``, ``username``, ``created_at``) or derived: hashtags / mentions / URLs are
extracted from the text, ids are generated, missing times are spaced one minute apart. Every
inferred field is reported in ``df.attrs["inferred"]`` so the UI can say what was assumed.

Chain of custody: ``raw_json`` keeps each record exactly as uploaded; ``post_sha256`` hashes it.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Any

import pandas as pd

_IST = timezone(timedelta(hours=5, minutes=30))

POST_FIELDS = ["post_id", "account_id", "handle", "account_created_at", "followers", "text", "lang", "timestamp",
               "hashtags", "mentions", "urls", "media", "reply_to", "repost_of", "district", "platform"]
_POST_REQUIRED = POST_FIELDS  # kept for backwards compatibility
_INCIDENT_REQUIRED = ["incident_id", "reported_at", "district", "location", "category", "description", "source"]
_LIST_FIELDS = {"hashtags", "mentions", "urls", "media"}

ALIASES = {
    "text": ["text", "content", "message", "body", "post", "tweet", "full_text", "caption", "post_text"],
    "post_id": ["post_id", "id", "tweet_id", "message_id", "status_id", "postid"],
    "handle": ["handle", "username", "user_name", "screen_name", "author", "user", "account", "author_handle"],
    "account_id": ["account_id", "user_id", "author_id", "userid"],
    "timestamp": ["timestamp", "created_at", "date", "datetime", "time", "posted_at", "published_at"],
    "account_created_at": ["account_created_at", "user_created_at", "account_created", "joined"],
    "followers": ["followers", "followers_count", "user_followers", "follower_count"],
    "lang": ["lang", "language"],
    "hashtags": ["hashtags", "tags"], "mentions": ["mentions", "user_mentions"], "urls": ["urls", "links"],
    "media": ["media", "media_urls", "images", "attachments"],
    "reply_to": ["reply_to", "in_reply_to", "in_reply_to_status_id", "parent_id"],
    "repost_of": ["repost_of", "retweet_of", "retweeted_status_id", "shared_post_id"],
    "district": ["district", "location", "city", "region", "place"],
    "platform": ["platform", "source", "network", "site"],
}
_HASHTAG_RE = re.compile(r"#\w+")
_MENTION_RE = re.compile(r"@\w+")
_URL_RE = re.compile(r"https?://\S+")


def _parse_dt(value: Any) -> datetime:
    """ISO / common date strings or epoch seconds -> tz-aware datetime (naive = IST)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=_IST)
    if isinstance(value, (int, float)) and not pd.isna(value):
        return datetime.fromtimestamp(float(value), _IST)
    s = str(value).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = pd.to_datetime(s, dayfirst=True).to_pydatetime()
        except Exception as exc:
            raise ValueError(f"Cannot parse datetime: {value!r}") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=_IST)


def _normalise_list(value: Any) -> list:
    if isinstance(value, list):
        return [str(v) for v in value if v not in (None, "")]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    s = str(value).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except json.JSONDecodeError:
            pass
    return [x.strip() for x in re.split(r"[,;|]", s) if x.strip()]


def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip())


def parse_posts_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Map, validate and type a raw posts table. Raises ValueError with a readable message."""
    if df.empty:
        raise ValueError("The file contains no posts")
    raw_json = [json.dumps(r, sort_keys=True, ensure_ascii=False, default=str) for r in df.to_dict("records")]
    lower = {c.lower().strip(): c for c in df.columns}
    out, inferred = pd.DataFrame(index=df.index), []
    for field, names in ALIASES.items():
        col = next((lower[n] for n in names if n in lower), None)
        if col is not None:
            out[field] = df[col]
        if col is not None and col != field:
            inferred.append(f"{field} ← column '{col}'")
    if "text" not in out:
        raise ValueError("No text column found. Expected one of: " + ", ".join(ALIASES["text"]))
    out["text"] = out["text"].apply(lambda v: "" if _blank(v) else str(v))
    if (out["text"].str.strip() == "").all():
        raise ValueError("Every post has empty text")

    n = len(out)
    if "post_id" not in out:
        out["post_id"] = [f"P{i + 1:04d}" for i in range(n)]
        inferred.append("post_id generated")
    out["post_id"] = out["post_id"].astype(str)
    if out["post_id"].duplicated().any():
        raise ValueError(f"Duplicate post id {out.loc[out['post_id'].duplicated(), 'post_id'].iloc[0]!r}")
    if "handle" not in out and "account_id" not in out:
        out["handle"] = "unknown"
        inferred.append("no author column: all posts treated as one unknown account")
    if "handle" not in out:
        out["handle"] = out["account_id"].astype(str)
    if "account_id" not in out:
        out["account_id"] = out["handle"].astype(str)
        inferred.append("account_id = handle")
    out["handle"] = out["handle"].astype(str).str.lstrip("@")
    out["account_id"] = out["account_id"].astype(str)

    if "timestamp" in out:
        out["timestamp"] = out["timestamp"].apply(_parse_dt)
    else:
        base = datetime.now(_IST).replace(second=0, microsecond=0) - timedelta(minutes=n)
        out["timestamp"] = [base + timedelta(minutes=i) for i in range(n)]
        inferred.append("no timestamps: posts spaced 1 minute apart in file order (time signals unreliable)")
    out["timestamp"] = pd.to_datetime(out["timestamp"].apply(lambda d: d.astimezone(_IST)))
    if "account_created_at" in out:
        out["account_created_at"] = out["account_created_at"].apply(lambda v: None if _blank(v) else _parse_dt(v))
    else:
        out["account_created_at"] = None
        inferred.append("account age unknown (fresh-account signal off)")
    out["followers"] = pd.to_numeric(out["followers"], errors="coerce").fillna(0).astype(int) \
        if "followers" in out else 0
    for field, rx in (("hashtags", _HASHTAG_RE), ("mentions", _MENTION_RE), ("urls", _URL_RE)):
        if field in out:
            out[field] = out[field].apply(_normalise_list)
        else:
            out[field] = out["text"].apply(lambda t, rx=rx: rx.findall(t))
            inferred.append(f"{field} extracted from text")
    out["media"] = out["media"].apply(_normalise_list) if "media" in out else [[] for _ in range(n)]
    for f in ("reply_to", "repost_of"):
        out[f] = out[f].apply(lambda v: None if _blank(v) else str(v).split(".")[0] if isinstance(v, float)
                              else str(v)) if f in out else None
    out["lang"] = out["lang"].astype(str) if "lang" in out else out["text"].apply(
        lambda t: "hi" if re.search(r"[ऀ-ॿ]", t) else "en")
    out["district"] = out["district"].fillna("Unknown").astype(str) if "district" in out else "Unknown"
    out["platform"] = out["platform"].fillna("Unknown").astype(str) if "platform" in out else "Unknown"
    out["raw_json"] = raw_json
    out = out[POST_FIELDS + ["raw_json"]].reset_index(drop=True)
    out.attrs["inferred"] = inferred
    return out


def _read(path: str | Path | IO) -> tuple[bytes, str]:
    name = getattr(path, "name", str(path))
    if isinstance(path, (str, Path)):
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")
        return p.read_bytes(), p.suffix.lower()
    data = path.read()
    return (data.encode("utf-8") if isinstance(data, str) else data), Path(name).suffix.lower()


def load_posts(path: str | Path | IO) -> pd.DataFrame:
    """Posts from a .json (list, or {"posts": [...]}) or .csv file, path or uploaded file object."""
    raw, suffix = _read(path)
    if suffix == ".json":
        records = json.loads(raw.decode("utf-8-sig"))
        if isinstance(records, dict):
            records = next((v for v in records.values() if isinstance(v, list)), None)
        if not isinstance(records, list):
            raise ValueError("JSON must be a list of posts (or an object holding one)")
        df = pd.DataFrame(records)
    elif suffix == ".csv":
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    else:
        raise ValueError(f"Unsupported file type {suffix!r}; upload .json or .csv")
    return parse_posts_frame(df)


def post_sha256(row) -> str:
    """sha256 of the post record exactly as it was loaded (PLAN 10.8 chain of custody)."""
    payload = row["raw_json"] if "raw_json" in row and isinstance(row["raw_json"], str) else \
        json.dumps({f: (row[f].isoformat() if isinstance(row[f], datetime) else row[f]) for f in POST_FIELDS},
                   sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_incidents(path: str | Path | IO) -> list[dict]:
    """Offline incident log from .json (list) or .csv; see PLAN 4.2 for the fields."""
    raw, suffix = _read(path)
    if suffix == ".csv":
        records = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False).to_dict("records")
    else:
        records = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(records, list):
        raise ValueError("Incidents must be a list of incident objects")
    result = []
    for i, rec in enumerate(records):
        missing = [f for f in ("reported_at", "location") if f not in rec]
        if missing:
            raise ValueError(f"Incident {i + 1} is missing {missing}")
        rec = {"incident_id": rec.get("incident_id") or f"INC-{i + 1:02d}", "district": rec.get("district", ""),
               "category": rec.get("category", "unknown"), "description": rec.get("description", ""),
               "source": rec.get("source", "uploaded log"), **rec}
        rec["reported_at"] = _parse_dt(rec["reported_at"])
        result.append(rec)
    return result
