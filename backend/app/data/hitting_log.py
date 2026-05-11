"""
Persistent prediction log for hitting props — stored at artifacts/hitting_prediction_log.json.
Mirrors prediction_log.py but tracks batter hits instead of pitcher strikeouts.
"""
import json
from datetime import date
from pathlib import Path

LOG_PATH     = Path(__file__).parent.parent.parent / "artifacts" / "hitting_prediction_log.json"
SKIPPED_PATH = Path(__file__).parent.parent.parent / "artifacts" / "hitting_skipped_log.json"


def _load(path: Path = LOG_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _save(records: list[dict], path: Path = LOG_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2))


def log_hitting_predictions(predictions: list[dict]) -> int:
    records = _load()
    today = date.today().isoformat()

    existing_names = {
        r["batter_name"].lower()
        for r in records if r.get("date") == today
    }

    for p in predictions:
        if p["batter_name"].lower() in existing_names:
            for rec in records:
                if rec.get("date") == today and rec["batter_name"].lower() == p["batter_name"].lower():
                    rec.update({**p, "date": today, "actual_hits": None, "outcome": None, "pnl": None})
                    break
        else:
            records.append({
                **p,
                "date":        today,
                "actual_hits": None,
                "outcome":     None,
                "pnl":         None,
            })

    _save(records)
    return len(predictions)


def log_hitting_skipped(skipped: list[dict]) -> int:
    records = _load(SKIPPED_PATH)
    today = date.today().isoformat()

    existing_names = {
        r["batter_name"].lower()
        for r in records if r.get("date") == today
    }

    for s in skipped:
        if s["batter_name"].lower() not in existing_names:
            records.append({
                **s,
                "date":        today,
                "actual_hits": None,
            })

    _save(records, SKIPPED_PATH)
    return len(skipped)


def update_hitting_results(date_str: str, results: list[dict]) -> int:
    """
    results: [{"mlbam_id": int, "actual_hits": float}, ...]
    Fills in actual_hits / outcome / pnl for resolved entries.
    """
    records = _load()
    result_map = {r["mlbam_id"]: r["actual_hits"] for r in results}

    updated = 0
    for rec in records:
        if rec.get("date") != date_str:
            continue
        mlbam_id = rec.get("mlbam_id")
        if mlbam_id not in result_map:
            continue

        actual = result_map[mlbam_id]
        rec["actual_hits"] = actual
        line    = rec["line"]
        rec_side = rec["recommendation"]
        bet      = rec.get("bet", 0) or 0

        # DK hit lines are half-integers; push is impossible
        if rec_side == "OVER":
            odds = rec.get("bet_odds", rec.get("over_odds", -115))
            net  = (100 / abs(odds)) if odds < 0 else (odds / 100)
            if actual > line:
                rec["outcome"] = "WIN"
                rec["pnl"]     = round(bet * net, 2)
            else:
                rec["outcome"] = "LOSS"
                rec["pnl"]     = -bet
        else:  # UNDER
            odds = rec.get("bet_odds", rec.get("under_odds", rec.get("over_odds", -115)))
            net  = (100 / abs(odds)) if odds < 0 else (odds / 100)
            if actual < line:
                rec["outcome"] = "WIN"
                rec["pnl"]     = round(bet * net, 2)
            else:
                rec["outcome"] = "LOSS"
                rec["pnl"]     = -bet
        updated += 1

    _save(records)
    return updated


def update_hitting_skipped_results(date_str: str, results: list[dict]) -> int:
    records = _load(SKIPPED_PATH)
    result_map = {r["mlbam_id"]: r["actual_hits"] for r in results}
    updated = 0
    for rec in records:
        if rec.get("date") != date_str:
            continue
        mlbam_id = rec.get("mlbam_id")
        if mlbam_id in result_map and rec.get("actual_hits") is None:
            rec["actual_hits"] = result_map[mlbam_id]
            updated += 1
    _save(records, SKIPPED_PATH)
    return updated


def get_hitting_skipped_record() -> list[dict]:
    records = _load(SKIPPED_PATH)
    for r in records:
        if r.get("actual_hits") is not None and r.get("predicted_hits") is not None:
            r["miss"] = round(r["actual_hits"] - r["predicted_hits"], 2)
        else:
            r["miss"] = None
    return records


def delete_hitting_prediction(date_str: str, batter_name: str) -> bool:
    records = _load()
    before = len(records)
    records = [
        r for r in records
        if not (r.get("date") == date_str and r.get("batter_name", "").lower() == batter_name.lower())
    ]
    _save(records)
    return len(records) < before


def get_hitting_live_record() -> dict:
    records = _load()
    resolved = [r for r in records if r.get("outcome") is not None]
    pending  = [r for r in records if r.get("outcome") is None]

    wins   = sum(1 for r in resolved if r["outcome"] == "WIN")
    losses = sum(1 for r in resolved if r["outcome"] == "LOSS")
    pushes = sum(1 for r in resolved if r["outcome"] == "PUSH")
    total_wagered = sum(r.get("bet", 0) or 0 for r in resolved)
    total_pnl     = sum(r.get("pnl", 0) or 0 for r in resolved)
    roi      = (total_pnl / total_wagered * 100) if total_wagered > 0 else 0
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

    return {
        "bets":      len(resolved),
        "pending":   len(pending),
        "wins":      wins,
        "losses":    losses,
        "pushes":    pushes,
        "win_rate":  round(win_rate, 1),
        "roi":       round(roi, 1),
        "pnl":       round(total_pnl, 2),
        "wagered":   round(total_wagered, 2),
        "records":   records,
    }
