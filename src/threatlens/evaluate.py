"""Evaluation against the answer key (PLAN.md section 12).

Per answer-key group: account precision / recall / F1 of the best-overlap
campaign, predicted vs true label, predicted vs expected state, expected
incidents found, detection lag (detected_at - first campaign post, minutes).
Overall: mean F1, label accuracy, state accuracy, "D1 decoy not escalated",
plus false-alarm campaigns (campaigns that match no answer-key group).
"""
from __future__ import annotations

from datetime import datetime

from threatlens.correlation import STATE_RANK


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def evaluate(result: dict, answer_key: dict) -> dict:
    campaigns = result.get("campaigns", [])
    rows, matched = [], set()
    for group, truth in answer_key.items():
        if not truth.get("expected_state"):
            continue  # individual (non-campaign) violations are scored per post, not here
        true_acc = set(truth["account_ids"])
        best = max(campaigns, key=lambda c: len(true_acc & set(c["_cluster"]["account_ids"])), default=None)
        if best is None or not true_acc & set(best["_cluster"]["account_ids"]):
            rows.append({"group": group, "campaign": None, "precision": 0.0, "recall": 0.0, "f1": 0.0,
                         "true_label": truth["type"], "pred_label": None, "label_ok": False,
                         "expected_state": truth["expected_state"], "pred_state": None, "state_ok": False,
                         "expected_incidents": truth["expected_incidents"], "incidents_found": False,
                         "detection_lag_min": None})
            continue
        matched.add(best["campaign_id"])
        pred_acc = set(best["_cluster"]["account_ids"])
        tp = len(true_acc & pred_acc)
        p, r = tp / len(pred_acc), tp / len(true_acc)
        found = {m["incident_id"] for m in best["offline"]["matches"]}
        first_post = min(_dt(best["_cluster"]["start"]), *[_dt(e["t"]) for e in best["timeline"]
                                                          if e["type"] == "FIRST_POST"])
        rows.append({
            "group": group, "campaign": best["campaign_id"],
            "precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3),
            "true_label": truth["type"], "pred_label": best["label"], "label_ok": best["label"] == truth["type"],
            "expected_state": truth["expected_state"], "pred_state": best["state"],
            "state_ok": best["state"] == truth["expected_state"],
            "expected_incidents": truth["expected_incidents"],
            "incidents_found": set(truth["expected_incidents"]) <= found,
            "detection_lag_min": round((_dt(best["_cluster"]["detected_at"]) - first_post).total_seconds() / 60, 1),
        })
    n = len(rows) or 1
    decoy = next((r for r in rows if r["group"] == "D1"), None)
    false_alarms = [c["campaign_id"] for c in campaigns if c["campaign_id"] not in matched]
    return {
        "per_group": rows,
        "overall": {
            "mean_f1": round(sum(r["f1"] for r in rows) / n, 3),
            "label_accuracy": round(sum(r["label_ok"] for r in rows) / n, 3),
            "state_accuracy": round(sum(r["state_ok"] for r in rows) / n, 3),
            "incidents_found": round(sum(r["incidents_found"] for r in rows) / n, 3),
            "d1_decoy_not_escalated": bool(decoy and decoy["pred_state"]
                                           and STATE_RANK[decoy["pred_state"]] <= STATE_RANK["COORDINATED"]),
            "false_alarm_campaigns": false_alarms,
            "mean_detection_lag_min": round(sum(r["detection_lag_min"] or 0 for r in rows) / n, 1),
        },
    }
