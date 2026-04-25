"""
Fetch historical pitcher strikeout lines from The Odds API for every unique
date in the training data, then cache them to artifacts/historical_lines.json.

Usage:
    cd backend
    python -m train.fetch_historical_lines              # fetch all missing dates
    python -m train.fetch_historical_lines --max-dates 20  # fetch at most 20 new dates

WARNING: Historical endpoints cost 10 credits per call (10x live data).
Each date requires ~16 calls (1 event list + ~15 per-game odds requests).
A full 2024 season (~150 dates) = ~24,000 credits.
Run with --max-dates to spread the cost across multiple days.

This only needs to run once per date (already-fetched dates are skipped on resume).
"""
import sys
import json
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

DATA_PATH            = Path("artifacts/test_data.parquet")
OUT_PATH             = Path("artifacts/historical_lines.json")
CREDITS_PER_DATE_EST = 160   # 16 calls × 10 credits each (historical endpoint multiplier)


def run(max_dates: int | None = None):
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

    print(f"Total test-set dates:  {len(all_dates)}")
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

    print(f"\nDone. {len(existing)}/{len(all_dates)} dates now cached in {OUT_PATH}")
    remaining = get_credits_remaining()
    if remaining is not None:
        print(f"Credits remaining: {remaining}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-dates", type=int, default=None,
        help="Max number of new dates to fetch in this run (default: all missing)"
    )
    args = parser.parse_args()
    run(max_dates=args.max_dates)
