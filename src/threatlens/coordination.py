"""M2: Coordination detection.

Builds an undirected account graph from four edge types, then extracts
connected components with ≥5 accounts as clusters (schema 4.4).

Edge types (PLAN.md §7):
1. Text similarity  — TF-IDF char_wb 3-5 ngrams, cosine ≥ 0.80, different accounts
2. Repost / reply   — explicit repost_of / reply_to links
3. Shared URL/media — same URL or media file posted by ≥5 accounts within 30 min
4. Time-sync hashtag — same hashtag by ≥8 distinct accounts in a 10-min window
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import timedelta

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---------------------------------------------------------------------------
# Constants (PLAN.md §7)
# ---------------------------------------------------------------------------
_SIM_THRESHOLD = 0.80          # cosine similarity for near-duplicate text
_SHARED_URL_MIN_ACCOUNTS = 5   # min accounts for shared-URL/media edge
_SHARED_URL_WINDOW_MIN = 30    # minutes
_HASHTAG_MIN_ACCOUNTS = 8      # min distinct accounts for time-sync hashtag
_HASHTAG_WINDOW_MIN = 10       # minutes sliding window
_MIN_CLUSTER_ACCOUNTS = 5      # min accounts for a valid cluster

# Signal weights
_WEIGHTS = {
    "text_similarity": 25,
    "time_sync": 20,
    "fresh_accounts": 20,
    "shared_url": 15,
    "amplification": 20,
}

_FRESH_AGE_DAYS = 30
_FRESH_FOLLOWERS = 100
_FRESH_HANDLE_RE = re.compile(r"^[a-z]+_?\d{3,}$")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_seconds(td: timedelta) -> float:
    return td.total_seconds()


def _build_text_sim_edges(df: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Return (account_a, account_b, 'similar') edges for cosine ≥ 0.80."""
    if len(df) < 2:
        return []

    texts = df["text"].tolist()
    try:
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)
        mat = vec.fit_transform(texts)
    except ValueError:
        return []

    # Work in chunks to avoid huge dense matrix
    edges = []
    account_ids = df["account_id"].tolist()
    post_ids = df["post_id"].tolist()
    n = mat.shape[0]

    chunk = 200  # process 200 rows at a time
    for start in range(0, n, chunk):
        end = min(start + chunk, n)
        block = cosine_similarity(mat[start:end], mat)
        for i_local, i_global in enumerate(range(start, end)):
            ai = account_ids[i_global]
            row = block[i_local]
            # Only look at j > i_global to avoid duplicate edges
            for j_global in range(i_global + 1, n):
                if row[j_global] >= _SIM_THRESHOLD:
                    aj = account_ids[j_global]
                    if ai != aj:
                        edges.append((ai, aj, "similar"))
    return edges


def _build_repost_reply_edges(df: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Return (reposter, original_author, 'repost') edges from repost_of / reply_to."""
    pid_to_account = dict(zip(df["post_id"], df["account_id"]))
    edges = []
    for _, row in df.iterrows():
        for field, label in (("repost_of", "repost"), ("reply_to", "reply")):
            target_pid = row.get(field)
            if target_pid and target_pid in pid_to_account:
                a = row["account_id"]
                b = pid_to_account[target_pid]
                if a != b:
                    edges.append((a, b, label))
    return edges


def _build_shared_url_media_edges(df: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Return edges for URL/media shared by ≥5 accounts within 30 min."""
    edges = []

    def _process_field(field: str) -> None:
        # Collect (item, account_id, timestamp) triples
        records: list[tuple[str, str, object]] = []
        for _, row in df.iterrows():
            for item in row.get(field, []):
                if item:
                    records.append((item, row["account_id"], row["timestamp"]))
        if not records:
            return

        # Group by item
        by_item: dict[str, list[tuple[str, object]]] = defaultdict(list)
        for item, acc, ts in records:
            by_item[item].append((acc, ts))

        window = timedelta(minutes=_SHARED_URL_WINDOW_MIN)
        for item, postings in by_item.items():
            postings.sort(key=lambda x: x[1])
            # Sliding window: for each anchor find accounts within 30 min
            i = 0
            for j, (acc_j, ts_j) in enumerate(postings):
                while _to_seconds(ts_j - postings[i][1]) > window.total_seconds():
                    i += 1
                window_accounts = list(dict.fromkeys(
                    a for a, _ in postings[i:j + 1]
                ))
                if len(window_accounts) >= _SHARED_URL_MIN_ACCOUNTS:
                    for x in range(len(window_accounts)):
                        for y in range(x + 1, len(window_accounts)):
                            edges.append((window_accounts[x], window_accounts[y], "url"))

    _process_field("urls")
    _process_field("media")
    return edges


def _build_hashtag_sync_edges(df: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Return edges for hashtag used by ≥8 accounts in a 10-min window."""
    edges = []
    # Use hashtags_lower if present (from ingest.normalize), else lowercase hashtags
    tag_col = "hashtags_lower" if "hashtags_lower" in df.columns else "hashtags"

    records: list[tuple[str, str, object]] = []
    for _, row in df.iterrows():
        for tag in row.get(tag_col, []):
            if tag:
                records.append((tag.lower(), row["account_id"], row["timestamp"]))

    by_tag: dict[str, list[tuple[str, object]]] = defaultdict(list)
    for tag, acc, ts in records:
        by_tag[tag].append((acc, ts))

    window = timedelta(minutes=_HASHTAG_WINDOW_MIN)
    for tag, postings in by_tag.items():
        postings.sort(key=lambda x: x[1])
        i = 0
        for j, (acc_j, ts_j) in enumerate(postings):
            while _to_seconds(ts_j - postings[i][1]) > window.total_seconds():
                i += 1
            window_accounts = list(dict.fromkeys(
                a for a, _ in postings[i:j + 1]
            ))
            if len(window_accounts) >= _HASHTAG_MIN_ACCOUNTS:
                for x in range(len(window_accounts)):
                    for y in range(x + 1, len(window_accounts)):
                        edges.append((window_accounts[x], window_accounts[y], "burst"))
    return edges


def _near_dup_groups(df: pd.DataFrame, sim_threshold: float = _SIM_THRESHOLD) -> list[list[str]]:
    """Return groups of post_ids whose texts are near-duplicates across different accounts."""
    if len(df) < 2:
        return []
    texts = df["text"].tolist()
    try:
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)
        mat = vec.fit_transform(texts)
    except ValueError:
        return []

    post_ids = df["post_id"].tolist()
    account_ids = df["account_id"].tolist()
    n = mat.shape[0]

    # Union-find to group near-duplicate posts
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    chunk = 200
    for start in range(0, n, chunk):
        end = min(start + chunk, n)
        block = cosine_similarity(mat[start:end], mat)
        for i_local, i_global in enumerate(range(start, end)):
            for j_global in range(i_global + 1, n):
                if (block[i_local][j_global] >= sim_threshold
                        and account_ids[i_global] != account_ids[j_global]):
                    union(i_global, j_global)

    groups: dict[int, list[str]] = defaultdict(list)
    for idx, pid in enumerate(post_ids):
        groups[find(idx)].append(pid)

    return [g for g in groups.values() if len(g) > 1]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_clusters(df: pd.DataFrame) -> list[dict]:
    """Detect coordinated clusters in *df* and return a list of cluster dicts.

    Each cluster conforms to schema 4.4.  Clusters are sorted by ``start``
    (ascending) and assigned ids K1, K2 …

    Parameters
    ----------
    df:
        Normalised post DataFrame produced by ``ingest.normalize``.

    Returns
    -------
    list[dict]
        Schema-4.4 clusters; empty list if none meet the ≥5-account threshold.
    """
    if df.empty:
        return []

    # Build account graph
    G = nx.Graph()
    G.add_nodes_from(df["account_id"].unique())

    all_edges: list[tuple[str, str, str]] = []
    all_edges.extend(_build_repost_reply_edges(df))
    all_edges.extend(_build_shared_url_media_edges(df))
    all_edges.extend(_build_hashtag_sync_edges(df))
    all_edges.extend(_build_text_sim_edges(df))

    # Deduplicate edges (keep all edge labels for schema output)
    edge_labels: dict[frozenset, list[str]] = defaultdict(list)
    for a, b, label in all_edges:
        key = frozenset([a, b])
        if label not in edge_labels[key]:
            edge_labels[key].append(label)

    for key, labels in edge_labels.items():
        pair = list(key)
        if len(pair) == 2:
            G.add_edge(pair[0], pair[1])

    # Extract components with ≥5 accounts
    pid_lookup = df.set_index("post_id")
    acc_to_posts: dict[str, list[str]] = defaultdict(list)
    for _, row in df.iterrows():
        acc_to_posts[row["account_id"]].append(row["post_id"])

    # Pre-compute near-dup groups once across the whole df
    all_near_dup = _near_dup_groups(df)
    pid_in_dup: set[str] = {pid for grp in all_near_dup for pid in grp}

    raw_clusters = []
    for component in nx.connected_components(G):
        if len(component) < _MIN_CLUSTER_ACCOUNTS:
            continue
        post_ids = [
            pid for acc in component for pid in acc_to_posts.get(acc, [])
            if pid in df["post_id"].values
        ]
        if not post_ids:
            continue

        cluster_df = df[df["post_id"].isin(post_ids)].sort_values("timestamp")
        timestamps = cluster_df["timestamp"].tolist()

        raw_clusters.append({
            "_accounts": component,
            "_post_ids": post_ids,
            "_timestamps": timestamps,
            "_cluster_df": cluster_df,
        })

    # Sort by earliest post time
    raw_clusters.sort(key=lambda c: c["_timestamps"][0])

    clusters: list[dict] = []
    for k_idx, raw in enumerate(raw_clusters):
        component = raw["_accounts"]
        post_ids = raw["_post_ids"]
        cluster_df = raw["_cluster_df"]
        timestamps = raw["_timestamps"]

        account_ids = list(component)
        start = timestamps[0]
        end = timestamps[-1]

        # near_dup_groups scoped to this cluster
        cluster_dup_groups = [
            [pid for pid in grp if pid in set(post_ids)]
            for grp in all_near_dup
            if any(pid in set(post_ids) for pid in grp)
        ]
        cluster_dup_groups = [g for g in cluster_dup_groups if len(g) > 1]
        cluster_dup_pids: set[str] = {pid for g in cluster_dup_groups for pid in g}

        # detected_at: timestamp of the 5th post in a dup group or burst
        # "burst" posts: in the densest 10-min window
        burst_pids = _densest_window_pids(cluster_df, minutes=10)
        qualifying_pids = cluster_dup_pids | burst_pids
        qualifying_sorted = cluster_df[cluster_df["post_id"].isin(qualifying_pids)].sort_values("timestamp")
        if len(qualifying_sorted) >= 5:
            detected_at = qualifying_sorted.iloc[4]["timestamp"]
        elif len(qualifying_sorted) > 0:
            detected_at = qualifying_sorted.iloc[-1]["timestamp"]
        else:
            detected_at = timestamps[min(4, len(timestamps) - 1)]

        # first_posters: up to 3 earliest unique authors of repost targets or dup groups
        fp_accounts = _compute_first_posters(cluster_df, cluster_dup_groups, df)

        # top_amplifiers: top 5 by reposts received + copies of their text
        top_amp = _compute_top_amplifiers(cluster_df, cluster_dup_groups, df)

        # Aggregate cluster-level fields
        hashtags = list(dict.fromkeys(
            h for _, row in cluster_df.iterrows() for h in row.get("hashtags", [])
        ))
        urls = list(dict.fromkeys(
            u for _, row in cluster_df.iterrows() for u in row.get("urls", [])
        ))
        media = list(dict.fromkeys(
            m for _, row in cluster_df.iterrows() for m in row.get("media", [])
        ))
        district_counts: dict[str, int] = {}
        for _, row in cluster_df.iterrows():
            d = row.get("district", "Unknown")
            district_counts[d] = district_counts.get(d, 0) + 1

        # edges for this cluster
        edges_out = []
        seen_pairs: set[frozenset] = set()
        for pair_key, labels in edge_labels.items():
            pair = list(pair_key)
            if len(pair) == 2 and pair[0] in component and pair[1] in component:
                fs = frozenset(pair)
                if fs not in seen_pairs:
                    edges_out.append([pair[0], pair[1], labels])
                    seen_pairs.add(fs)

        cluster_id = f"K{k_idx + 1}"
        partial = {
            "cluster_id": cluster_id,
            "account_ids": account_ids,
            "post_ids": post_ids,
            "first_posters": fp_accounts,
            "top_amplifiers": top_amp,
            "hashtags": hashtags,
            "urls": urls,
            "media": media,
            "districts": district_counts,
            "start": _iso(start),
            "end": _iso(end),
            "detected_at": _iso(detected_at),
            "near_dup_groups": cluster_dup_groups,
            "edges": edges_out,
            # signals/contributions/score filled by score_cluster below
        }
        score_cluster(partial, df)
        clusters.append(partial)

    return clusters


def score_cluster(cluster: dict, df: pd.DataFrame) -> dict:
    """Compute coordination signals and score for *cluster* (mutates in-place).

    Parameters
    ----------
    cluster:
        Partial cluster dict with ``account_ids``, ``post_ids``,
        ``near_dup_groups``.
    df:
        Full normalised post DataFrame.

    Returns
    -------
    dict
        The same *cluster* dict with ``signals``, ``contributions``,
        ``coordination_score`` populated.
    """
    post_ids = cluster["post_ids"]
    account_ids = cluster["account_ids"]
    near_dup_groups = cluster.get("near_dup_groups", [])
    cluster_df = df[df["post_id"].isin(post_ids)].copy()
    n_posts = len(cluster_df)
    n_accounts = len(account_ids)

    if n_posts == 0:
        cluster["signals"] = {k: 0.0 for k in _WEIGHTS}
        cluster["contributions"] = {k: 0 for k in _WEIGHTS}
        cluster["coordination_score"] = 0
        return cluster

    # --- text_similarity ---
    dup_pids = {pid for g in near_dup_groups for pid in g}
    text_sim = len(dup_pids) / n_posts if n_posts else 0.0

    # --- time_sync ---
    densest = _densest_window_pids(cluster_df, minutes=10)
    time_sync = len(densest) / n_posts if n_posts else 0.0

    # --- fresh_accounts ---
    acc_df = df[df["account_id"].isin(account_ids)].drop_duplicates("account_id")
    fresh_mask = (
        (acc_df["account_age_days"] < _FRESH_AGE_DAYS)
        & (acc_df["followers"] < _FRESH_FOLLOWERS)
    ) if "account_age_days" in acc_df.columns else pd.Series([False] * len(acc_df))
    fresh_ratio = fresh_mask.sum() / n_accounts if n_accounts else 0.0
    handle_bonus = 0.0
    if fresh_ratio > 0.5:
        fresh_handles = acc_df[fresh_mask]["handle"].tolist() if fresh_mask.any() else []
        if fresh_handles and sum(1 for h in fresh_handles if _FRESH_HANDLE_RE.match(str(h).lower())) / len(fresh_handles) > 0.5:
            handle_bonus = 0.2
    fresh_accounts = min(1.0, fresh_ratio + handle_bonus)

    # --- shared_url ---
    all_urls_media = (
        [u for _, row in cluster_df.iterrows() for u in row.get("urls", [])]
        + [m for _, row in cluster_df.iterrows() for m in row.get("media", [])]
    )
    if all_urls_media:
        from collections import Counter
        top_item = Counter(all_urls_media).most_common(1)[0][0]
        shared_url = sum(
            1 for _, row in cluster_df.iterrows()
            if top_item in row.get("urls", []) or top_item in row.get("media", [])
        ) / n_posts
    else:
        shared_url = 0.0

    # --- amplification ---
    repost_reply_edges = sum(
        1 for e in cluster.get("edges", [])
        if any(lbl in ("repost", "reply") for lbl in e[2])
    )
    amplification = min(1.0, repost_reply_edges / n_posts if n_posts else 0.0)

    signals = {
        "text_similarity": round(float(text_sim), 4),
        "time_sync": round(float(time_sync), 4),
        "fresh_accounts": round(float(fresh_accounts), 4),
        "shared_url": round(float(shared_url), 4),
        "amplification": round(float(amplification), 4),
    }
    contributions = {k: int(round(_WEIGHTS[k] * signals[k])) for k in _WEIGHTS}
    score = int(sum(contributions.values()))

    cluster["signals"] = signals
    cluster["contributions"] = contributions
    cluster["coordination_score"] = score
    return cluster


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _densest_window_pids(cluster_df: pd.DataFrame, minutes: int = 10) -> set[str]:
    """Return post_ids inside the densest *minutes*-wide time window."""
    if cluster_df.empty:
        return set()
    sorted_df = cluster_df.sort_values("timestamp")
    timestamps = sorted_df["timestamp"].tolist()
    post_ids = sorted_df["post_id"].tolist()
    window = timedelta(minutes=minutes)
    best_start = 0
    best_count = 0
    i = 0
    for j in range(len(timestamps)):
        while _to_seconds(timestamps[j] - timestamps[i]) > window.total_seconds():
            i += 1
        if (j - i + 1) > best_count:
            best_count = j - i + 1
            best_start = i
    if best_count == 0:
        return set()
    # Re-find the window
    i = best_start
    anchor = timestamps[best_start]
    return {
        post_ids[k] for k in range(best_start, len(timestamps))
        if _to_seconds(timestamps[k] - anchor) <= window.total_seconds()
    }


def _compute_first_posters(
    cluster_df: pd.DataFrame,
    near_dup_groups: list[list[str]],
    full_df: pd.DataFrame,
) -> list[str]:
    """Return up to 3 accounts: earliest authors of repost_of targets or dup-group roots."""
    pid_to_ts = dict(zip(cluster_df["post_id"], cluster_df["timestamp"]))
    pid_to_acc = dict(zip(cluster_df["post_id"], cluster_df["account_id"]))
    full_pid_to_acc = dict(zip(full_df["post_id"], full_df["account_id"]))

    candidates: dict[str, object] = {}  # account_id → earliest timestamp

    # Authors of repost_of targets
    for _, row in cluster_df.iterrows():
        orig = row.get("repost_of")
        if orig:
            orig_acc = full_pid_to_acc.get(orig)
            if orig_acc:
                # Use timestamp of the original post if we have it, else row ts
                orig_ts = full_df[full_df["post_id"] == orig]["timestamp"]
                ts = orig_ts.iloc[0] if not orig_ts.empty else row["timestamp"]
                if orig_acc not in candidates or ts < candidates[orig_acc]:
                    candidates[orig_acc] = ts

    # Authors of first post in each near-dup group
    for group in near_dup_groups:
        group_rows = [(pid, pid_to_ts[pid], pid_to_acc[pid])
                      for pid in group if pid in pid_to_ts]
        if group_rows:
            group_rows.sort(key=lambda x: x[1])
            first_acc = group_rows[0][2]
            ts = group_rows[0][1]
            if first_acc not in candidates or ts < candidates[first_acc]:
                candidates[first_acc] = ts

    sorted_fps = sorted(candidates, key=lambda a: candidates[a])
    return sorted_fps[:3]


def _compute_top_amplifiers(
    cluster_df: pd.DataFrame,
    near_dup_groups: list[list[str]],
    full_df: pd.DataFrame,
) -> list[str]:
    """Return top 5 accounts by reposts received + copies of their text."""
    from collections import Counter
    full_pid_to_acc = dict(zip(full_df["post_id"], full_df["account_id"]))
    scores: Counter = Counter()

    # Reposts received
    for _, row in cluster_df.iterrows():
        orig = row.get("repost_of")
        if orig:
            orig_acc = full_pid_to_acc.get(orig)
            if orig_acc:
                scores[orig_acc] += 1

    # Text copies received: author of first post in each dup group gets +len(group)-1
    pid_to_acc = dict(zip(cluster_df["post_id"], cluster_df["account_id"]))
    pid_to_ts = dict(zip(cluster_df["post_id"], cluster_df["timestamp"]))
    for group in near_dup_groups:
        group_rows = [(pid, pid_to_ts[pid], pid_to_acc[pid])
                      for pid in group if pid in pid_to_ts]
        if group_rows:
            group_rows.sort(key=lambda x: x[1])
            scores[group_rows[0][2]] += len(group_rows) - 1

    return [acc for acc, _ in scores.most_common(5)]


def _iso(dt: object) -> str:
    """Return an IST ISO-8601 string from a datetime."""
    from datetime import datetime, timezone, timedelta
    _IST = timezone(timedelta(hours=5, minutes=30))
    if not isinstance(dt, datetime):
        return str(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_IST)
    return dt.isoformat()
