"""
Player profiles — stable, multi-season talent estimates for pitchers and hitters.

Instead of reacting to noisy rolling windows (last 5/15 starts), profiles
anchor predictions to career/3-year baselines and enable true matchup scoring:
  pitcher pitch arsenal  ×  hitter K-rate by pitch type  →  expected K total

Data sources (all free):
  - MLB Stats API:  career/season stats, platoon splits
  - Statcast via pybaseball:  pitch mix, velo, spin, whiff per pitch type

Cached in artifacts/pitcher_profiles.json and artifacts/hitter_profiles.json.
Profiles refresh daily; stale entries older than 7 days are rebuilt on access.
"""
import json
import warnings
import numpy as np
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

PITCHER_CACHE = Path(__file__).parent.parent.parent / "artifacts" / "pitcher_profiles.json"
HITTER_CACHE  = Path(__file__).parent.parent.parent / "artifacts" / "hitter_profiles.json"

STALE_DAYS = 7   # rebuild profile if older than this
MIN_PA     = 100  # minimum PA to trust a hitter's K rate
MIN_BF     = 50   # minimum BF to trust a pitcher's K rate


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _load_cache(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def _save_cache(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _is_stale(profile: dict) -> bool:
    updated = profile.get("last_updated", "2000-01-01")
    return (date.today() - date.fromisoformat(updated)).days > STALE_DAYS


# ---------------------------------------------------------------------------
# Pitcher profile
# ---------------------------------------------------------------------------

def _fetch_pitcher_statcast(mlbam_id: int, seasons: list[int]) -> pd.DataFrame:
    """Pull Statcast for specified seasons, return pitch-level DataFrame."""
    from app.data.statcast_agg import get_pitcher_statcast_range
    frames = []
    for s in seasons:
        df = get_pitcher_statcast_range(mlbam_id, f"{s}-03-01", f"{s}-11-01")
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _pitch_mix_profile(sc_df: pd.DataFrame) -> dict:
    """
    From pitch-level Statcast, compute per-pitch-type:
      usage%, avg_velo, avg_spin, whiff_rate, k_rate (pitch leads to K%)
    """
    if sc_df.empty:
        return {}

    _swinging = {"swinging_strike", "swinging_strike_blocked"}
    total_pitches = len(sc_df)

    arsenal = {}
    for pt, grp in sc_df.groupby("pitch_type"):
        if pd.isna(pt) or pt == "" or len(grp) < 20:
            continue
        usage     = len(grp) / total_pitches
        velo      = grp["release_speed"].dropna().mean()
        spin      = grp["release_spin_rate"].dropna().mean()
        swings    = grp[grp["description"].isin({
            "swinging_strike","swinging_strike_blocked","foul","foul_tip",
            "hit_into_play","hit_into_play_no_out","hit_into_play_score","missed_bunt"
        })]
        whiff_rate = grp["description"].isin(_swinging).sum() / max(len(swings), 1)

        arsenal[str(pt)] = {
            "usage":      round(float(usage), 3),
            "velo":       round(float(velo), 1) if not np.isnan(velo) else None,
            "spin":       round(float(spin))    if not np.isnan(spin) else None,
            "whiff_rate": round(float(whiff_rate), 3),
            "n_pitches":  int(len(grp)),
        }
    return arsenal


def _pitcher_career_splits(mlbam_id: int, seasons: list[int]) -> dict:
    """Career K rate, BB rate, IP/start from MLB Stats API game logs."""
    from app.data.mlb_api import get_pitcher_multi_season_log
    try:
        log = get_pitcher_multi_season_log(mlbam_id, seasons)
    except Exception:
        return {}

    starts = [g for g in log if g.get("is_start", 1) and g.get("BF", 0) >= 9]
    if not starts:
        return {}

    total_bf = sum(g["BF"] for g in starts)
    total_so = sum(g["SO"] for g in starts)
    total_bb = sum(g.get("BB", 0) for g in starts)
    total_ip = sum(g.get("IP", 0) for g in starts)
    n_starts = len(starts)

    # Recency-weighted K rate (recent 3 seasons weighted 3x, older 1x)
    current_year = date.today().year
    weighted_so = weighted_bf = 0
    for g in starts:
        w = 3 if g.get("season", 0) >= current_year - 2 else 1
        weighted_so += g["SO"] * w
        weighted_bf += g["BF"] * w

    return {
        "career_k_pct":       round(total_so / max(total_bf, 1), 4),
        "career_k_pct_3yr":   round(weighted_so / max(weighted_bf, 1), 4),
        "career_bb_pct":      round(total_bb / max(total_bf, 1), 4),
        "career_ip_per_start": round(total_ip / max(n_starts, 1), 2),
        "career_starts":      n_starts,
    }


def build_pitcher_profile(mlbam_id: int, name: str = "", seasons: list[int] = None) -> dict:
    """
    Build a complete pitcher profile: career stats + Statcast pitch arsenal.
    Uses last 4 seasons of data for stability.
    """
    if seasons is None:
        cy = date.today().year
        seasons = [cy - 3, cy - 2, cy - 1, cy]

    career = _pitcher_career_splits(mlbam_id, seasons)
    sc_df  = _fetch_pitcher_statcast(mlbam_id, seasons[-3:])  # Statcast last 3 seasons
    arsenal = _pitch_mix_profile(sc_df)

    # Overall whiff/CSW from Statcast
    overall_whiff = overall_csw = None
    if not sc_df.empty:
        _swinging = {"swinging_strike", "swinging_strike_blocked"}
        _called   = {"called_strike"}
        total = len(sc_df)
        swings = sc_df[sc_df["description"].isin({
            "swinging_strike","swinging_strike_blocked","foul","foul_tip",
            "hit_into_play","hit_into_play_no_out","hit_into_play_score"
        })]
        overall_whiff = round(float(sc_df["description"].isin(_swinging).sum() / max(len(swings), 1)), 3)
        overall_csw   = round(float(sc_df["description"].isin(_swinging | _called).sum() / max(total, 1)), 3)

    return {
        "mlbam_id":     mlbam_id,
        "name":         name,
        "type":         "pitcher",
        **career,
        "arsenal":      arsenal,
        "overall_whiff_rate": overall_whiff,
        "overall_csw_rate":   overall_csw,
        "last_updated": date.today().isoformat(),
        "seasons_used": seasons,
    }


def get_pitcher_profile(mlbam_id: int, name: str = "", force_refresh: bool = False) -> dict:
    cache = _load_cache(PITCHER_CACHE)
    key   = str(mlbam_id)
    if not force_refresh and key in cache and not _is_stale(cache[key]):
        return cache[key]

    print(f"  [profile] Building pitcher profile: {name or mlbam_id}")
    profile = build_pitcher_profile(mlbam_id, name)
    cache[key] = profile
    _save_cache(PITCHER_CACHE, cache)
    return profile


# ---------------------------------------------------------------------------
# Hitter profile
# ---------------------------------------------------------------------------

def _hitter_statcast_splits(mlbam_id: int, seasons: list[int]) -> dict:
    """
    Pull hitter Statcast data and compute K-rate by pitch type faced,
    chase rate, and contact rate.
    """
    try:
        from pybaseball import statcast_batter
    except ImportError:
        return {}

    frames = []
    for s in seasons:
        try:
            df = statcast_batter(f"{s}-03-01", f"{s}-11-01", player_id=mlbam_id)
            if not df.empty:
                frames.append(df)
        except Exception:
            pass

    if not frames:
        return {}

    sc = pd.concat(frames, ignore_index=True)
    if sc.empty:
        return {}

    _swinging = {"swinging_strike", "swinging_strike_blocked"}
    total_pa  = sc[sc["events"].notna()].shape[0]  # plate appearances

    # K rate by pitch type faced
    k_by_pitch = {}
    for pt, grp in sc.groupby("pitch_type"):
        if pd.isna(pt) or pt == "" or len(grp) < 10:
            continue
        pa_in_group = grp[grp["events"].notna()]
        k_in_group  = grp[grp["events"] == "strikeout"]
        if len(pa_in_group) < 10:
            continue
        k_by_pitch[str(pt)] = round(len(k_in_group) / len(pa_in_group), 4)

    # Chase rate: swings on balls outside zone
    zone_col = "zone"
    if zone_col in sc.columns:
        outside = sc[sc[zone_col].isin([11, 12, 13, 14])]  # outside zone codes
        swings_outside = outside["description"].isin({
            "swinging_strike","swinging_strike_blocked","foul","foul_tip","hit_into_play",
            "hit_into_play_no_out","hit_into_play_score"
        }).sum()
        chase_rate = round(float(swings_outside / max(len(outside), 1)), 3)
    else:
        chase_rate = None

    # Contact rate: (swings - whiffs) / swings
    all_swings = sc["description"].isin({
        "swinging_strike","swinging_strike_blocked","foul","foul_tip",
        "hit_into_play","hit_into_play_no_out","hit_into_play_score"
    }).sum()
    whiffs = sc["description"].isin(_swinging).sum()
    contact_rate = round(float((all_swings - whiffs) / max(all_swings, 1)), 3)

    return {
        "k_by_pitch_type": k_by_pitch,
        "chase_rate":      chase_rate,
        "contact_rate":    contact_rate,
        "statcast_pa":     int(total_pa),
    }


def _hitter_career_stats(mlbam_id: int, seasons: list[int]) -> dict:
    """Career K rate from MLB Stats API player season stats."""
    import urllib.request
    splits = {}
    total_pa = total_so = 0
    recent_pa = recent_so = 0
    current_year = date.today().year

    for s in seasons:
        url = (f"https://statsapi.mlb.com/api/v1/people/{mlbam_id}"
               f"/stats?stats=season&season={s}&group=hitting")
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
            for split in data.get("stats", [{}])[0].get("splits", []):
                st = split.get("stat", {})
                pa = int(st.get("plateAppearances", 0))
                so = int(st.get("strikeOuts", 0))
                total_pa += pa; total_so += so
                if s >= current_year - 2:
                    recent_pa += pa; recent_so += so
        except Exception:
            pass

    if total_pa < MIN_PA:
        return {}

    return {
        "career_k_pct":     round(total_so / max(total_pa, 1), 4),
        "career_k_pct_3yr": round(recent_so / max(recent_pa, 1), 4) if recent_pa >= 50 else None,
        "career_pa":        total_pa,
    }


def build_hitter_profile(mlbam_id: int, name: str = "", seasons: list[int] = None,
                          bats: str = "") -> dict:
    """Build a complete hitter profile: career K stats + Statcast pitch-type splits."""
    if seasons is None:
        cy = date.today().year
        seasons = [cy - 3, cy - 2, cy - 1, cy]

    career  = _hitter_career_stats(mlbam_id, seasons)
    statcast = _hitter_statcast_splits(mlbam_id, seasons[-3:])

    return {
        "mlbam_id":     mlbam_id,
        "name":         name,
        "bats":         bats,
        "type":         "hitter",
        **career,
        **statcast,
        "last_updated": date.today().isoformat(),
        "seasons_used": seasons,
    }


def get_hitter_profile(mlbam_id: int, name: str = "", bats: str = "",
                       force_refresh: bool = False) -> dict:
    cache = _load_cache(HITTER_CACHE)
    key   = str(mlbam_id)
    if not force_refresh and key in cache and not _is_stale(cache[key]):
        return cache[key]

    print(f"  [profile] Building hitter profile: {name or mlbam_id}")
    profile = build_hitter_profile(mlbam_id, name, bats=bats)
    cache[key] = profile
    _save_cache(HITTER_CACHE, cache)
    return profile


# ---------------------------------------------------------------------------
# Matchup scoring
# ---------------------------------------------------------------------------

def pitcher_vs_lineup_k_score(pitcher_profile: dict, hitter_profiles: list[dict]) -> float:
    """
    Estimate expected strikeout total from pitcher-vs-lineup matchup.

    For each hitter, compute:
      matchup_k_pct = sum over pitch types of (pitcher_usage × hitter_k_pct_on_that_pitch)

    Fall back to hitter's career K rate for pitch types with no split data.
    Expected Ks = avg matchup K% × expected PA × expected IP fraction.
    """
    if not hitter_profiles:
        return None

    arsenal = pitcher_profile.get("arsenal", {})
    ip_per_start = pitcher_profile.get("career_ip_per_start", 5.5)
    expected_pa  = ip_per_start * 4.3  # ~4.3 batters faced per inning

    matchup_k_pcts = []
    for hitter in hitter_profiles:
        h_k_career  = hitter.get("career_k_pct_3yr") or hitter.get("career_k_pct", 0.22)
        h_k_by_pt   = hitter.get("k_by_pitch_type", {})

        if arsenal and h_k_by_pt:
            # Weighted K rate: pitcher's usage × hitter's K% on each pitch
            total_usage = sum(pt["usage"] for pt in arsenal.values())
            k_pct = 0.0
            for pt_name, pt_stats in arsenal.items():
                usage  = pt_stats["usage"] / max(total_usage, 1)
                h_k_pt = h_k_by_pt.get(pt_name, h_k_career)
                k_pct += usage * h_k_pt
        else:
            k_pct = h_k_career

        matchup_k_pcts.append(k_pct)

    avg_matchup_k = float(np.mean(matchup_k_pcts))
    return round(avg_matchup_k * expected_pa, 2)


def matchup_summary(pitcher_profile: dict, hitter_profiles: list[dict]) -> dict:
    """Return a human-readable matchup summary for display."""
    score = pitcher_vs_lineup_k_score(pitcher_profile, hitter_profiles)
    p     = pitcher_profile
    return {
        "pitcher":              p.get("name"),
        "pitcher_career_k_pct": p.get("career_k_pct_3yr") or p.get("career_k_pct"),
        "pitcher_ip_per_start": p.get("career_ip_per_start"),
        "lineup_size":          len(hitter_profiles),
        "avg_lineup_k_pct":     round(float(np.mean([
            h.get("career_k_pct_3yr") or h.get("career_k_pct", 0.22)
            for h in hitter_profiles
        ])), 4) if hitter_profiles else None,
        "expected_ks_matchup":  score,
    }
