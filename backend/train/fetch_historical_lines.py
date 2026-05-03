"""
Fetch historical pitcher strikeout lines from The Odds API for every unique
date in the training data, then cache them to artifacts/historical_lines.json.

Usage:
    cd backend
    python -m train.fetch_historical_lines              # fetch all missing dates from test_data.parquet
    python -m train.fetch_historical_lines --season 2025            # fetch all 2025 game dates
    python -m train.fetch_historical_lines --season 2025 --max-dates 70  # fetch first 70 dates

WARNING: Historical endpoints cost 10 credits per call (10x live data).
Each date requires ~16 calls (1 event list + ~15 per-game odds requests).
A full season (~180 dates) = ~28,800 credits.
Run with --max-dates to spread the cost across multiple months.

This only needs to run once per date (already-fetched dates are skipped on resume).
"""
import sys
import json
import time
import argparse
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

DATA_PATH            = Path("artifacts/test_data.parquet")
OUT_PATH             = Path("artifacts/historical_lines.json")
CREDITS_PER_DATE_EST = 160   # 16 calls × 10 credits each (historical endpoint multiplier)


def _mlb_game_dates(season: int) -> list[str]:
    """Fetch all regular-season game dates for a given year from the free MLB Stats API."""
    print(f"Fetching {season} MLB schedule from Stats API...", flush=True)
    url = (
        f"https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&season={season}&gameType=R&fields=dates,date,games,gamePk"
    )
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read())
    dates = sorted({
        entry["date"]
        for entry in data.get("dates", [])
        if entry.get("games")
    })
    print(f"  {len(dates)} game dates found for {season}.")
    return dates


def run(max_dates: int | None = None, yes: bool = False, season: int | None = None):
    # Determine which dates to consider
    if season is not None:
        all_dates = _mlb_game_dates(season)
    else:
        if not DATA_PATH.exists():
            print(f"No training data at {DATA_PATH}. Run train.build_dataset first.")
            return
        df = pd.read_parquet(DATA_PATH).dropna(subset=["ks_per_start"])
        df["date"] = pd.to_datetime(df["date"])
        all_dates = sorted(df["date"].dt.strftime("%Y-%m-%d").unique())

    # Load existing cache so we can resume if interrupted
    existing: dict = {}
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text())

    missing = [d for d in all_dates if d not in existing]

    print(f"Total dates:           {len(all_dates)}")
    print(f"Already cached:        {len(existing)}")
    print(f"Remaining to fetch:    {len(missing)}")

    if not missing:
        print("All dates already cached — nothing to do.")
        return

    to_fetch = missing[:max_dates] if max_dates else missing
    est_credits = len(to_fetch) * CREDITS_PER_DATE_EST

    print(f"\nWill fetch:            {len(to_fetch)} dates")
    print(f"Estimated credit cost: ~{est_credits:,} credits  "
          f"({CREDITS_PER_DATE_EST} credits/date × {len(to_fetch)} dates)")
    if len(missing) > len(to_fetch):
        print(f"Remaining after this:  {len(missing) - len(to_fetch)} dates "
              f"(run again to continue)")

    if not yes:
        answer = input("\nProceed? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    from app.data.odds_api import get_historical_lines, get_credits_remaining

    for i, date_str in enumerate(to_fetch):
        print(f"  [{i+1}/{len(to_fetch)}] {date_str} ...", end=" ", flush=True)
        try:
            lines = get_historical_lines(date_str)
            existing[date_str] = lines
            remaining = get_credits_remaining()
            suffix = f"  (credits remaining: {remaining})" if remaining is not None else ""
            print(f"{len(lines)} lines{suffix}")
        except Exception as e:
            print(f"ERROR: {e}")
            existing[date_str] = {}

        # Save after every date so an interruption doesn't lose progress
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(existing, indent=2))
        time.sleep(1.0)  # 1s between dates to stay within rate limits

    print(f"\nDone. {len(existing)} total dates cached in {OUT_PATH}")
    remaining = get_credits_remaining()
    if remaining is not None:
        print(f"Credits remaining: {remaining}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-dates", type=int, default=None,
        help="Max number of new dates to fetch in this run (default: all missing)"
    )
    parser.add_argument(
        "--season", type=int, default=None,
        help="Fetch dates for a specific MLB season (e.g. 2025) via the free MLB schedule API"
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Skip confirmation prompt"
    )
    args = parser.parse_args()
    run(max_dates=args.max_dates, yes=args.yes, season=args.season)
