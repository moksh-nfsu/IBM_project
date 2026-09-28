"""Shared fixtures: the sample data and one rules-mode analysis (deterministic, offline)."""
from __future__ import annotations

import json

import pytest

from threatlens.paths import SAMPLE_DATA
from threatlens.pipeline import analyze, load_sample


@pytest.fixture(scope="session")
def sample():
    return load_sample()


@pytest.fixture(scope="session")
def df(sample):
    return sample[0]


@pytest.fixture(scope="session")
def incidents(sample):
    return sample[1]


@pytest.fixture(scope="session")
def answer_key():
    return json.loads((SAMPLE_DATA / "answer_key.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def result(df, incidents):
    return analyze(df, incidents, llm_mode="rules")


@pytest.fixture(scope="session")
def by_group(result, answer_key):
    """Answer-key group -> the campaign with the largest account overlap."""
    out = {}
    for g, truth in answer_key.items():
        if not truth.get("expected_state"):
            continue
        acc = set(truth["account_ids"])
        out[g] = max(result["campaigns"], key=lambda c: len(acc & set(c["_cluster"]["account_ids"])))
    return out
