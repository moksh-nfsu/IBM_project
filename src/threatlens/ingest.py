"""M1: DataFrame normalisation and snapshot filtering.

``normalize(df)`` adds derived columns:
- ``text_masked``: PII-masked version of ``text`` ([PHONE], [EMAIL]).
- ``hashtags_lower``: lowercase copy of each hashtag for case-insensitive matching.
- ``account_age_days``: account age in days *at the moment the post was made*.

``snapshot(df, cutoff)`` returns only the posts whose ``timestamp <= cutoff``.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

import pandas as pd

_IST = timezone(timedelta(hours=5, minutes=30))

# Regex patterns for PII masking
_PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(?:\+91[-\s]?)?"               # optional country code
    r"(?:0?[6-9]\d{9})"             # 10-digit Indian mobile
    r"(?!\d)"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _mask_pii(text: str) -> str:
    """Replace phone numbers and email addresses with placeholders."""
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    return text


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns to a posts DataFrame in-place and return it.

    New columns
    -----------
    text_masked : str
        ``text`` with phone numbers replaced by ``[PHONE]`` and email
        addresses replaced by ``[EMAIL]``.
    hashtags_lower : list[str]
        Lowercase copies of every hashtag (keeps the ``#`` prefix).
    account_age_days : float
        ``(timestamp − account_created_at).total_seconds() / 86400``.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame produced by ``schema.load_posts``.

    Returns
    -------
    pd.DataFrame
        Same object with the three new columns added.
    """
    df = df.copy()

    df["text_masked"] = df["text"].apply(_mask_pii)

    df["hashtags_lower"] = df["hashtags"].apply(
        lambda tags: [t.lower() for t in tags]
    )

    def _age(row: pd.Series) -> float:
        ts: datetime = row["timestamp"]
        created: datetime = row["account_created_at"]
        # Both are tz-aware; subtraction is safe
        if created is None or pd.isna(created):
            return float("nan")  # unknown account age: the fresh-account signal stays off
        return (ts - created).total_seconds() / 86_400

    df["account_age_days"] = df.apply(_age, axis=1).astype(float)

    return df


def snapshot(df: pd.DataFrame, cutoff: str | datetime) -> pd.DataFrame:
    """Return only posts whose ``timestamp`` is ≤ *cutoff*.

    Parameters
    ----------
    df : pd.DataFrame
        Normalised post DataFrame.
    cutoff : str | datetime
        ISO 8601 string (with offset) or a tz-aware datetime.

    Returns
    -------
    pd.DataFrame
        Filtered subset; index is reset.
    """
    if isinstance(cutoff, str):
        cutoff_str = cutoff.replace("Z", "+00:00")
        cutoff = datetime.fromisoformat(cutoff_str)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=_IST)
    mask = df["timestamp"] <= cutoff
    return df.loc[mask].reset_index(drop=True)
