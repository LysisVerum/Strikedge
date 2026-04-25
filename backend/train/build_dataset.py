"""
Build labeled training and test datasets from MLB Stats API + Statcast.

Usage:
    cd backend
    python -m train.build_dataset

    Optional flags:
      --train-seasons 2022 2023   (default: 2022 2023)
      --test-seasons  2024        (default: 2024)
      --min-gs 8

Output:
    artifacts/train_data.parquet   <- model trains on this (2022-2023)
    artifacts/test_data.parquet    <- backtest tests on this (2024, never seen during training)
    artifacts/training_data_summary.json

Runtime: ~20-40 min on first run (Statcast pulls are cached month-by-month
         in artifacts/statcast_cache/ so subsequent runs are fast).
"""
import sys
import json
import time
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data.mlb_api import get_season_sp_ids, get_pitcher_multi_season_log, get_team_k_pct
from app.data.statcast_agg import get_pitcher_statcast_range, pitch_mix_features, get_team_pitch_k_pct, compute_matchup_k_score
from app.data.pipeline import build_training_row
from app.data.umpire import _load_cache as load_umpire_cache
from app.data.lineup import get_season_batter_k_pcts, get_season_lineups, compute_lineup_k_pct
from app.models.features import FEATURE_COLS

ARTIFACT_DIR    = Path("artifacts")
TRAIN_PARQUET   = ARTIFACT_DIR / "train_data.parquet"
TEST_PARQUET    = ARTIFACT_DIR / "test_data.parquet"
OUT_SUMMARY     = ARTIFACT_DIR / "training_data_summary.json"


def build_dataset(seasons: list[int], min_gs: int = 8) -> pd.DataFrame:
    ARTIFACT_DIR.mkdir(exist_ok=True)
    rows = []
    total_pitchers = 0

    for season in seasons:
        print(f"\n=== Season {season} ===")

        # 1. Get all SPs this season
        sp_list = get_season_sp_ids(season, min_gs=min_gs)
        print(f"  SPs with >= {min_gs} GS: {len(sp_list)}")

        # 2. Pre-fetch prior season team K%, pitch-type K%, batter K%, and lineups
        prior_season_k       = get_team_k_pct(season - 1)
        prior_team_pitch_k   = get_team_pitch_k_pct(season - 1)
        prior_batter_k_pcts  = get_season_batter_k_pcts(season - 1)
        season_lineups       = get_season_lineups(season)
        print(f"  Prior season team K% fetched for {len(prior_season_k)} teams")
        print(f"  Prior season batter K% fetched for {len(prior_batter_k_pcts)} batters")
        print(f"  Season lineups fetched for {len(season_lineups)} games")

        # Build date+game_pk → umpire_id lookup from cache
        ump_cache = load_umpire_cache()
        # {(date, game_pk_str): umpire_id}
        ump_by_game = {
            (v["date"], k): v["umpire_id"]
            for k, v in ump_cache.get("games", {}).items()
        }

        for i, sp in enumerate(sp_list):
            pid   = sp["mlbam_id"]
            name  = sp["full_name"]

            if not pid:
                continue

            try:
                # 3. Game log (this season + prior for rolling continuity)
                prior = [season - 1] if season > 2019 else []
                full_log = get_pitcher_multi_season_log(pid, prior + [season])
                season_games = [g for g in full_log if g.get("season") == season and g.get("is_start", 1)]

                if len(season_games) < min_gs:
                    continue

                # 4. Load Statcast for prior season + current — sliced per game below
                sc_start = f"{season - 1}-04-01"
                sc_end   = f"{season}-10-01"
                sc_df_full = get_pitcher_statcast_range(pid, sc_start, sc_end)
                if not sc_df_full.empty:
                    sc_df_full = sc_df_full.copy()
                    sc_df_full["game_date"] = pd.to_datetime(sc_df_full["game_date"])

                # 5. Build one row per game start (using only prior history as features)
                # Skip short outings (openers, injury exits) — IP < 3 adds noise
                for game in [g for g in season_games if g.get("IP", 5.0) >= 3.0]:
                    game_date = game["date"]

                    # Pitch mix: only pitches thrown BEFORE this game (no future data)
                    if not sc_df_full.empty:
                        sc_prior = sc_df_full[sc_df_full["game_date"] < pd.Timestamp(game_date)]
                        mix = pitch_mix_features(sc_prior)
                    else:
                        mix = pitch_mix_features(pd.DataFrame())

                    # Matchup score: pitcher pitch mix × opponent K% vs each pitch type
                    opp_abbr      = game.get("opponent_name", "")[:3].upper()
                    matchup_score = compute_matchup_k_score(mix, prior_team_pitch_k, opp_abbr)

                    # Lineup K rate: actual batters in this game × prior-season individual K rates
                    game_pk_int    = game.get("game_pk")
                    lineup_entry   = season_lineups.get(int(game_pk_int)) if game_pk_int else {}
                    is_home        = game.get("is_home", True)
                    opp_batter_ids = lineup_entry.get("away" if is_home else "home", [])
                    lineup_k_pct   = compute_lineup_k_pct(opp_batter_ids, prior_batter_k_pcts)

                    # Look up umpire from pre-built cache
                    game_pk   = str(game_pk_int or "")
                    ump_id    = ump_by_game.get((game["date"], game_pk))
                    row = build_training_row(
                        game, full_log, mix, prior_season_k,
                        umpire_id=ump_id,
                        matchup_k_score=matchup_score,
                        opp_lineup_k_pct=lineup_k_pct,
                    )
                    if row is not None:
                        row["pitcher_name"] = name
                        rows.append(row)

                total_pitchers += 1
                if (i + 1) % 20 == 0 or i == len(sp_list) - 1:
                    print(f"  [{i+1}/{len(sp_list)}] {name} — {len(rows)} rows so far")

            except KeyboardInterrupt:
                print("\nInterrupted — saving partial dataset...")
                break
            except Exception as e:
                print(f"  WARN {name}: {e}")
                continue

    df = pd.DataFrame(rows)
    print(f"\nTotal rows: {len(df)}")
    print(f"Pitchers: {total_pitchers}")
    print(f"Seasons: {seasons}")

    if not df.empty:
        print(f"\nTarget distribution:")
        print(f"  Mean: {df['ks_per_start'].mean():.2f}")
        print(f"  Std:  {df['ks_per_start'].std():.2f}")
        print(f"  Min:  {df['ks_per_start'].min():.0f}")
        print(f"  Max:  {df['ks_per_start'].max():.0f}")

        null_pct = df[FEATURE_COLS].isnull().mean()
        print(f"\nNull rates by feature:")
        for col, rate in null_pct[null_pct > 0].items():
            print(f"  {col:<25} {rate:.1%}")

        summary = {
            "n_rows": len(df),
            "n_pitchers": total_pitchers,
            "seasons": seasons,
            "target_mean": round(df["ks_per_start"].mean(), 3),
            "target_std":  round(df["ks_per_start"].std(), 3),
            "null_rates": {col: round(r, 3) for col, r in null_pct.items()},
        }
        OUT_SUMMARY.write_text(json.dumps(summary, indent=2))
        print(f"Summary saved: {OUT_SUMMARY}")

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-seasons", nargs="+", type=int, default=[2016, 2017, 2018, 2019, 2021, 2022, 2023])
    parser.add_argument("--test-seasons",  nargs="+", type=int, default=[2024])
    parser.add_argument("--min-gs",        type=int, default=8)
    args = parser.parse_args()

    t0 = time.time()

    print("=== Building TRAIN dataset ===")
    df_train = build_dataset(args.train_seasons, args.min_gs)
    if not df_train.empty:
        df_train.to_parquet(TRAIN_PARQUET, index=False)
        print(f"Train data saved: {TRAIN_PARQUET}  ({len(df_train):,} rows, seasons {args.train_seasons})")

    print("\n=== Building TEST dataset ===")
    df_test = build_dataset(args.test_seasons, args.min_gs)
    if not df_test.empty:
        df_test.to_parquet(TEST_PARQUET, index=False)
        print(f"Test data saved:  {TEST_PARQUET}  ({len(df_test):,} rows, seasons {args.test_seasons})")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed/60:.1f} min")
