"""
Fetch actual strikeout results for yesterday's logged predictions.

Usage (run each night after games finish):
    cd backend
    python -m train.check_results

    # Or for a specific date:
    python -m train.check_results --date 2026-04-21
"""
import sys
import argparse
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data.prediction_log import get_live_record, update_results
from app.data.k_log import update_actuals, get_accuracy_stats


def fetch_actual_ks(date_str: str) -> list[dict]:
    """
    Pull actual strikeout totals for all starters on a given date
    from the MLB Stats API game feed.
    """
    import urllib.request
    import json

    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&hydrate=boxscore"
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read())

    results = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            game_pk = game.get("gamePk")
            if not game_pk:
                continue
            if game.get("status", {}).get("abstractGameState") != "Final":
                continue

            # Fetch boxscore for this game
            box_url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
            try:
                with urllib.request.urlopen(box_url, timeout=15) as br:
                    box = json.loads(br.read())
            except Exception as e:
                print(f"  [warn] boxscore {game_pk}: {e}")
                continue

            for side in ("home", "away"):
                team = box.get("teams", {}).get(side, {})
                pitchers = team.get("pitchers", [])
                players  = team.get("players", {})

                if not pitchers:
                    continue

                # First pitcher = starter
                starter_id = pitchers[0]
                player_key = f"ID{starter_id}"
                player     = players.get(player_key, {})
                stats      = player.get("stats", {}).get("pitching", {})
                ks         = stats.get("strikeOuts")

                if ks is not None:
                    results.append({
                        "mlbam_id":  starter_id,
                        "actual_ks": float(ks),
                    })

    return results


def run(date_str: str = None):
    if not date_str:
        date_str = (date.today() - timedelta(days=1)).isoformat()

    print(f"Checking results for {date_str}...")
    try:
        results = fetch_actual_ks(date_str)
        print(f"  Found {len(results)} starter results from MLB API.")
    except Exception as e:
        print(f"  Error fetching results: {e}")
        return

    updated_bets = update_results(date_str, results)
    updated_ks   = update_actuals(date_str, results)
    print(f"  Updated {updated_bets} bet predictions, {updated_ks} K predictions.")

    record = get_live_record()
    print(f"\nLive betting record: {record['wins']}W / {record['losses']}L / {record['pushes']}P")
    print(f"Win rate: {record['win_rate']}%  |  ROI: {record['roi']:+.1f}%  |  P&L: ${record['pnl']:+.2f}")

    acc = get_accuracy_stats()
    if acc["mae"] is not None:
        print(f"\nK prediction accuracy ({acc['resolved']} starts):")
        print(f"  MAE:      {acc['mae']} Ks")
        print(f"  RMSE:     {acc['rmse']} Ks")
        print(f"  Within 1K: {acc['within_1']}%")
        print(f"  Within 2K: {acc['within_2']}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None, help="Date to check (YYYY-MM-DD), defaults to yesterday")
    args = parser.parse_args()
    run(args.date)
