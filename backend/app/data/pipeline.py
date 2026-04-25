"""
Feature pipeline — the single place where MLB API game logs + Statcast
are combined into the feature vector used by the model.

Used by:
  - train/build_dataset.py  (build training rows from historical data)
  - app.py                  (build inference rows for today's starters)
"""
import warnings
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.data.mlb_api import (
    get_pitcher_multi_season_log,
    get_pitcher_game_log,
    get_team_k_pct,
)
from app.data.statcast_agg import get_pitcher_statcast_range, pitch_mix_features, get_team_pitch_k_pct, compute_matchup_k_score
from app.data.umpire import get_umpire_k_rate, LEAGUE_K_PCT
from app.data.lineup import get_season_batter_k_pcts, compute_lineup_k_pct
from app.models.features import FEATURE_COLS

warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# Rolling stats from game log
# ---------------------------------------------------------------------------

def _rolling_features(game_log: list[dict], as_of_date: str) -> dict:
    """
    Given a pitcher's full game log (sorted ascending), compute rolling
    K-rate and IP features as of (but not including) as_of_date.
    """
    # Require >= 12 BF to exclude opener/injury-exit starts from rolling window
    past = [g for g in game_log if g["date"] < as_of_date and g["BF"] >= 12 and g.get("is_start", 1)]
    if not past:
        return {
            "k_pct_last5":  np.nan,
            "k_pct_last15": np.nan,
            "k_pct_season": np.nan,
            "avg_ip_last5": np.nan,
            "avg_bf_last5": np.nan,
            "days_rest":    np.nan,
        }

    def k_pct(rows): return sum(r["SO"] for r in rows) / max(sum(r["BF"] for r in rows), 1)

    season_rows = [g for g in past if g.get("season") == int(as_of_date[:4])]
    last5  = past[-5:]
    last15 = past[-15:]

    last_date = past[-1]["date"]
    raw_rest  = (date.fromisoformat(as_of_date) - date.fromisoformat(last_date)).days
    days_rest = min(float(raw_rest), 7.0)

    return {
        "k_pct_last5":  k_pct(last5),
        "k_pct_last15": k_pct(last15),
        "k_pct_season": k_pct(season_rows) if season_rows else k_pct(last15),
        "avg_ip_last5": float(np.mean([g["IP"] for g in last5])),
        "avg_bf_last5": float(np.mean([g["BF"] for g in last5])),
        "days_rest":    float(days_rest),
    }


# ---------------------------------------------------------------------------
# Inference: build a feature row for a single upcoming start
# ---------------------------------------------------------------------------

def build_inference_row(
    mlbam_id: int,
    game_date: str,
    opponent_id: int,
    is_home: bool,
    season: int = None,
    _team_k_cache: dict = None,
    umpire_id: int = None,
    opponent_abbr: str = "",
    _team_pitch_k_cache: dict = None,
    opp_lineup_ids: list = None,
    _batter_k_cache: dict = None,
    park_abbr: str = "",  # kept for call-site compatibility, no longer used
) -> pd.Series:
    if season is None:
        season = int(game_date[:4])

    # -- Game log rolling features --
    seasons_to_pull = [season - 1, season] if int(game_date[5:7]) < 5 else [season]
    game_log = get_pitcher_multi_season_log(mlbam_id, seasons_to_pull)
    rolling  = _rolling_features(game_log, game_date)

    # -- Pitch mix from Statcast — look back 365 days to cover prior season --
    sc_start = (date.fromisoformat(game_date) - timedelta(days=365)).isoformat()
    sc_df    = get_pitcher_statcast_range(mlbam_id, sc_start, game_date)
    mix      = pitch_mix_features(sc_df)

    # -- Opponent K% (use prior season to avoid leakage) --
    if _team_k_cache is None:
        _team_k_cache = get_team_k_pct(season - 1)
    opp_k_pct = _team_k_cache.get(opponent_id, 0.225)

    # -- Lineup-specific K rate --
    if opp_lineup_ids:
        if _batter_k_cache is None:
            _batter_k_cache = get_season_batter_k_pcts(season - 1)
        lineup_k = compute_lineup_k_pct(opp_lineup_ids, _batter_k_cache)
    else:
        lineup_k = opp_k_pct  # fall back to team average when no lineup available

    # -- Matchup K score: pitcher pitch mix × opponent K% per pitch type --
    if _team_pitch_k_cache is None:
        _team_pitch_k_cache = get_team_pitch_k_pct(season - 1)
    matchup_k = compute_matchup_k_score(mix, _team_pitch_k_cache, opponent_abbr)

    umpire_k = get_umpire_k_rate(umpire_id, game_date) if umpire_id else LEAGUE_K_PCT

    feature_dict = {
        **rolling,
        **mix,
        "opp_k_pct":         opp_k_pct,
        "opp_lineup_k_pct":  lineup_k,
        "matchup_k_score":   matchup_k,
        "is_home":       int(is_home),
        "umpire_k_rate": umpire_k,
    }

    return pd.Series({col: feature_dict.get(col, np.nan) for col in FEATURE_COLS})


# ---------------------------------------------------------------------------
# Training: build feature rows from one game's historical context
# ---------------------------------------------------------------------------

def build_training_row(
    game: dict,
    full_log: list[dict],
    pitch_mix: dict,
    team_k_map: dict,
    umpire_id: int = None,
    matchup_k_score: float = None,
    opp_lineup_k_pct: float = None,
) -> dict | None:
    """
    Build one labeled training row.
    Returns None if not enough prior history to compute rolling features.
    """
    rolling = _rolling_features(full_log, game["date"])
    if np.isnan(rolling["k_pct_last5"]):
        return None

    opp_k_pct  = team_k_map.get(game.get("opponent_id"), 0.225)
    umpire_k   = get_umpire_k_rate(umpire_id, game["date"]) if umpire_id else LEAGUE_K_PCT

    feature_dict = {
        **rolling,
        **pitch_mix,
        "opp_k_pct":         opp_k_pct,
        "opp_lineup_k_pct":  opp_lineup_k_pct if opp_lineup_k_pct is not None else np.nan,
        "matchup_k_score":   matchup_k_score if matchup_k_score is not None else np.nan,
        "is_home":       int(game.get("is_home", True)),
        "umpire_k_rate": umpire_k,
    }

    return {
        **{col: feature_dict.get(col, np.nan) for col in FEATURE_COLS},
        "ks_per_start": float(game["SO"]),
        "date":         game["date"],
        "mlbam_id":     game["mlbam_id"],
        "season":       game.get("season"),
    }
