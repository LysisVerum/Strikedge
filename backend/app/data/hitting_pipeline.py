"""
Live hitting slate pipeline.

Fetches DraftKings batter hit prop lines, resolves player IDs, loads recent
Statcast data from the hitting_cache, computes feature vectors, and returns a
slate list compatible with _HITTING_DEMO_SLATE / _run_hitting_slate() in app.py.

Public API:
    slate = build_live_hitting_slate()

Each element of the returned list is a dict:
    {
        "batter_name": str,
        "mlbam_id":    int,
        "team":        str,
        "opponent_abbr": str,
        "is_home":     bool,
        "line":        float,
        "over_odds":   int,
        "under_odds":  int,
        "features":    dict,   # keys == HITTING_FEATURE_COLS
    }

The module keeps two module-level caches that survive across calls within a
single server session:
    _player_id_cache   {name_lower: {mlbam_id, team}}
    _sc_month_cache    {(year, month): DataFrame}
"""
import calendar
import time
import warnings
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file's location)
# ---------------------------------------------------------------------------

_REPO_ROOT    = Path(__file__).parent.parent.parent          # backend/
_CACHE_DIR    = _REPO_ROOT / "artifacts" / "hitting_cache"

# ---------------------------------------------------------------------------
# Static park factors (2025 approximations)
# ---------------------------------------------------------------------------

_PARK_FACTORS = {
    "COL": 1.12, "CIN": 1.07, "BOS": 1.06, "TEX": 1.05, "PHI": 1.04,
    "MIL": 1.03, "CLE": 1.02, "CHC": 1.01, "HOU": 1.01, "ARI": 1.01,
    "STL": 0.99, "NYY": 0.99, "ATL": 0.99, "LAD": 0.99, "TOR": 0.98,
    "MIN": 0.98, "SEA": 0.98, "TB":  0.97, "SF":  0.97, "DET": 0.97,
    "CWS": 0.97, "WSH": 0.96, "BAL": 0.96, "NYM": 0.96, "OAK": 0.96,
    "MIA": 0.95, "KC":  0.95, "LAA": 0.95, "PIT": 0.94, "SD":  0.94,
}

# ---------------------------------------------------------------------------
# Statcast columns we need — keeps memory lean
# ---------------------------------------------------------------------------

_SC_COLS = [
    "game_date", "game_pk",
    "batter",
    "events",
    "p_throws",
    "launch_speed",
    "launch_angle",
    "estimated_ba_using_speedangle",
    "barrel",
    "inning_topbot",
]

_HIT_EVENTS = frozenset(["single", "double", "triple", "home_run"])
_NON_AB     = frozenset([
    "walk", "intent_walk", "hit_by_pitch",
    "sac_fly", "sac_bunt", "sac_fly_double_play", "sac_bunt_double_play",
    "catcher_interf",
])

# ---------------------------------------------------------------------------
# Module-level caches — persist within a server session
# ---------------------------------------------------------------------------

_player_id_cache: dict[str, dict] = {}   # name_lower -> {mlbam_id, team}
_sc_month_cache:  dict[tuple, pd.DataFrame] = {}   # (year, month) -> DataFrame


# ---------------------------------------------------------------------------
# Statcast helpers
# ---------------------------------------------------------------------------

def _load_sc_month(year: int, month: int) -> pd.DataFrame:
    """Load one month of Statcast, using the parquet cache or pybaseball."""
    cache_key = (year, month)
    if cache_key in _sc_month_cache:
        return _sc_month_cache[cache_key]

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / f"sc_{year}_{month:02d}.parquet"

    if path.exists():
        df = pd.read_parquet(path, columns=[c for c in _SC_COLS if True])
        # Only keep columns we actually have
        keep = [c for c in _SC_COLS if c in df.columns]
        df = df[keep].copy()
        df["game_date"] = pd.to_datetime(df["game_date"])
        _sc_month_cache[cache_key] = df
        return df

    today = date.today()
    if date(year, month, 1) > today:
        empty = pd.DataFrame(columns=_SC_COLS)
        _sc_month_cache[cache_key] = empty
        return empty

    from pybaseball import statcast
    _, last_day = calendar.monthrange(year, month)
    start = f"{year}-{month:02d}-01"
    end   = f"{year}-{month:02d}-{last_day:02d}"

    print(f"  [hitting_pipeline] Fetching Statcast {start} → {end}...", end=" ", flush=True)
    try:
        raw = statcast(start, end, parallel=False)
        if raw is None or raw.empty:
            result = pd.DataFrame(columns=_SC_COLS)
        else:
            keep   = [c for c in _SC_COLS if c in raw.columns]
            result = raw[keep].copy()
            result["game_date"] = pd.to_datetime(result["game_date"])
        result.to_parquet(path, index=False)
        print(f"{len(result):,} pitches")
    except Exception as exc:
        print(f"SKIP ({exc})")
        result = pd.DataFrame(columns=_SC_COLS)

    _sc_month_cache[cache_key] = result
    return result


def _load_recent_statcast(days: int = 95) -> pd.DataFrame:
    """
    Load the last `days` worth of Statcast data (current season only).
    Returns a concatenated DataFrame covering the required months.
    """
    today     = date.today()
    year      = today.year
    cutoff    = pd.Timestamp(today) - pd.Timedelta(days=days)

    # Figure out which months to load
    months_needed = set()
    cur = date(year, cutoff.month, 1)
    while cur <= today:
        months_needed.add((cur.year, cur.month))
        # advance one month
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)

    parts = []
    for (y, m) in sorted(months_needed):
        chunk = _load_sc_month(y, m)
        if not chunk.empty:
            parts.append(chunk)

    if not parts:
        return pd.DataFrame(columns=_SC_COLS)

    df = pd.concat(parts, ignore_index=True)
    df["game_date"] = pd.to_datetime(df["game_date"])
    # Keep only rows within the rolling window
    df = df[df["game_date"] >= cutoff].reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Aggregate Statcast → batter-game level
# ---------------------------------------------------------------------------

def _aggregate_batter_games(sc: pd.DataFrame) -> pd.DataFrame:
    """One row per (batter, game_date, game_pk) with rolling metrics."""
    if sc.empty:
        return pd.DataFrame()

    pa = sc[sc["events"].notna()].copy()
    if pa.empty:
        return pd.DataFrame()

    pa["is_hit"]      = pa["events"].isin(_HIT_EVENTS).fillna(False).astype(np.int8)
    pa["is_ab"]       = (~pa["events"].isin(_NON_AB)).fillna(False).astype(np.int8)
    pa["is_home_bat"] = (pa["inning_topbot"] == "Bot").fillna(False).astype(np.int8)
    pa["is_hard_hit"] = (pa["launch_speed"] >= 95).fillna(False).astype(np.int8)
    pa["is_sweet"]    = (
        (pa["launch_angle"] >= 8) & (pa["launch_angle"] <= 32)
    ).fillna(False).astype(np.int8)
    pa["has_contact"] = pa["launch_speed"].notna().astype(np.int8)

    grp = pa.groupby(["batter", "game_date", "game_pk"], sort=False)

    n_pa         = grp["is_hit"].count()
    hits         = grp["is_hit"].sum()
    n_contact    = grp["has_contact"].sum()
    hard_hit_sum = grp["is_hard_hit"].sum()
    sweet_sum    = grp["is_sweet"].sum()
    ev_sum       = grp["launch_speed"].sum()

    result = pd.DataFrame({
        "hits":      hits,
        "pa":        n_pa,
        "n_contact": n_contact,
    }).reset_index()

    result["hard_hit_pct"] = (
        hard_hit_sum.values / np.where(n_contact.values > 0, n_contact.values, np.nan)
    )
    result["sweet_spot_pct"] = (
        sweet_sum.values / np.where(n_contact.values > 0, n_contact.values, np.nan)
    )
    result["avg_exit_velo"] = (
        ev_sum.values / np.where(n_contact.values > 0, n_contact.values, np.nan)
    )

    if "barrel" in pa.columns:
        barrel_sum = grp["barrel"].sum()
        result["barrel_rate"] = (
            barrel_sum.values / np.where(n_contact.values > 0, n_contact.values, np.nan)
        )
    else:
        result["barrel_rate"] = np.nan

    if "estimated_ba_using_speedangle" in pa.columns:
        xba_mean = grp["estimated_ba_using_speedangle"].mean()
        result["xba"] = xba_mean.values
    else:
        result["xba"] = np.nan

    # Pitcher handedness per game (majority vote)
    if "p_throws" in pa.columns:
        p_throws = pa.groupby(["batter", "game_date", "game_pk"])["p_throws"].agg(
            lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan
        ).reset_index()
        result = result.merge(p_throws, on=["batter", "game_date", "game_pk"], how="left")
    else:
        result["p_throws"] = np.nan

    return result


# ---------------------------------------------------------------------------
# Rolling feature computation for a single batter
# ---------------------------------------------------------------------------

def _compute_batter_features(
    batter_id: int,
    batter_history: pd.DataFrame,
    pitcher_hand: Optional[str],
    is_home: bool,
    home_team_abbr: str,
) -> dict:
    """
    Compute all HITTING_FEATURE_COLS from recent game history.
    Uses np.nan for features that cannot be computed.
    """
    prior = batter_history.sort_values("game_date")

    def h_per_pa(df: pd.DataFrame) -> float:
        total_pa = df["pa"].sum()
        return float(df["hits"].sum() / total_pa) if total_pa > 0 else np.nan

    today_ts  = pd.Timestamp(date.today())
    last7     = prior[prior["game_date"] >= today_ts - pd.Timedelta(days=7)]
    last14    = prior[prior["game_date"] >= today_ts - pd.Timedelta(days=14)]
    last30    = prior[prior["game_date"] >= today_ts - pd.Timedelta(days=30)]
    last60    = prior[prior["game_date"] >= today_ts - pd.Timedelta(days=60)]
    season_df = prior[prior["game_date"].dt.year == today_ts.year]

    feats = {
        "h_per_pa_last7":   h_per_pa(last7)   if not last7.empty  else np.nan,
        "h_per_pa_last14":  h_per_pa(last14)  if not last14.empty else np.nan,
        "h_per_pa_last30":  h_per_pa(last30)  if not last30.empty else np.nan,
        "h_per_pa_season":  h_per_pa(season_df) if not season_df.empty else np.nan,
        # Contact quality — 30-day rolling means
        "barrel_rate_last30":    float(last30["barrel_rate"].mean())    if not last30.empty else np.nan,
        "hard_hit_pct_last30":   float(last30["hard_hit_pct"].mean())   if not last30.empty else np.nan,
        "xba_last30":            float(last30["xba"].mean())            if not last30.empty else np.nan,
        "avg_exit_velo_last30":  float(last30["avg_exit_velo"].mean())  if not last30.empty else np.nan,
        "sweet_spot_pct_last30": float(last30["sweet_spot_pct"].mean()) if not last30.empty else np.nan,
        # PA per game proxy (lineup-spot depth)
        "pa_per_game_last14":    float(last14["pa"].mean()) if not last14.empty else np.nan,
        # Platoon split — NaN when pitcher hand unknown
        "h_per_pa_vs_hand_last60": np.nan,
        # Opponent pitcher quality — filled by caller if available, else NaN
        "opp_k_pct":              np.nan,
        "opp_hard_hit_pct_allowed": np.nan,
        "opp_xba_allowed":        np.nan,
        # Context
        "park_factor": float(_PARK_FACTORS.get(home_team_abbr, 1.0)),
        "is_home":     float(int(is_home)),
    }

    # Platoon split
    if pitcher_hand and "p_throws" in prior.columns:
        vs_hand = last60[last60["p_throws"] == pitcher_hand]
        if not vs_hand.empty:
            feats["h_per_pa_vs_hand_last60"] = h_per_pa(vs_hand)

    return feats


# ---------------------------------------------------------------------------
# DraftKings batter hit lines
# ---------------------------------------------------------------------------

def _get_batter_hit_lines() -> dict[str, dict]:
    """
    Fetch today's DraftKings batter hit prop lines via The Odds API.
    Market key: batter_hits

    Returns {name_lower: {line, over_odds, under_odds, book}} or {} on failure.

    NOTE: If odds_api.get_batter_hit_lines() is implemented in the future,
    call that instead.  This implementation calls The Odds API directly using
    the same _get/_api_key helpers to avoid duplicating auth logic.
    """
    # Import the shared HTTP helper and credentials from odds_api
    try:
        from backend.app.data.odds_api import _get as _odds_get, PREFERRED_BOOKS
        BATTER_MARKET = "batter_hits"
        SPORT         = "baseball_mlb"
        REGIONS       = "us"
        FMT           = "american"

        print("[hitting_pipeline] Fetching DK batter hit lines via The Odds API...")
        events = _odds_get(f"/sports/{SPORT}/events", {"regions": REGIONS})
        if not isinstance(events, list):
            print("[hitting_pipeline] Unexpected events response — returning empty lines.")
            return {}

        result: dict[str, dict] = {}

        for event in events:
            event_id = event.get("id")
            if not event_id:
                continue
            try:
                odds = _odds_get(
                    f"/sports/{SPORT}/events/{event_id}/odds",
                    {
                        "regions":    REGIONS,
                        "markets":    BATTER_MARKET,
                        "oddsFormat": FMT,
                    },
                )
                # Parse bookmakers — prefer DraftKings first
                bookmakers = odds.get("bookmakers", [])

                def _book_rank(bm):
                    title = bm.get("title", "")
                    try:
                        return PREFERRED_BOOKS.index(title)
                    except ValueError:
                        return len(PREFERRED_BOOKS)

                bookmakers = sorted(bookmakers, key=_book_rank)

                for bookmaker in bookmakers:
                    book = bookmaker.get("title", "")
                    for market in bookmaker.get("markets", []):
                        if market.get("key") != BATTER_MARKET:
                            continue
                        outcomes = market.get("outcomes", [])
                        # First pass: over lines
                        for outcome in outcomes:
                            name  = (outcome.get("description") or outcome.get("name") or "").strip()
                            point = outcome.get("point")
                            price = outcome.get("price")
                            label = (outcome.get("name") or "").lower()
                            if not name or point is None or "over" not in label:
                                continue
                            key = name.lower()
                            if key not in result:
                                result[key] = {
                                    "line":       float(point),
                                    "over_odds":  int(price) if price is not None else -115,
                                    "under_odds": -115,
                                    "book":       book,
                                }
                        # Second pass: under_odds for recorded entries
                        for outcome in outcomes:
                            name  = (outcome.get("description") or outcome.get("name") or "").strip()
                            price = outcome.get("price")
                            label = (outcome.get("name") or "").lower()
                            key   = name.lower()
                            if (
                                key in result
                                and result[key]["book"] == book
                                and "under" in label
                                and price is not None
                            ):
                                result[key]["under_odds"] = int(price)
            except Exception as exc:
                print(f"  [hitting_pipeline] event {event_id}: {exc}")

        print(f"[hitting_pipeline] {len(result)} batter hit lines fetched.")
        return result

    except Exception as exc:
        print(f"[hitting_pipeline] Could not fetch batter hit lines: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Player ID lookup — resolves name → MLBAM ID + team, with persistent cache
# ---------------------------------------------------------------------------

def _resolve_player_id(name_lower: str) -> Optional[dict]:
    """
    Return {mlbam_id, team} for a batter, using the module-level cache.
    Calls pybaseball.playerid_lookup() on cache miss.
    """
    if name_lower in _player_id_cache:
        return _player_id_cache[name_lower]

    parts = name_lower.strip().split()
    if len(parts) < 2:
        return None

    first = parts[0].capitalize()
    last  = " ".join(parts[1:]).title()

    try:
        from pybaseball import playerid_lookup
        result_df = playerid_lookup(last, first, fuzzy=True)
        if result_df is None or result_df.empty:
            print(f"  [hitting_pipeline] No MLBAM ID found for '{name_lower}'")
            return None
        row      = result_df.iloc[0]
        mlbam_id = int(row["key_mlbam"])
        entry    = {"mlbam_id": mlbam_id, "team": ""}
        _player_id_cache[name_lower] = entry
        return entry
    except Exception as exc:
        print(f"  [hitting_pipeline] playerid_lookup error for '{name_lower}': {exc}")
        return None


def _get_current_team(mlbam_id: int) -> str:
    """
    Fetch the player's current team abbreviation from the MLB Stats API.
    Returns "" on failure.
    """
    import urllib.request, json as _json
    try:
        url = f"https://statsapi.mlb.com/api/v1/people/{mlbam_id}?hydrate=currentTeam"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = _json.loads(r.read())
        people = data.get("people", [])
        if not people:
            return ""
        team = people[0].get("currentTeam", {})
        return team.get("abbreviation", "")
    except Exception as exc:
        print(f"  [hitting_pipeline] currentTeam lookup failed for {mlbam_id}: {exc}")
        return ""


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def build_live_hitting_slate(game_date: Optional[str] = None) -> list[dict]:
    """
    Build a live batter slate compatible with _run_hitting_slate() in app.py.

    Steps:
      1. Fetch DraftKings batter hit prop lines.
      2. Resolve each batter name → MLBAM ID + current team.
      3. Load today's team matchup map for home/away and opponent info.
      4. Load recent Statcast (~90 days) and aggregate to batter-game level.
      5. Compute feature vectors from rolling history.
      6. Return slate list.

    Returns [] gracefully if lines or Statcast data are unavailable.
    """
    if game_date is None:
        game_date = date.today().isoformat()

    # ------------------------------------------------------------------
    # Step 1 — DraftKings lines
    # ------------------------------------------------------------------
    lines = _get_batter_hit_lines()
    if not lines:
        print("[hitting_pipeline] No batter hit lines available — returning empty slate.")
        return []

    # ------------------------------------------------------------------
    # Step 2 & 3 — MLBAM IDs + matchup map
    # ------------------------------------------------------------------
    from backend.app.data.mlb_api import get_team_matchups_today

    try:
        matchup_map = get_team_matchups_today(game_date)
        print(f"[hitting_pipeline] {len(matchup_map)} team matchups loaded.")
    except Exception as exc:
        print(f"[hitting_pipeline] Could not fetch matchups: {exc} — home/away will be unknown.")
        matchup_map = {}

    # ------------------------------------------------------------------
    # Step 4 — Statcast
    # ------------------------------------------------------------------
    print("[hitting_pipeline] Loading recent Statcast (~90 days)...")
    t0 = time.time()
    sc = _load_recent_statcast(days=95)
    if sc.empty:
        print("[hitting_pipeline] Statcast data empty — returning empty slate.")
        return []
    print(f"[hitting_pipeline] {len(sc):,} pitches loaded in {time.time()-t0:.1f}s.")

    print("[hitting_pipeline] Aggregating batter-game rows...")
    game_df = _aggregate_batter_games(sc)
    print(f"[hitting_pipeline] {len(game_df):,} batter-game rows.")

    # Index by batter_id for fast lookup
    if game_df.empty:
        batter_index: dict[int, pd.DataFrame] = {}
    else:
        game_df["game_date"] = pd.to_datetime(game_df["game_date"])
        batter_index = {
            int(bid): grp.reset_index(drop=True)
            for bid, grp in game_df.groupby("batter")
        }

    # ------------------------------------------------------------------
    # Step 5 & 6 — Build slate rows
    # ------------------------------------------------------------------
    slate: list[dict] = []
    skipped = 0

    for name_lower, line_info in lines.items():
        # Resolve MLBAM ID
        player_entry = _resolve_player_id(name_lower)
        if player_entry is None:
            skipped += 1
            continue

        mlbam_id = player_entry["mlbam_id"]

        # Fetch team if not yet cached
        if not player_entry.get("team"):
            team_abbr = _get_current_team(mlbam_id)
            player_entry["team"] = team_abbr
            _player_id_cache[name_lower]["team"] = team_abbr
        else:
            team_abbr = player_entry["team"]

        # Validate team has a game today
        matchup = matchup_map.get(team_abbr)
        if not matchup:
            print(f"  [hitting_pipeline] {name_lower} ({team_abbr}): no game today — skipping stale DK prop.")
            skipped += 1
            continue

        is_home        = bool(matchup.get("is_home", False))
        opponent_abbr  = matchup.get("opponent_abbr", "???")

        # Home team determines park factor
        home_team_abbr = team_abbr if is_home else opponent_abbr

        # Batter history from Statcast
        batter_history = batter_index.get(mlbam_id)
        if batter_history is None or batter_history.empty:
            print(f"  [hitting_pipeline] {name_lower}: no Statcast history — using NaN features.")
            feats = {
                "h_per_pa_last7":         np.nan,
                "h_per_pa_last14":        np.nan,
                "h_per_pa_last30":        np.nan,
                "h_per_pa_season":        np.nan,
                "barrel_rate_last30":     np.nan,
                "hard_hit_pct_last30":    np.nan,
                "xba_last30":             np.nan,
                "avg_exit_velo_last30":   np.nan,
                "sweet_spot_pct_last30":  np.nan,
                "pa_per_game_last14":     np.nan,
                "h_per_pa_vs_hand_last60": np.nan,
                "opp_k_pct":              np.nan,
                "opp_hard_hit_pct_allowed": np.nan,
                "opp_xba_allowed":        np.nan,
                "park_factor": float(_PARK_FACTORS.get(home_team_abbr, 1.0)),
                "is_home":     float(int(is_home)),
            }
        else:
            # Pitcher handedness — we don't know today's starter here, so use NaN for platoon
            feats = _compute_batter_features(
                batter_id      = mlbam_id,
                batter_history = batter_history,
                pitcher_hand   = None,     # opp pitcher not resolved here; NaN for platoon
                is_home        = is_home,
                home_team_abbr = home_team_abbr,
            )

        # Construct display name from dict key (title-case)
        display_name = " ".join(w.capitalize() for w in name_lower.split())

        slate.append({
            "batter_name":   display_name,
            "mlbam_id":      mlbam_id,
            "team":          team_abbr,
            "opponent_abbr": opponent_abbr,
            "is_home":       is_home,
            "line":          line_info["line"],
            "over_odds":     line_info["over_odds"],
            "under_odds":    line_info["under_odds"],
            "features":      feats,
        })

    print(
        f"[hitting_pipeline] Slate built: {len(slate)} batters "
        f"({skipped} skipped — no game today or ID not found)."
    )
    return slate
