"""
Build batter-game labeled datasets for the hitting prop model.

Usage:
    cd backend
    python -m train.build_hitting_dataset

    Optional flags:
      --train-seasons 2016 2017 2018 2019 2021 2022 2023 2024
      --test-seasons  2025
      --min-games     20

Output:
    artifacts/hitting_train.parquet   <- model trains on this
    artifacts/hitting_test.parquet    <- backtest tests on this (2025)
    artifacts/hitting_dataset_summary.json

Runtime: ~30-60 min first run (Statcast pulled month by month, cached in
         artifacts/hitting_cache/).  Subsequent runs use the cache and finish
         in 2-3 min.

Each row = one batter-game with:
  - target: hits_in_game (integer)
  - all HITTING_FEATURE_COLS computed from strictly prior data (no leakage)
  - metadata: batter_id, batter_name, game_date, game_pk, season
"""
import sys
import json
import time
import calendar
import argparse
import warnings
from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.hitting import HITTING_FEATURE_COLS

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR  = Path("artifacts")
HITTING_CACHE = ARTIFACT_DIR / "hitting_cache"
TRAIN_OUT     = ARTIFACT_DIR / "hitting_train.parquet"
TEST_OUT      = ARTIFACT_DIR / "hitting_test.parquet"
SUMMARY_OUT   = ARTIFACT_DIR / "hitting_dataset_summary.json"

# Statcast columns we actually need — keeps memory small
_SC_COLS = [
    "game_date", "game_pk",
    "batter", "pitcher",
    "events",
    "stand",           # batter handedness (L/R/S)
    "p_throws",        # pitcher handedness (L/R)
    "launch_speed",
    "launch_angle",
    "estimated_ba_using_speedangle",
    "estimated_woba_using_speedangle",
    "barrel",
    "home_team",
    "away_team",
    "inning_topbot",
    "at_bat_number",
]

_HIT_EVENTS = frozenset(["single", "double", "triple", "home_run"])
_NON_AB     = frozenset([
    "walk", "intent_walk", "hit_by_pitch",
    "sac_fly", "sac_bunt", "sac_fly_double_play", "sac_bunt_double_play",
    "catcher_interf",
])


# ---------------------------------------------------------------------------
# Statcast pull + cache
# ---------------------------------------------------------------------------

def _load_sc_month(year: int, month: int) -> pd.DataFrame:
    """Load one month of Statcast, cached as parquet in hitting_cache/."""
    HITTING_CACHE.mkdir(parents=True, exist_ok=True)
    path = HITTING_CACHE / f"sc_{year}_{month:02d}.parquet"

    if path.exists():
        return pd.read_parquet(path)

    today = date.today()
    if date(year, month, 1) > today:
        return pd.DataFrame(columns=_SC_COLS)

    from pybaseball import statcast
    _, last_day = calendar.monthrange(year, month)
    start = f"{year}-{month:02d}-01"
    end   = f"{year}-{month:02d}-{last_day:02d}"

    print(f"    Fetching Statcast {start} → {end}...", end=" ", flush=True)
    try:
        df = statcast(start, end, parallel=False)
        if df.empty:
            result = pd.DataFrame(columns=_SC_COLS)
        else:
            keep = [c for c in _SC_COLS if c in df.columns]
            result = df[keep].copy()
            result["game_date"] = pd.to_datetime(result["game_date"])
        result.to_parquet(path, index=False)
        print(f"{len(result):,} pitches")
        return result
    except Exception as e:
        print(f"SKIP ({e})")
        return pd.DataFrame(columns=_SC_COLS)


def pull_statcast_seasons(seasons: list[int]) -> pd.DataFrame:
    """Pull and concatenate Statcast for multiple full seasons."""
    parts = []
    for year in seasons:
        months = range(7, 10) if year == 2020 else range(3, 11)
        for month in months:
            chunk = _load_sc_month(year, month)
            if not chunk.empty:
                parts.append(chunk)
    if not parts:
        return pd.DataFrame(columns=_SC_COLS)
    df = pd.concat(parts, ignore_index=True)
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df


# ---------------------------------------------------------------------------
# Aggregate raw Statcast → batter-game level
# ---------------------------------------------------------------------------

def aggregate_batter_games(sc: pd.DataFrame) -> pd.DataFrame:
    """
    One row per (batter, game_date, game_pk).
    Aggregates hits, PA/AB, and contact quality metrics.
    """
    if sc.empty:
        return pd.DataFrame()

    # PA-ending rows only (events is non-null)
    pa = sc[sc["events"].notna()].copy()
    if pa.empty:
        return pd.DataFrame()

    pa["is_hit"]      = pa["events"].isin(_HIT_EVENTS).fillna(False).astype(np.int8)
    pa["is_ab"]       = (~pa["events"].isin(_NON_AB)).fillna(False).astype(np.int8)
    pa["is_home"]     = (pa["inning_topbot"] == "Bot").fillna(False).astype(np.int8)
    pa["is_hard_hit"] = (pa["launch_speed"] >= 95).fillna(False).astype(np.int8)
    pa["is_sweet"]    = (
        (pa["launch_angle"] >= 8) & (pa["launch_angle"] <= 32)
    ).fillna(False).astype(np.int8)
    pa["has_contact"] = pa["launch_speed"].notna().astype(np.int8)

    grp = pa.groupby(["batter", "game_date", "game_pk"], sort=False)

    hits         = grp["is_hit"].sum()
    ab           = grp["is_ab"].sum()
    n_pa         = grp["is_hit"].count()
    n_contact    = grp["has_contact"].sum()
    hard_hit_sum = grp["is_hard_hit"].sum()
    sweet_sum    = grp["is_sweet"].sum()
    ev_sum       = grp["launch_speed"].sum()
    xba_mean     = grp["estimated_ba_using_speedangle"].mean() \
                   if "estimated_ba_using_speedangle" in pa.columns else None
    xwoba_mean   = grp["estimated_woba_using_speedangle"].mean() \
                   if "estimated_woba_using_speedangle" in pa.columns else None

    if "barrel" in pa.columns:
        barrel_sum = grp["barrel"].sum()
    else:
        barrel_sum = None

    result = pd.DataFrame({
        "hits":       hits,
        "ab":         ab,
        "pa":         n_pa,
        "n_contact":  n_contact,
    }).reset_index()

    result["hard_hit_pct"]   = hard_hit_sum.values / np.where(n_contact.values > 0, n_contact.values, np.nan)
    result["sweet_spot_pct"] = sweet_sum.values / np.where(n_contact.values > 0, n_contact.values, np.nan)
    result["avg_exit_velo"]  = ev_sum.values / np.where(n_contact.values > 0, n_contact.values, np.nan)

    if barrel_sum is not None:
        result["barrel_rate"] = barrel_sum.values / np.where(n_contact.values > 0, n_contact.values, np.nan)
    else:
        result["barrel_rate"] = np.nan

    if xba_mean is not None:
        result["xba"] = xba_mean.values
    else:
        result["xba"] = np.nan

    if xwoba_mean is not None:
        result["xwoba"] = xwoba_mean.values
    else:
        result["xwoba"] = np.nan

    # Majority-vote pitcher handedness and batter stance per game
    p_throws = pa.groupby(["batter", "game_date", "game_pk"])["p_throws"].agg(
        lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan
    ).reset_index()
    stand = pa.groupby(["batter", "game_date", "game_pk"])["stand"].agg(
        lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan
    ).reset_index()
    is_home = pa.groupby(["batter", "game_date", "game_pk"])["is_home"].first().reset_index()
    home_team = pa.groupby(["batter", "game_date", "game_pk"])["home_team"].first().reset_index()
    # Primary opposing pitcher (earliest at_bat_number = starter)
    if "at_bat_number" in pa.columns:
        pitcher = (
            pa.sort_values("at_bat_number")
            .groupby(["batter", "game_date", "game_pk"])["pitcher"]
            .first()
            .reset_index()
        )
    else:
        pitcher = pa.groupby(["batter", "game_date", "game_pk"])["pitcher"].first().reset_index()

    for extra in [p_throws, stand, is_home, home_team, pitcher]:
        key = [c for c in extra.columns if c not in result.columns or c in ["batter", "game_date", "game_pk"]]
        result = result.merge(extra, on=["batter", "game_date", "game_pk"], how="left")

    return result


# ---------------------------------------------------------------------------
# Aggregate Statcast → pitcher-game level (for opponent quality features)
# ---------------------------------------------------------------------------

def aggregate_pitcher_games(sc: pd.DataFrame) -> pd.DataFrame:
    """
    One row per (pitcher, game_date) with K rate, hard_hit% allowed, xBA allowed.
    Used to attach opponent quality features to batter rows.
    """
    if sc.empty:
        return pd.DataFrame()

    pa = sc[sc["events"].notna()].copy()
    if pa.empty:
        return pd.DataFrame()

    pa["is_k"]        = (pa["events"] == "strikeout").fillna(False).astype(np.int8)
    pa["is_hard_hit"] = (pa["launch_speed"] >= 95).fillna(False).astype(np.int8)
    pa["has_contact"] = pa["launch_speed"].notna().astype(np.int8)

    grp = pa.groupby(["pitcher", "game_date"], sort=False)

    n_bf      = grp["is_k"].count()
    k_sum     = grp["is_k"].sum()
    hh_sum    = grp["is_hard_hit"].sum()
    con_sum   = grp["has_contact"].sum()

    result = pd.DataFrame({
        "bf":         n_bf,
        "k_sum":      k_sum,
        "hh_sum":     hh_sum,
        "contact_sum": con_sum,
    }).reset_index()

    if "estimated_ba_using_speedangle" in pa.columns:
        xba_mean = grp["estimated_ba_using_speedangle"].mean().reset_index()
        result = result.merge(
            xba_mean.rename(columns={"estimated_ba_using_speedangle": "xba_allowed"}),
            on=["pitcher", "game_date"], how="left"
        )
    else:
        result["xba_allowed"] = np.nan

    result["k_pct"]           = result["k_sum"] / result["bf"].replace(0, np.nan)
    result["hard_hit_allowed"] = result["hh_sum"] / result["contact_sum"].replace(0, np.nan)

    return result[["pitcher", "game_date", "k_pct", "hard_hit_allowed", "xba_allowed", "bf"]]


# ---------------------------------------------------------------------------
# Park factors
# ---------------------------------------------------------------------------

def compute_park_factors(game_df: pd.DataFrame) -> dict:
    """
    Compute hits-park factor per home_team: ratio of H/PA to league average.
    Returns {team_abbr: park_factor}.  League average = 1.0.
    """
    if game_df.empty or "home_team" not in game_df.columns:
        return {}

    df = game_df[game_df["pa"] > 0].copy()
    league_h_per_pa = df["hits"].sum() / df["pa"].sum()
    if league_h_per_pa == 0:
        return {}

    pf = {}
    for team, grp in df.groupby("home_team"):
        if len(grp) < 200:
            continue
        team_h_per_pa = grp["hits"].sum() / grp["pa"].sum()
        pf[str(team)] = round(team_h_per_pa / league_h_per_pa, 4)

    return pf


# ---------------------------------------------------------------------------
# Rolling feature builder
# ---------------------------------------------------------------------------

def build_rolling_features(
    batter_id: int,
    batter_history: pd.DataFrame,
    pitcher_game_df: pd.DataFrame,
    park_factors: dict,
    target_row: pd.Series,
    min_prior_games: int = 7,
) -> dict | None:
    """
    Given a batter's game history STRICTLY BEFORE target_row's game_date,
    compute all HITTING_FEATURE_COLS.  Returns None if insufficient history.
    """
    gd = pd.to_datetime(target_row["game_date"])
    prior = batter_history[batter_history["game_date"] < gd].sort_values("game_date")

    if len(prior) < min_prior_games:
        return None

    def h_per_pa(df):
        total_pa = df["pa"].sum()
        return df["hits"].sum() / total_pa if total_pa > 0 else np.nan

    last7   = prior.tail(7)
    last14  = prior.tail(14)
    last30  = prior.tail(30)
    last60  = prior.tail(60)
    season_df = prior[prior["game_date"].dt.year == gd.year]

    row = {
        "h_per_pa_last7":   h_per_pa(last7),
        "h_per_pa_last14":  h_per_pa(last14),
        "h_per_pa_last30":  h_per_pa(last30),
        "h_per_pa_season":  h_per_pa(season_df) if not season_df.empty else h_per_pa(last30),
        # Contact quality rolling 30
        "barrel_rate_last30":    last30["barrel_rate"].mean(),
        "hard_hit_pct_last30":   last30["hard_hit_pct"].mean(),
        "xba_last30":            last30["xba"].mean(),
        "avg_exit_velo_last30":  last30["avg_exit_velo"].mean(),
        "sweet_spot_pct_last30": last30["sweet_spot_pct"].mean(),
        # PA per game (lineup spot proxy)
        "pa_per_game_last14":    last14["pa"].mean(),
    }

    # Platoon split: H/PA vs today's pitcher handedness over last 60 days
    p_hand = target_row.get("p_throws", np.nan)
    if pd.notna(p_hand):
        vs_hand = last60[last60["p_throws"] == p_hand]
        row["h_per_pa_vs_hand_last60"] = h_per_pa(vs_hand) if not vs_hand.empty else row["h_per_pa_last30"]
    else:
        row["h_per_pa_vs_hand_last60"] = row["h_per_pa_last30"]

    # Opponent pitcher quality — rolling 5 starts before this game
    opp_pitcher = target_row.get("pitcher", np.nan)
    if pd.notna(opp_pitcher) and not pitcher_game_df.empty:
        opp_hist = pitcher_game_df[
            (pitcher_game_df["pitcher"] == opp_pitcher) &
            (pitcher_game_df["game_date"] < gd)
        ].tail(5)
        if not opp_hist.empty:
            row["opp_k_pct"]              = opp_hist["k_pct"].mean()
            row["opp_hard_hit_pct_allowed"] = opp_hist["hard_hit_allowed"].mean()
            row["opp_xba_allowed"]        = opp_hist["xba_allowed"].mean()
        else:
            row["opp_k_pct"]              = np.nan
            row["opp_hard_hit_pct_allowed"] = np.nan
            row["opp_xba_allowed"]        = np.nan
    else:
        row["opp_k_pct"]              = np.nan
        row["opp_hard_hit_pct_allowed"] = np.nan
        row["opp_xba_allowed"]        = np.nan

    # Park factor
    home_team = target_row.get("home_team", "")
    row["park_factor"] = park_factors.get(str(home_team), 1.0)

    # Home/away
    row["is_home"] = float(target_row.get("is_home", 0))

    return row


# ---------------------------------------------------------------------------
# Main dataset builder
# ---------------------------------------------------------------------------

def build_dataset(
    seasons: list[int],
    min_games: int = 20,
    prior_season: bool = True,
) -> pd.DataFrame:
    """
    Build labeled batter-game rows for the given seasons.
    Pulls one extra prior season for rolling context if prior_season=True.
    """
    pull_seasons = seasons.copy()
    if prior_season and min(seasons) > 2016:
        pull_seasons = [min(seasons) - 1] + pull_seasons

    print(f"Pulling Statcast for seasons: {pull_seasons}")
    sc = pull_statcast_seasons(pull_seasons)
    if sc.empty:
        print("No Statcast data pulled.")
        return pd.DataFrame()

    print(f"Total pitches loaded: {len(sc):,}")

    print("Aggregating batter-game rows...")
    game_df = aggregate_batter_games(sc)
    print(f"Batter-game rows: {len(game_df):,}")

    print("Aggregating pitcher-game rows...")
    pitcher_df = aggregate_pitcher_games(sc)
    print(f"Pitcher-game rows: {len(pitcher_df):,}")

    print("Computing park factors...")
    park_factors = compute_park_factors(game_df)
    print(f"Park factors computed for {len(park_factors)} parks")

    # Filter to target seasons only (prior season was just for rolling context)
    game_df["game_date"] = pd.to_datetime(game_df["game_date"])
    target_game_df = game_df[game_df["game_date"].dt.year.isin(seasons)].copy()
    print(f"Target-season batter-game rows: {len(target_game_df):,}")

    rows = []
    batters = target_game_df["batter"].unique()
    print(f"Building rolling features for {len(batters):,} unique batters...")

    for i, batter_id in enumerate(batters):
        batter_games = game_df[game_df["batter"] == batter_id].sort_values("game_date")
        target_games = target_game_df[target_game_df["batter"] == batter_id]

        # Filter to batters with enough games in target seasons
        if len(target_games) < min_games:
            continue

        for _, trow in target_games.iterrows():
            feats = build_rolling_features(
                batter_id, batter_games, pitcher_df, park_factors, trow
            )
            if feats is None:
                continue

            feats["batter_id"]   = int(batter_id)
            feats["game_date"]   = trow["game_date"]
            feats["game_pk"]     = int(trow.get("game_pk", 0))
            feats["season"]      = int(trow["game_date"].year)
            feats["hits_in_game"] = int(trow["hits"])
            rows.append(feats)

        if (i + 1) % 100 == 0 or i == len(batters) - 1:
            print(f"  [{i+1}/{len(batters)}] {len(rows):,} rows so far")

    if not rows:
        print("No rows built.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    print(f"\nFinal dataset: {len(df):,} rows, {df['batter_id'].nunique()} batters")
    print(f"Target distribution — hits_in_game:")
    print(f"  mean: {df['hits_in_game'].mean():.3f}")
    print(f"  std:  {df['hits_in_game'].std():.3f}")
    print(f"  0H:   {(df['hits_in_game'] == 0).mean():.1%}")
    print(f"  1H:   {(df['hits_in_game'] == 1).mean():.1%}")
    print(f"  2H+:  {(df['hits_in_game'] >= 2).mean():.1%}")

    null_pct = df[HITTING_FEATURE_COLS].isnull().mean()
    if null_pct[null_pct > 0].any():
        print("\nNull rates by feature:")
        for col, rate in null_pct[null_pct > 0].items():
            print(f"  {col:<30} {rate:.1%}")

    return df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-seasons", nargs="+", type=int,
                        default=[2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024])
    parser.add_argument("--test-seasons",  nargs="+", type=int,
                        default=[2025])
    parser.add_argument("--min-games",     type=int, default=20)
    parser.add_argument("--test-only",     action="store_true")
    parser.add_argument("--train-out",     type=str, default=None)
    parser.add_argument("--test-out",      type=str, default=None)
    args = parser.parse_args()

    ARTIFACT_DIR.mkdir(exist_ok=True)
    t0 = time.time()

    train_out = Path(args.train_out) if args.train_out else TRAIN_OUT
    test_out  = Path(args.test_out)  if args.test_out  else TEST_OUT

    if not args.test_only:
        print("=== Building TRAIN dataset ===")
        df_train = build_dataset(args.train_seasons, args.min_games)
        if not df_train.empty:
            df_train.to_parquet(train_out, index=False)
            print(f"Train data saved: {train_out}  ({len(df_train):,} rows)")

    print("\n=== Building TEST dataset ===")
    df_test = build_dataset(args.test_seasons, args.min_games, prior_season=True)
    if not df_test.empty:
        df_test.to_parquet(test_out, index=False)
        print(f"Test data saved: {test_out}  ({len(df_test):,} rows)")

    summary = {
        "train_seasons": args.train_seasons,
        "test_seasons":  args.test_seasons,
        "train_rows":    int(len(df_train)) if not args.test_only and "df_train" in dir() else 0,
        "test_rows":     int(len(df_test)) if "df_test" in dir() else 0,
        "elapsed_min":   round((time.time() - t0) / 60, 1),
    }
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2))
    print(f"\nDone in {summary['elapsed_min']} min")
