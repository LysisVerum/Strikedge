"""
Build the profile-based training and test datasets.

Unlike build_dataset.py (which uses rolling windows), this builder anchors
every row to stable pitcher/hitter career profiles and computes a true
matchup score from pitcher arsenal × per-pitch-type lineup K rates.

Usage:
    cd backend
    python -m train.build_profile_dataset
    python -m train.build_profile_dataset --test-seasons 2025 --test-only

Output:
    artifacts/profile_train.parquet
    artifacts/profile_test_2025.parquet
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

from app.data.mlb_api import (
    get_season_sp_ids,
    get_pitcher_multi_season_log,
    get_team_k_pct,
)
from app.data.statcast_agg import (
    get_pitcher_statcast_range,
    pitch_mix_features,
    get_team_pitch_k_pct,
    compute_matchup_k_score,
)
from app.data.umpire import get_umpire_k_rate, LEAGUE_K_PCT
from app.data.lineup import get_season_batter_k_pcts, get_season_lineups
from app.data.player_profiles import (
    build_pitcher_profile,
    get_hitter_profile,
    pitcher_vs_lineup_k_score,
    _load_cache, _save_cache, HITTER_CACHE,
)
from app.models.features import PROFILE_FEATURE_COLS

ARTIFACT_DIR = Path("artifacts")
TRAIN_OUT    = ARTIFACT_DIR / "profile_train.parquet"
TEST_OUT_TPL = "profile_test_{season}.parquet"


# ---------------------------------------------------------------------------
# Pitcher snapshot profile (as-of a specific date, no future leakage)
# ---------------------------------------------------------------------------

def _pitcher_snapshot(mlbam_id: int, as_of_season: int, game_log: list[dict]) -> dict:
    """
    Build pitcher talent metrics from game log data available BEFORE as_of_season.
    Uses at most 3 prior seasons so old data doesn't dominate.
    """
    current_year = as_of_season
    prior_starts = [
        g for g in game_log
        if g.get("season", 0) < current_year
        and g.get("is_start", 1)
        and g.get("BF", 0) >= 9
    ]

    if not prior_starts:
        return {}

    # Recency weights: current-2 to current-1 weighted 3x, older 1x
    weighted_so = weighted_bf = weighted_bb = 0
    total_ip = total_starts = 0
    for g in prior_starts:
        w = 3 if g.get("season", 0) >= current_year - 2 else 1
        weighted_so += g["SO"] * w
        weighted_bf += g["BF"] * w
        weighted_bb += g.get("BB", 0) * w
        total_ip     += g.get("IP", 0)
        total_starts += 1

    career_k  = weighted_so / max(weighted_bf, 1)
    career_bb = weighted_bb / max(weighted_bf, 1)
    ip_start  = total_ip / max(total_starts, 1)

    return {
        "p_k_pct_career": round(career_k, 4),
        "p_bb_pct_career": round(career_bb, 4),
        "p_ip_per_start": round(ip_start, 2),
    }


def _pitcher_recent(game_log: list[dict], as_of_date: str) -> dict:
    """K rate over last 15 starts before this game (same-season context)."""
    past = [
        g for g in game_log
        if g["date"] < as_of_date and g.get("BF", 0) >= 9 and g.get("is_start", 1)
    ]
    last15 = past[-15:]
    if not last15:
        return {"p_k_pct_recent": np.nan, "p_form": np.nan, "p_fip": np.nan,
                "p_ip_per_start_recent": np.nan, "season_starts": 0.0}

    so15 = sum(g["SO"] for g in last15)
    bf15 = sum(g["BF"] for g in last15)
    bb15 = sum(g.get("BB", 0) for g in last15)
    hr15 = sum(g.get("HR", 0) for g in last15)
    ip15 = sum(g.get("IP", 0) for g in last15)
    k15  = so15 / max(bf15, 1)

    fip  = (13 * hr15 + 3 * bb15 - 2 * so15) / max(ip15, 1) + 3.10 if ip15 > 0 else np.nan
    season_year = int(as_of_date[:4])
    season_starts = float(len([g for g in past if g.get("season") == season_year]))

    return {
        "p_k_pct_recent":      round(k15, 4),
        "p_fip":               round(fip, 3),
        "p_ip_per_start_recent": round(ip15 / len(last15), 2),
        "season_starts":       season_starts,
    }


# ---------------------------------------------------------------------------
# Hitter profile snapshot (using prior-season individual rates)
# ---------------------------------------------------------------------------

def _build_lineup_features(
    lineup_ids: list[int],
    prior_batter_k_pcts: dict,
    hitter_profile_cache: dict,
    season: int,
) -> dict:
    """
    Compute lineup-level features using batter profiles.
    Falls back to team-average K rate when profile is unavailable.
    """
    k_pcts        = []
    chase_rates   = []
    contact_rates = []

    for bid in lineup_ids:
        # Try profile cache first
        profile = hitter_profile_cache.get(str(bid))
        if profile:
            k  = profile.get("career_k_pct_3yr") or profile.get("career_k_pct")
            cr = profile.get("chase_rate")
            ct = profile.get("contact_rate")
            if k:  k_pcts.append(k)
            if cr: chase_rates.append(cr)
            if ct: contact_rates.append(ct)
        else:
            # Fall back to season K rate
            k = prior_batter_k_pcts.get(bid)
            if k:
                k_pcts.append(k)

    return {
        "lineup_k_pct":      round(float(np.mean(k_pcts)),    4) if k_pcts        else 0.225,
        "lineup_chase_rate": round(float(np.mean(chase_rates)),4) if chase_rates   else np.nan,
        "lineup_contact_rate":round(float(np.mean(contact_rates)),4) if contact_rates else np.nan,
    }


# ---------------------------------------------------------------------------
# Statcast pitch quality for a pitcher as-of season start
# ---------------------------------------------------------------------------

def _pitcher_statcast_quality(mlbam_id: int, as_of_season: int) -> dict:
    """Pitch quality metrics from Statcast across 2 prior seasons."""
    _swinging = {"swinging_strike", "swinging_strike_blocked"}
    _called   = {"called_strike"}
    frames = []
    for s in [as_of_season - 2, as_of_season - 1]:
        if s < 2015:
            continue
        df = get_pitcher_statcast_range(mlbam_id, f"{s}-03-01", f"{s}-11-01")
        if not df.empty:
            frames.append(df)

    if not frames:
        return {}

    sc = pd.concat(frames, ignore_index=True)
    if sc.empty or len(sc) < 50:
        return {}

    total = len(sc)
    swings = sc["description"].isin({
        "swinging_strike","swinging_strike_blocked","foul","foul_tip",
        "hit_into_play","hit_into_play_no_out","hit_into_play_score"
    })
    whiff_rate = float(sc["description"].isin(_swinging).sum() / max(swings.sum(), 1))
    csw_rate   = float(sc["description"].isin(_swinging | _called).sum() / max(total, 1))

    # Fastball velocity
    ff = sc[sc["pitch_type"] == "FF"]["release_speed"].dropna()
    velo_ff = float(ff.mean()) if not ff.empty else np.nan

    # Offspeed usage (SL, CH, CU, ST, FS, KC)
    offspeed = {"SL", "CH", "CU", "ST", "FS", "KC", "SV"}
    pts = sc["pitch_type"].value_counts()
    offspeed_pct = float(pts[pts.index.isin(offspeed)].sum() / max(total, 1))

    return {
        "p_whiff_rate":   round(whiff_rate, 4),
        "p_csw_rate":     round(csw_rate, 4),
        "p_velo_ff":      round(velo_ff, 1) if not np.isnan(velo_ff) else np.nan,
        "p_offspeed_pct": round(offspeed_pct, 4),
    }


# ---------------------------------------------------------------------------
# Main dataset builder
# ---------------------------------------------------------------------------

def build_profile_dataset(seasons: list[int], min_gs: int = 8) -> pd.DataFrame:
    ARTIFACT_DIR.mkdir(exist_ok=True)
    rows = []

    # Load hitter profile cache (built from player_profiles.py)
    hitter_profile_cache = _load_cache(HITTER_CACHE)

    for season in seasons:
        print(f"\n=== Season {season} ===")
        sp_list = get_season_sp_ids(season, min_gs=min_gs)
        print(f"  SPs with >= {min_gs} GS: {len(sp_list)}")

        prior_k          = get_team_k_pct(season - 1)
        prior_batter_k   = get_season_batter_k_pcts(season - 1)
        prior_team_pitch = get_team_pitch_k_pct(season - 1)
        season_lineups   = get_season_lineups(season)
        print(f"  Prior team K% loaded: {len(prior_k)} teams")
        print(f"  Prior batter K% loaded: {len(prior_batter_k)} batters")

        from app.data.umpire import _load_cache as load_ump_cache
        ump_cache  = load_ump_cache()
        ump_by_game = {
            (v["date"], k): v["umpire_id"]
            for k, v in ump_cache.get("games", {}).items()
        }

        for i, sp in enumerate(sp_list):
            pid  = sp["mlbam_id"]
            name = sp["full_name"]
            if not pid:
                continue

            try:
                prior_seasons = [s for s in [season - 2, season - 1, season] if s >= 2015]
                full_log = get_pitcher_multi_season_log(pid, prior_seasons)
                season_games = [
                    g for g in full_log
                    if g.get("season") == season and g.get("is_start", 1)
                ]
                if len(season_games) < min_gs:
                    continue

                # Career snapshot (pre-season)
                career_snap = _pitcher_snapshot(pid, season, full_log)
                if not career_snap:
                    continue

                # Statcast quality (pre-season, 2 prior years)
                sc_quality = _pitcher_statcast_quality(pid, season)

                # Pitch mix for matchup score (Statcast prior to each game)
                sc_start = f"{season - 1}-04-01"
                sc_end   = f"{season}-10-01"
                sc_full  = get_pitcher_statcast_range(pid, sc_start, sc_end)
                if not sc_full.empty:
                    sc_full = sc_full.copy()
                    sc_full["game_date"] = pd.to_datetime(sc_full["game_date"])

                for game in [g for g in season_games if g.get("IP", 5.0) >= 3.0]:
                    gdate = game["date"]

                    # Recent form (rolling 15 starts BEFORE this game)
                    recent = _pitcher_recent(full_log, gdate)
                    p_k_recent = recent.get("p_k_pct_recent", np.nan)
                    career_k   = career_snap.get("p_k_pct_career", np.nan)
                    p_form     = (p_k_recent - career_k) if not (np.isnan(p_k_recent) or np.isnan(career_k)) else np.nan

                    # Pitch mix for matchup (only pitches BEFORE this game)
                    if not sc_full.empty:
                        sc_prior = sc_full[sc_full["game_date"] < pd.Timestamp(gdate)]
                        mix = pitch_mix_features(sc_prior)
                    else:
                        mix = pitch_mix_features(pd.DataFrame())

                    opp_abbr = game.get("opponent_name", "")[:3].upper()
                    matchup_score = compute_matchup_k_score(mix, prior_team_pitch, opp_abbr)

                    # Lineup features
                    game_pk = game.get("game_pk")
                    lineup_entry = season_lineups.get(int(game_pk)) if game_pk else {}
                    is_home = game.get("is_home", True)
                    opp_batter_ids = lineup_entry.get("away" if is_home else "home", [])
                    lineup_feats = _build_lineup_features(
                        opp_batter_ids, prior_batter_k, hitter_profile_cache, season
                    )

                    # Umpire
                    ump_id = ump_by_game.get((gdate, str(game_pk or "")))
                    umpire_k = get_umpire_k_rate(ump_id, gdate) if ump_id else LEAGUE_K_PCT

                    row = {
                        # Pitcher career
                        "p_k_pct_career":  career_snap.get("p_k_pct_career", np.nan),
                        "p_bb_pct_career": career_snap.get("p_bb_pct_career", np.nan),
                        "p_ip_per_start":  career_snap.get("p_ip_per_start", np.nan),
                        # Recent form
                        "p_k_pct_recent":  p_k_recent,
                        "p_form":          p_form,
                        "p_fip":           recent.get("p_fip", np.nan),
                        "season_starts":   recent.get("season_starts", 0.0),
                        # Statcast quality
                        "p_whiff_rate":    sc_quality.get("p_whiff_rate", np.nan),
                        "p_csw_rate":      sc_quality.get("p_csw_rate", np.nan),
                        "p_velo_ff":       sc_quality.get("p_velo_ff", np.nan),
                        "p_offspeed_pct":  sc_quality.get("p_offspeed_pct", np.nan),
                        # Matchup
                        "matchup_k_score": matchup_score,
                        # Lineup
                        **lineup_feats,
                        # Context
                        "umpire_k_rate":   umpire_k,
                        # Target and identifiers
                        "ks_per_start":    float(game["SO"]),
                        "date":            gdate,
                        "mlbam_id":        pid,
                        "pitcher_name":    name,
                        "season":          season,
                    }
                    rows.append(row)

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

    if not df.empty:
        print(f"Target: mean={df['ks_per_start'].mean():.2f}  std={df['ks_per_start'].std():.2f}")
        null_pct = df[PROFILE_FEATURE_COLS].isnull().mean()
        print("\nNull rates:")
        for col, r in null_pct[null_pct > 0.01].items():
            print(f"  {col:<28} {r:.1%}")

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-seasons", nargs="+", type=int,
                        default=[2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024])
    parser.add_argument("--test-seasons",  nargs="+", type=int, default=[2025])
    parser.add_argument("--min-gs",        type=int, default=8)
    parser.add_argument("--test-only",     action="store_true")
    args = parser.parse_args()

    import time
    t0 = time.time()

    if not args.test_only:
        print("=== Building TRAIN dataset ===")
        df_train = build_profile_dataset(args.train_seasons, args.min_gs)
        if not df_train.empty:
            df_train.to_parquet(ARTIFACT_DIR / "profile_train.parquet", index=False)
            print(f"Saved: profile_train.parquet  ({len(df_train):,} rows)")

    for s in args.test_seasons:
        print(f"\n=== Building TEST dataset ({s}) ===")
        df_test = build_profile_dataset([s], args.min_gs)
        if not df_test.empty:
            out = ARTIFACT_DIR / TEST_OUT_TPL.format(season=s)
            df_test.to_parquet(out, index=False)
            print(f"Saved: {out.name}  ({len(df_test):,} rows)")

    print(f"\nDone in {(time.time()-t0)/60:.1f} min")
