"""
Statcast aggregation.

statcast_pitcher() is broken in pybaseball 2.2.7 for specific IDs,
so we pull full-day Statcast and filter.  To keep this tractable we cache
monthly chunks on disk so repeat runs are fast.
"""
import os
import time
import warnings
import calendar
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

CACHE_DIR = Path(__file__).parent.parent.parent / "artifacts" / "statcast_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

KEEP_COLS = [
    "pitcher", "game_date", "pitch_type",
    "release_speed", "release_spin_rate",
    "events", "description",
    "home_team", "away_team", "inning_topbot",
]

TEAM_PITCH_K_CACHE = CACHE_DIR / "team_pitch_k_{season}.json"


def _month_cache_path(year: int, month: int) -> Path:
    return CACHE_DIR / f"statcast_{year}_{month:02d}.parquet"


def _load_month(year: int, month: int) -> pd.DataFrame:
    """Load one calendar month of Statcast, caching as parquet."""
    path = _month_cache_path(year, month)
    if path.exists():
        return pd.read_parquet(path)

    from pybaseball import statcast
    _, last_day = calendar.monthrange(year, month)
    start = f"{year}-{month:02d}-01"
    end   = f"{year}-{month:02d}-{last_day:02d}"

    # Don't pull future months
    today = date.today()
    if date(year, month, 1) > today:
        return pd.DataFrame(columns=KEEP_COLS)

    print(f"    Fetching Statcast {start} to {end}...", end=" ", flush=True)
    try:
        df = statcast(start, end)
        result = pd.DataFrame(columns=KEEP_COLS) if df.empty else df[[c for c in KEEP_COLS if c in df.columns]].copy()
        if not result.empty:
            result["game_date"] = pd.to_datetime(result["game_date"])
        # Always cache (including empty) so we don't re-fetch dead months
        result.to_parquet(path, index=False)
        print(f"{len(result):,} pitches cached")
        return result
    except Exception as e:
        print(f"FAILED ({e})")
        return pd.DataFrame(columns=KEEP_COLS)


def invalidate_current_month():
    """Delete current month's parquet if >20h old so next lookup re-fetches fresh data."""
    today = date.today()
    path = _month_cache_path(today.year, today.month)
    if path.exists():
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        if age_hours > 20:
            path.unlink()
            print(f"  [statcast] Invalidated stale cache: {path.name} (age: {age_hours:.1f}h)")
            return True
    return False


def get_pitcher_statcast_range(
    mlbam_id: int,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Pull Statcast for all months in [start_date, end_date] and filter to pitcher.
    Uses disk cache so second pull is instant.
    """
    start = pd.to_datetime(start_date)
    end   = pd.to_datetime(end_date)

    frames = []
    cur = start.replace(day=1)
    while cur <= end:
        chunk = _load_month(cur.year, cur.month)
        if not chunk.empty:
            filtered = chunk[chunk["pitcher"] == mlbam_id]
            if not filtered.empty:
                frames.append(filtered)
        cur = (cur + pd.offsets.MonthEnd(1) + timedelta(days=1)).replace(day=1)

    if not frames:
        return pd.DataFrame(columns=KEEP_COLS)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Feature extraction from raw pitch log
# ---------------------------------------------------------------------------

_SWINGING_MISS = {"swinging_strike", "swinging_strike_blocked"}
_SWINGS = {
    "swinging_strike", "swinging_strike_blocked",
    "foul", "foul_tip", "foul_bunt", "bunt_foul_tip",
    "hit_into_play", "missed_bunt", "foul_pitchout",
}
_CALLED_STRIKE = {"called_strike", "automatic_strike"}

def pitch_mix_features(df: pd.DataFrame) -> dict:
    """
    Aggregate pitch-level rows into per-pitcher mix/velocity/whiff features.
    Uses the most recent 60 days of data.
    """
    if df.empty:
        return {
            "ff_pct": np.nan,
            "ch_pct": np.nan, "cb_pct": np.nan,
            "ff_velo_avg": np.nan, "ff_spin_avg": np.nan,
            "swstr_pct": np.nan, "whiff_pct": np.nan, "csw_pct": np.nan,
        }

    # Use most recent 60 days
    cutoff = df["game_date"].max() - pd.Timedelta(days=60)
    recent = df[df["game_date"] >= cutoff]
    if recent.empty:
        recent = df

    total = len(recent)
    counts = recent["pitch_type"].value_counts()

    def pct(pt): return counts.get(pt, 0) / total

    ff = recent[recent["pitch_type"] == "FF"]

    swstr_pct = whiff_pct = csw_pct = np.nan
    if "description" in recent.columns and total > 0:
        desc = recent["description"]
        miss_count = desc.isin(_SWINGING_MISS).sum()
        swings     = desc.isin(_SWINGS).sum()
        csw_count  = desc.isin(_CALLED_STRIKE | _SWINGING_MISS).sum()

        swstr_pct = float(miss_count / total)
        whiff_pct = float(miss_count / swings) if swings > 0 else np.nan
        csw_pct   = float(csw_count  / total)

    return {
        "ff_pct":      pct("FF"),
        "ch_pct":      pct("CH"),
        "cb_pct":      pct("CU"),
        "ff_velo_avg": float(ff["release_speed"].mean()) if not ff.empty else np.nan,
        "ff_spin_avg": float(ff["release_spin_rate"].mean()) if not ff.empty else np.nan,
        "swstr_pct":   swstr_pct,
        "whiff_pct":   whiff_pct,
        "csw_pct":     csw_pct,
    }


def get_team_pitch_k_pct(season: int) -> dict:
    """
    Returns {team_abbr: {pitch_type: k_pct}} for a season.
    K rate = strikeouts / plate-appearance-ending events per pitch type, per batting team.
    Uses prior-season data to avoid leakage (call with season-1 for training rows).
    Cached to artifacts/statcast_cache/team_pitch_k_{season}.json.
    """
    import json as _json
    cache_path = Path(str(TEAM_PITCH_K_CACHE).replace("{season}", str(season)))
    if cache_path.exists():
        return _json.loads(cache_path.read_text())

    print(f"  Building team pitch K% for {season}...")
    frames = []
    for month in range(3, 11):
        chunk = _load_month(season, month)
        if not chunk.empty:
            needed = [c for c in ["home_team", "away_team", "inning_topbot", "pitch_type", "events"] if c in chunk.columns]
            if len(needed) == 5:
                frames.append(chunk[needed])

    if not frames:
        return {}

    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["inning_topbot", "pitch_type"])

    # Batting team = home if bottom inning, away if top
    df["bat_team"] = df.apply(
        lambda r: r["home_team"] if r["inning_topbot"] == "Bot" else r["away_team"], axis=1
    )

    # Only rows where a PA ended
    pa_events = {"strikeout","field_out","grounded_into_double_play","double_play",
                 "sac_fly","sac_bunt","field_error","single","double","triple",
                 "home_run","walk","hit_by_pitch","force_out","fielders_choice"}
    df = df[df["events"].isin(pa_events)]

    result = {}
    for team, grp in df.groupby("bat_team"):
        result[team] = {}
        for pt, ptgrp in grp.groupby("pitch_type"):
            if len(ptgrp) < 30:
                continue
            k_pct = (ptgrp["events"] == "strikeout").sum() / len(ptgrp)
            result[team][pt] = round(float(k_pct), 4)

    cache_path.write_text(_json.dumps(result))
    print(f"    {len(result)} teams cached")
    return result


def compute_matchup_k_score(pitch_mix: dict, team_pitch_k: dict, opponent_abbr: str) -> float:
    """
    Weighted K rate: pitcher's pitch usage × opponent's K rate vs each pitch type.
    Falls back to league average per pitch type if no data.
    """
    LEAGUE_AVG = {"FF": 0.215, "SL": 0.255, "CH": 0.230, "CU": 0.235}
    opp = team_pitch_k.get(opponent_abbr, {})
    pitch_map = {"ff_pct": "FF", "sl_pct": "SL", "ch_pct": "CH", "cb_pct": "CU"}
    score = 0.0
    total_usage = 0.0
    for feat, pt in pitch_map.items():
        usage = pitch_mix.get(feat) or 0.0
        k_rate = opp.get(pt, LEAGUE_AVG.get(pt, 0.225))
        score += usage * k_rate
        total_usage += usage
    if total_usage < 0.1:
        return np.nan
    return round(score, 4)


def game_level_strikeouts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate pitch rows to per-game strikeout counts for a pitcher.
    Returns DataFrame with columns: game_date, SO_statcast.
    Used to cross-validate against MLB API game logs.
    """
    if df.empty:
        return pd.DataFrame(columns=["game_date", "SO_statcast"])
    so = (
        df[df["events"] == "strikeout"]
        .groupby("game_date")
        .size()
        .reset_index(name="SO_statcast")
    )
    return so
