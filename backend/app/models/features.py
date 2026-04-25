"""
Feature engineering for the strikeout prop model.

Every feature is derived from publicly available pitcher game logs and
Statcast data. The pipeline is designed to work both for training
(historical rows) and live inference (most-recent N starts).
"""
import numpy as np
import pandas as pd


FEATURE_COLS = [
    # Rolling pitcher K rate
    "k_pct_last5",
    "k_pct_last15",
    "k_pct_season",
    # Pitch-mix features (from Statcast)
    "ff_pct",        # four-seam fastball usage %
    "sl_pct",        # slider usage %
    # Velocity
    "ff_velo_avg",
    # Spin proxies
    "ff_spin_avg",
    # Swing-and-miss
    "swstr_pct",     # swinging strike rate (swinging_strike + swinging_strike_blocked) / total pitches
    # Recent workload
    "avg_ip_last5",
    "avg_bf_last5",
    "days_rest",
    # Opponent factors
    "opp_k_pct",           # opponent team K% prior season (fallback)
    "opp_lineup_k_pct",    # weighted K% of today's actual lineup (prior-season rates)
    "matchup_k_score",     # pitcher pitch mix × opponent K% vs each pitch type
    # Context
    "is_home",
    # Umpire
    "umpire_k_rate",      # home plate umpire's historical K rate
]


def build_pitcher_rolling_features(game_log: pd.DataFrame, n_last: int = 5) -> dict:
    """
    Given a DataFrame of a single pitcher's game-level stats (sorted ascending by date),
    return rolling feature dict for the *next* start.
    Expects columns: SO, BF, IP, game_date
    """
    df = game_log.sort_values("game_date").copy()
    df["k_pct"] = df["SO"] / df["BF"].replace(0, np.nan)

    last5 = df.tail(5)
    last15 = df.tail(15)

    return {
        "k_pct_last5": last5["k_pct"].mean(),
        "k_pct_last15": last15["k_pct"].mean(),
        "k_pct_season": df["k_pct"].mean(),
        "avg_ip_last5": last5["IP"].mean(),
    }


def build_pitch_mix_features(statcast_df: pd.DataFrame) -> dict:
    """
    Compute pitch-type usage, velocity, and whiff features from raw Statcast pitch log.
    """
    _swinging_miss = {"swinging_strike", "swinging_strike_blocked"}
    if statcast_df.empty:
        return {col: np.nan for col in ["ff_pct", "sl_pct", "ch_pct", "cb_pct", "ff_velo_avg", "ff_spin_avg", "swstr_pct"]}

    total = len(statcast_df)
    pitch_counts = statcast_df["pitch_type"].value_counts()

    def pct(pt: str) -> float:
        return pitch_counts.get(pt, 0) / total

    ff = statcast_df[statcast_df["pitch_type"] == "FF"]

    swstr_pct = np.nan
    if "description" in statcast_df.columns and total > 0:
        swstr_pct = float(statcast_df["description"].isin(_swinging_miss).sum() / total)

    return {
        "ff_pct":      pct("FF"),
        "sl_pct":      pct("SL"),
        "ch_pct":      pct("CH"),
        "cb_pct":      pct("CU"),
        "ff_velo_avg": ff["release_speed"].mean() if not ff.empty else np.nan,
        "ff_spin_avg": ff["release_spin_rate"].mean() if not ff.empty else np.nan,
        "swstr_pct":   swstr_pct,
    }


def assemble_feature_row(
    game_log: pd.DataFrame,
    statcast_df: pd.DataFrame,
    days_rest: int,
    opp_k_pct: float,
    is_home: bool,
) -> pd.Series:
    rolling = build_pitcher_rolling_features(game_log)
    pitch_mix = build_pitch_mix_features(statcast_df)

    row = {
        **rolling,
        **pitch_mix,  # includes swstr_pct
        "days_rest":        days_rest,
        "opp_k_pct":        opp_k_pct,
        "opp_lineup_k_pct": np.nan,
        "matchup_k_score":  np.nan,
        "is_home":          int(is_home),
        "umpire_k_rate":    np.nan,
    }

    return pd.Series({col: row.get(col, np.nan) for col in FEATURE_COLS})
