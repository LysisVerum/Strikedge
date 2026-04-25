"""
Automatic K prediction log — no lines needed.

Every morning when the slate loads, predicted Ks are saved for every starter.
Each night check_results.py fills in actual Ks from box scores.
This gives a clean measure of raw model accuracy independent of betting lines.
"""
import json
from pathlib import Path

LOG_PATH = Path(__file__).parent.parent.parent / "artifacts" / "k_log.json"


def _load() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    return json.loads(LOG_PATH.read_text())


def _save(records: list[dict]):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(records, indent=2))


def log_slate_predictions(date_str: str, picks: list[dict]):
    """
    Called after slate loads. Saves predicted Ks for every starter.
    picks: the _store["picks"] list — each has pitcher_name, mlbam_id, predicted_ks.
    """
    records = _load()

    # Remove existing entries for today so re-refreshes don't duplicate
    records = [r for r in records if r.get("date") != date_str]

    for p in picks:
        records.append({
            "date":          date_str,
            "pitcher_name":  p["pitcher_name"],
            "mlbam_id":      p.get("mlbam_id") or 0,
            "predicted_ks":  p["predicted_ks"],
            "actual_ks":     None,
        })

    _save(records)
    return len(picks)


def update_actuals(date_str: str, results: list[dict]) -> int:
    """
    Fill in actual_ks for entries on date_str.
    results: [{"mlbam_id": int, "actual_ks": float}, ...]
    """
    records = _load()
    result_map = {r["mlbam_id"]: r["actual_ks"] for r in results}

    updated = 0
    for rec in records:
        if rec.get("date") != date_str:
            continue
        mid = rec.get("mlbam_id")
        if mid and mid in result_map:
            rec["actual_ks"] = result_map[mid]
            updated += 1

    _save(records)
    return updated


def get_accuracy_stats() -> dict:
    """
    Compute MAE, direction accuracy, and per-entry data for resolved predictions.
    """
    records = _load()
    resolved = [r for r in records if r.get("actual_ks") is not None]
    pending  = [r for r in records if r.get("actual_ks") is None]

    if not resolved:
        return {
            "resolved": 0,
            "pending":  len(pending),
            "mae":      None,
            "rmse":     None,
            "within_1": None,
            "within_2": None,
            "records":  records,
        }

    errors = [abs(r["predicted_ks"] - r["actual_ks"]) for r in resolved]
    sq_errors = [(r["predicted_ks"] - r["actual_ks"]) ** 2 for r in resolved]
    within_1 = sum(1 for e in errors if e <= 1.0) / len(errors) * 100
    within_2 = sum(1 for e in errors if e <= 2.0) / len(errors) * 100
    mae  = sum(errors) / len(errors)
    rmse = (sum(sq_errors) / len(sq_errors)) ** 0.5

    return {
        "resolved": len(resolved),
        "pending":  len(pending),
        "mae":      round(mae, 3),
        "rmse":     round(rmse, 3),
        "within_1": round(within_1, 1),
        "within_2": round(within_2, 1),
        "records":  records,
    }
