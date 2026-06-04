"""
Feature engineering for the strikeout prop model.

Two feature sets are defined:
  FEATURE_COLS        — current rolling-window model (production)
  PROFILE_FEATURE_COLS — new profile-based model (redesign in progress)

The profile model anchors every prediction to stable career talent rather
than noisy short-term windows, and uses real matchup scoring (pitcher
arsenal × per-pitch-type hitter K rates) instead of team-level proxies.
"""
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Current model (rolling windows)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Profile-based model (redesign)
# ---------------------------------------------------------------------------

PROFILE_FEATURE_COLS = [
    # --- Pitcher stable talent (from career game logs) ---
    "p_k_pct_career",       # 3yr-weighted career K rate — primary talent signal
    "p_k_pct_recent",       # last 15 starts — form modifier on top of career
    "p_form",               # p_k_pct_recent - p_k_pct_career (deviation from talent)
    "p_bb_pct_career",      # walk rate — limits innings and drives pitch count
    "p_ip_per_start",       # typical outing length — directly scales K total
    "p_fip",                # FIP over last 15 starts — defense-independent quality

    # --- Pitcher pitch quality (from Statcast) ---
    "p_whiff_rate",         # overall whiff rate across all pitch types
    "p_csw_rate",           # called strike + whiff — best single K predictor
    "p_velo_ff",            # fastball velocity — correlates with swing-and-miss
    "p_offspeed_pct",       # SL+CH+CU+ST usage — breaking/offspeed heavy = more Ks

    # --- Matchup: pitcher arsenal × lineup pitch-type K vulnerability ---
    "matchup_k_score",      # pitcher pitch mix × opponent K% per pitch type

    # --- Opponent lineup (individual batter profiles) ---
    "lineup_k_pct",         # avg career K rate of today's actual lineup batters
    "lineup_chase_rate",    # how aggressively this lineup chases — favours Ks
    "lineup_contact_rate",  # contact skill — lower = more Ks

    # --- Context ---
    "umpire_k_rate",        # home plate umpire historical K rate
    "season_starts",        # pitcher's starts so far this season
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
