"""
Persistent prediction log stored at artifacts/prediction_log.json.

Each entry is written when lines are submitted, then updated nightly
when actual results are fetched from the MLB Stats API.
"""
import json
from datetime import date
from pathlib import Path

LOG_PATH     = Path(__file__).parent.parent.parent / "artifacts" / "prediction_log.json"
SKIPPED_PATH = Path(__file__).parent.parent.parent / "artifacts" / "skipped_log.json"


def _load(path: Path = LOG_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _save(records: list[dict], path: Path = LOG_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2))


def log_predictions(predictions: list[dict]):
    """
    Append today's predictions. Each dict should have at minimum:
        date, pitcher_name, mlbam_id, line, over_odds, line_source,
        predicted_ks, recommendation, edge, confidence, model_prob_over
    Sets actual_ks / outcome / pnl to null until results are checked.
    """
    records = _load()
    today = date.today().isoformat()

    existing_names = {
        r["pitcher_name"].lower()
        for r in records if r.get("date") == today
    }

    for p in predictions:
        if p["pitcher_name"].lower() in existing_names:
            for rec in records:
                if rec.get("date") == today and rec["pitcher_name"].lower() == p["pitcher_name"].lower():
                    rec.update({**p, "date": today, "actual_ks": None, "outcome": None, "pnl": None})
                    break
        else:
            records.append({
                **p,
                "date":      today,
                "actual_ks": None,
                "outcome":   None,
                "pnl":       None,
            })

    _save(records)
    return len(predictions)


def log_skipped(skipped: list[dict]):
    """
    Persist skipped predictions to skipped_log.json for post-game analysis.
    Each dict should include: pitcher_name, mlbam_id, line, predicted_ks,
    edge, confidence, recommendation, skip_reason.
    Resolves actual_ks after game day via update_skipped_results().
    """
    records = _load(SKIPPED_PATH)
    today = date.today().isoformat()

    existing_names = {
        r["pitcher_name"].lower()
        for r in records if r.get("date") == today
    }

    for s in skipped:
        if s["pitcher_name"].lower() not in existing_names:
            records.append({
                **s,
                "date":      today,
                "actual_ks": None,
            })

    _save(records, SKIPPED_PATH)
    return len(skipped)


def update_skipped_results(date_str: str, results: list[dict]):
    """Fill in actual_ks for skipped entries on date_str."""
    records = _load(SKIPPED_PATH)
    result_map = {r["mlbam_id"]: r["actual_ks"] for r in results}
    updated = 0
    for rec in records:
        if rec.get("date") != date_str:
            continue
        mlbam_id = rec.get("mlbam_id")
        if mlbam_id in result_map and rec.get("actual_ks") is None:
            rec["actual_ks"] = result_map[mlbam_id]
            updated += 1
    _save(records, SKIPPED_PATH)
    return updated


def get_skipped_record() -> list[dict]:
    return _load(SKIPPED_PATH)


def update_results(date_str: str, results: list[dict]):
    """
    Update entries for date_str with actual_ks / outcome / pnl.
    results: [{"mlbam_id": int, "actual_ks": float}, ...]
    """
    records = _load()
    result_map = {r["mlbam_id"]: r["actual_ks"] for r in results}

    updated = 0
    for rec in records:
        if rec.get("date") != date_str:
            continue
        mlbam_id = rec.get("mlbam_id")
        if mlbam_id not in result_map:
            continue

        actual = result_map[mlbam_id]
        rec["actual_ks"] = actual
        line = rec["line"]
        rec_side = rec["recommendation"]
        bet = rec.get("bet", 0) or 0

        if actual == line:
            rec["outcome"] = "PUSH"
            rec["pnl"] = 0.0
        elif rec_side == "OVER":
            odds = rec.get("bet_odds", rec.get("over_odds", -115))
            net = (100 / abs(odds)) if odds < 0 else (odds / 100)
            if actual > line:
                rec["outcome"] = "WIN"
                rec["pnl"] = round(bet * net, 2)
            else:
                rec["outcome"] = "LOSS"
                rec["pnl"] = -bet
        else:  # UNDER
            odds = rec.get("bet_odds", rec.get("under_odds", rec.get("over_odds", -115)))
            net = (100 / abs(odds)) if odds < 0 else (odds / 100)
            if actual < line:
                rec["outcome"] = "WIN"
                rec["pnl"] = round(bet * net, 2)
            else:
                rec["outcome"] = "LOSS"
                rec["pnl"] = -bet
        updated += 1

    _save(records)
    return updated


def delete_prediction(date_str: str, pitcher_name: str) -> bool:
    records = _load()
    before = len(records)
    records = [
        r for r in records
        if not (r.get("date") == date_str and r.get("pitcher_name", "").lower() == pitcher_name.lower())
    ]
    _save(records)
    return len(records) < before


def get_live_record() -> dict:
    """Return aggregate stats for all resolved predictions."""
    records = _load()
    resolved = [r for r in records if r.get("outcome") is not None]
    pending  = [r for r in records if r.get("outcome") is None]

    wins   = sum(1 for r in resolved if r["outcome"] == "WIN")
    losses = sum(1 for r in resolved if r["outcome"] == "LOSS")
    pushes = sum(1 for r in resolved if r["outcome"] == "PUSH")
    total_wagered = sum(r.get("bet", 0) or 0 for r in resolved)
    total_pnl     = sum(r.get("pnl", 0) or 0 for r in resolved)
    roi = (total_pnl / total_wagered * 100) if total_wagered > 0 else 0
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

    return {
        "bets":        len(resolved),
        "pending":     len(pending),
        "wins":        wins,
        "losses":      losses,
        "pushes":      pushes,
        "win_rate":    round(win_rate, 1),
        "roi":         round(roi, 1),
        "pnl":         round(total_pnl, 2),
        "wagered":     round(total_wagered, 2),
        "records":     records,
    }
