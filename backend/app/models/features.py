"""
Feature engineering for the strikeout prop model.

Every feature is derived from publicly available pitcher game logs and
Statcast data. The pipeline is designed to work both for training
(historical rows) and live inference (most-recent N starts).
"""
import numpy as np
import pandas as pd


FEATURE_COLS = [
    # Rolling pitcher K rate — short windows are noisy, longer windows anchor predictions
    "k_pct_last5",
    "k_pct_last15",
    "k_pct_last30",   # ~2-season anchor; dampens cold-streak overreaction
    "k_pct_season",
    "k_pct_career",   # career K rate — strongest prior against regression-to-mean noise
    # K-rate momentum: positive = heating up, negative = slipping
    "k_trend",        # k_pct_last5 - k_pct_last15
    "k_vs_career",    # k_pct_last15 - k_pct_career (how far from true talent)
    # Pitcher quality (defense-independent)
    "fip_last15",     # fielding-independent pitching over last 15 starts
    # Pitch-mix features (from Statcast)
    "ff_pct",         # four-seam fastball usage %
    # Velocity / spin
    "ff_velo_avg",
    "ff_spin_avg",
    # Swing-and-miss
    "swstr_pct",      # swinging strike rate
    "whiff_pct",      # whiff rate
    "csw_pct",        # called strike + whiff %
    # Recent workload
    "avg_ip_last5",
    # Season context
    "season_starts",
    # Opponent factors
    "opp_k_pct",
    "opp_lineup_k_pct",
    "matchup_k_score",
    # Umpire
    "umpire_k_rate",
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
