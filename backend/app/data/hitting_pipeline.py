"""
Hitting slate pipeline — mirrors the pitching pipeline.

1. Fetch DK batter hit lines from the Odds API (batter_hits market).
   Uses a 2-hour disk cache and 30-minute force-refresh throttle (same as
   strikeout lines) to protect Odds API credits.
2. Enrich with MLB confirmed lineup context (team, opponent, home/away).
3. Compute H/PA features from MLB Stats API game logs (free, same API used
   for pitcher K% data). Statcast contact-quality features stay NaN until a
   local parquet cache is built.
4. Returns a slate list for _run_hitting_slate() in app.py.
"""
import json
import time
import unicodedata
import warnings
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

_REPO_ROOT  = Path(__file__).parent.parent.parent   # backend/
_CACHE_DIR  = _REPO_ROOT / "artifacts" / "hitting_cache"
_ARTIFACTS  = _REPO_ROOT / "artifacts"

# ---------------------------------------------------------------------------
# Disk cache for DK hitting lines — 2-hour TTL, same pattern as odds_api.py
# ---------------------------------------------------------------------------

_HIT_DISK_TTL              = 7200   # 2 hours
_HIT_REFRESH_MIN_INTERVAL  = 1800   # 30 minutes between force-refreshes
_last_hit_fetch_ts: float  = 0.0


def _hit_cache_path() -> Path:
    return _ARTIFACTS / f"hit_lines_cache_{date.today().isoformat()}.json"


def _load_hit_disk_cache() -> dict | None:
    path = _hit_cache_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - payload.get("ts", 0)
        if age < _HIT_DISK_TTL:
            print(f"  [hitting] disk cache hit ({int(age)}s old) — skipping API calls")
            return payload["lines"]
    except Exception:
        pass
    return None


def _save_hit_disk_cache(lines: dict) -> None:
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = _hit_cache_path()
    path.write_text(json.dumps({"ts": time.time(), "lines": lines}, indent=2), encoding="utf-8")
    for old in _ARTIFACTS.glob("hit_lines_cache_*.json"):
        if old != path:
            try:
                old.unlink()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Team name → abbreviation (used to parse Odds API event home/away)
# ---------------------------------------------------------------------------

_TEAM_NAME_TO_ABBR: dict[str, str] = {
    "arizona diamondbacks": "ARI", "atlanta braves": "ATL",
    "baltimore orioles": "BAL",    "boston red sox": "BOS",
    "chicago white sox": "CWS",    "chicago cubs": "CHC",
    "cincinnati reds": "CIN",      "cleveland guardians": "CLE",
    "colorado rockies": "COL",     "detroit tigers": "DET",
    "houston astros": "HOU",       "kansas city royals": "KC",
    "los angeles angels": "LAA",   "los angeles dodgers": "LAD",
    "miami marlins": "MIA",        "milwaukee brewers": "MIL",
    "minnesota twins": "MIN",      "new york yankees": "NYY",
    "new york mets": "NYM",        "athletics": "OAK",
    "oakland athletics": "OAK",    "philadelphia phillies": "PHI",
    "pittsburgh pirates": "PIT",   "san diego padres": "SD",
    "san francisco giants": "SF",  "seattle mariners": "SEA",
    "st. louis cardinals": "STL",  "tampa bay rays": "TB",
    "texas rangers": "TEX",        "toronto blue jays": "TOR",
    "washington nationals": "WSH",
}

_PARK_FACTORS = {
    "COL": 1.12, "CIN": 1.07, "BOS": 1.06, "TEX": 1.05, "PHI": 1.04,
    "MIL": 1.03, "CLE": 1.02, "CHC": 1.01, "HOU": 1.01, "ARI": 1.01,
    "STL": 0.99, "NYY": 0.99, "ATL": 0.99, "LAD": 0.99, "TOR": 0.98,
    "MIN": 0.98, "SEA": 0.98, "TB":  0.97, "SF":  0.97, "DET": 0.97,
    "CWS": 0.97, "WSH": 0.96, "BAL": 0.96, "NYM": 0.96, "OAK": 0.96,
    "MIA": 0.95, "KC":  0.95, "LAA": 0.95, "PIT": 0.94, "SD":  0.94,
}

# ---------------------------------------------------------------------------
# Statcast columns (for parquet cache — populated from local data only)
# ---------------------------------------------------------------------------

_SC_COLS = [
    "game_date", "game_pk", "batter", "events", "p_throws",
    "launch_speed", "launch_angle", "estimated_ba_using_speedangle",
    "barrel", "inning_topbot",
]
_HIT_EVENTS = frozenset(["single", "double", "triple", "home_run"])
_NON_AB = frozenset([
    "walk", "intent_walk", "hit_by_pitch", "sac_fly", "sac_bunt",
    "sac_fly_double_play", "sac_bunt_double_play", "catcher_interf",
])

_sc_month_cache: dict[tuple, pd.DataFrame] = {}

# MLB Stats API game log cache: {mlbam_id: [{"date", "H", "PA", "AB"}]}
_mlb_log_cache: dict[int, list[dict]] = {}

# Batter name → MLBAM ID resolved from season leaderboard (no pybaseball)
_batter_id_cache: dict[str, int] = {}


def _norm(name: str) -> str:
    return unicodedata.normalize("NFD", name).encode("ascii", "ignore").decode().lower().strip()


def _resolve_batter_mlbam(name_lower: str) -> int:
    """
    Resolve a batter name to an MLBAM ID using the MLB Stats API season leaderboard.
    Same approach as search_pitcher() — free, no pybaseball.
    Returns 0 if no match found.
    """
    if name_lower in _batter_id_cache:
        return _batter_id_cache[name_lower]

    try:
        try:
            from backend.app.data.mlb_api import get_season_batter_ids
        except ImportError:
            from app.data.mlb_api import get_season_batter_ids

        season   = date.today().year
        batters  = get_season_batter_ids(season, min_pa=1)
        norm_q   = _norm(name_lower)
        last_q   = norm_q.split()[-1] if norm_q else ""

        # Exact match first
        for b in batters:
            if _norm(b["full_name"]) == norm_q:
                _batter_id_cache[name_lower] = b["mlbam_id"]
                return b["mlbam_id"]

        # Last-name match fallback
        for b in batters:
            norm_full = _norm(b["full_name"])
            if last_q and norm_full.split()[-1] == last_q:
                _batter_id_cache[name_lower] = b["mlbam_id"]
                return b["mlbam_id"]
    except Exception as exc:
        print(f"  [hitting_pipeline] MLBAM lookup failed for '{name_lower}': {exc}")

    _batter_id_cache[name_lower] = 0
    return 0


# ---------------------------------------------------------------------------
# Statcast — cache-only, never calls pybaseball at runtime
# ---------------------------------------------------------------------------

def _load_cached_statcast(days: int = 95) -> pd.DataFrame:
    """Load from parquet cache only. Never calls pybaseball."""
    today  = date.today()
    cutoff = pd.Timestamp(today) - pd.Timedelta(days=days)

    months: set[tuple] = set()
    from datetime import date as _date
    cur = _date(today.year, cutoff.month, 1)
    while cur <= today:
        months.add((cur.year, cur.month))
        if cur.month == 12:
            cur = _date(cur.year + 1, 1, 1)
        else:
            cur = _date(cur.year, cur.month + 1, 1)

    parts = []
    for (y, m) in sorted(months):
        key  = (y, m)
        if key in _sc_month_cache:
            parts.append(_sc_month_cache[key])
            continue
        path = _CACHE_DIR / f"sc_{y}_{m:02d}.parquet"
        if not path.exists():
            continue
        try:
            df   = pd.read_parquet(path)
            keep = [c for c in _SC_COLS if c in df.columns]
            df   = df[keep].copy()
            df["game_date"] = pd.to_datetime(df["game_date"])
            _sc_month_cache[key] = df
            parts.append(df)
        except Exception:
            pass

    if not parts:
        return pd.DataFrame(columns=_SC_COLS)

    df = pd.concat(parts, ignore_index=True)
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df[df["game_date"] >= cutoff].reset_index(drop=True)


def _aggregate_batter_games(sc: pd.DataFrame) -> pd.DataFrame:
    if sc.empty:
        return pd.DataFrame()
    pa = sc[sc["events"].notna()].copy()
    if pa.empty:
        return pd.DataFrame()

    pa["is_hit"]      = pa["events"].isin(_HIT_EVENTS).astype(np.int8)
    pa["is_hard_hit"] = (pa["launch_speed"] >= 95).fillna(False).astype(np.int8)
    pa["is_sweet"]    = (
        (pa["launch_angle"] >= 8) & (pa["launch_angle"] <= 32)
    ).fillna(False).astype(np.int8)
    pa["has_contact"] = pa["launch_speed"].notna().astype(np.int8)

    grp          = pa.groupby(["batter", "game_date", "game_pk"], sort=False)
    n_pa         = grp["is_hit"].count()
    hits         = grp["is_hit"].sum()
    n_contact    = grp["has_contact"].sum()
    hard_hit_sum = grp["is_hard_hit"].sum()
    sweet_sum    = grp["is_sweet"].sum()
    ev_sum       = grp["launch_speed"].sum()

    result = pd.DataFrame({"hits": hits, "pa": n_pa, "n_contact": n_contact}).reset_index()
    result["hard_hit_pct"]   = hard_hit_sum.values / np.where(n_contact.values > 0, n_contact.values, np.nan)
    result["sweet_spot_pct"] = sweet_sum.values     / np.where(n_contact.values > 0, n_contact.values, np.nan)
    result["avg_exit_velo"]  = ev_sum.values        / np.where(n_contact.values > 0, n_contact.values, np.nan)

    if "barrel" in pa.columns:
        result["barrel_rate"] = grp["barrel"].sum().values / np.where(n_contact.values > 0, n_contact.values, np.nan)
    else:
        result["barrel_rate"] = np.nan

    if "estimated_ba_using_speedangle" in pa.columns:
        result["xba"] = grp["estimated_ba_using_speedangle"].mean().values
    else:
        result["xba"] = np.nan

    if "p_throws" in pa.columns:
        p_throws = pa.groupby(["batter", "game_date", "game_pk"])["p_throws"].agg(
            lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan
        ).reset_index()
        result = result.merge(p_throws, on=["batter", "game_date", "game_pk"], how="left")
    else:
        result["p_throws"] = np.nan

    return result


# ---------------------------------------------------------------------------
# MLB Stats API game log features — free, same as pitcher K% data
# ---------------------------------------------------------------------------

def _get_mlb_log(mlbam_id: int) -> list[dict]:
    """
    Fetch game log from MLB Stats API for current + prior season.
    Fetching two seasons ensures players returning from IL still have recent
    stats from late last year (e.g., April returner has March prior-season data).
    Cached per session.
    """
    if mlbam_id in _mlb_log_cache:
        return _mlb_log_cache[mlbam_id]
    try:
        try:
            from backend.app.data.mlb_api import get_batter_game_log
        except ImportError:
            from app.data.mlb_api import get_batter_game_log
        year = date.today().year
        rows_this = get_batter_game_log(mlbam_id, year)
        rows_last: list[dict] = []
        try:
            rows_last = get_batter_game_log(mlbam_id, year - 1)
        except Exception:
            pass
        rows = rows_this + rows_last
        _mlb_log_cache[mlbam_id] = rows
        return rows
    except Exception:
        _mlb_log_cache[mlbam_id] = []
        return []


def _features_from_mlb_log(
    mlbam_id: int,
    is_home: bool,
    home_team_abbr: str,
) -> dict:
    """
    Compute H/PA rolling features from the MLB Stats API game log (2 seasons).
    Populates h_per_pa_* and pa_per_game_* features.
    Statcast contact-quality features remain NaN (not available from Stats API).
    Also adds h60/h90 as display-only fallback fields for the UI.
    """
    rows = _get_mlb_log(mlbam_id)

    feats = _nan_feats(home_team_abbr, is_home)
    if not rows:
        return feats

    today = pd.Timestamp(date.today())
    df    = pd.DataFrame(rows)
    df["game_date"] = pd.to_datetime(df["date"])

    def h_per_pa(sub: pd.DataFrame) -> float:
        total = sub["PA"].sum()
        return float(sub["H"].sum() / total) if total > 0 else np.nan

    last7   = df[df["game_date"] >= today - pd.Timedelta(days=7)]
    last14  = df[df["game_date"] >= today - pd.Timedelta(days=14)]
    last30  = df[df["game_date"] >= today - pd.Timedelta(days=30)]
    last60  = df[df["game_date"] >= today - pd.Timedelta(days=60)]
    last90  = df[df["game_date"] >= today - pd.Timedelta(days=90)]
    season  = df[df["game_date"].dt.year == today.year]

    feats["h_per_pa_last7"]     = h_per_pa(last7)  if not last7.empty  else np.nan
    feats["h_per_pa_last14"]    = h_per_pa(last14) if not last14.empty else np.nan
    feats["h_per_pa_last30"]    = h_per_pa(last30) if not last30.empty else np.nan
    feats["h_per_pa_season"]    = h_per_pa(season) if not season.empty else np.nan
    feats["pa_per_game_last14"] = (
        float(last14["PA"].mean()) if not last14.empty
        else float(last30["PA"].mean()) if not last30.empty
        else float(last60["PA"].mean()) if not last60.empty
        else np.nan
    )
    # Extra display-only fields (not model features) for fallback bars in the UI
    feats["_h60"] = h_per_pa(last60) if not last60.empty else np.nan
    feats["_h90"] = h_per_pa(last90) if not last90.empty else np.nan

    return feats


def _compute_batter_features_sc(
    mlbam_id: int,
    batter_history: pd.DataFrame,
    is_home: bool,
    home_team_abbr: str,
) -> dict:
    """Compute features from cached Statcast data (richer: includes contact quality)."""
    prior   = batter_history.sort_values("game_date")
    today_t = pd.Timestamp(date.today())

    def h_per_pa(df):
        total = df["pa"].sum()
        return float(df["hits"].sum() / total) if total > 0 else np.nan

    last7  = prior[prior["game_date"] >= today_t - pd.Timedelta(days=7)]
    last14 = prior[prior["game_date"] >= today_t - pd.Timedelta(days=14)]
    last30 = prior[prior["game_date"] >= today_t - pd.Timedelta(days=30)]
    season = prior[prior["game_date"].dt.year == today_t.year]

    return {
        "h_per_pa_last7":           h_per_pa(last7)  if not last7.empty  else np.nan,
        "h_per_pa_last14":          h_per_pa(last14) if not last14.empty else np.nan,
        "h_per_pa_last30":          h_per_pa(last30) if not last30.empty else np.nan,
        "h_per_pa_season":          h_per_pa(season) if not season.empty else np.nan,
        "barrel_rate_last30":       float(last30["barrel_rate"].mean())    if not last30.empty else np.nan,
        "hard_hit_pct_last30":      float(last30["hard_hit_pct"].mean())   if not last30.empty else np.nan,
        "xba_last30":               float(last30["xba"].mean())            if not last30.empty else np.nan,
        "avg_exit_velo_last30":     float(last30["avg_exit_velo"].mean())  if not last30.empty else np.nan,
        "sweet_spot_pct_last30":    float(last30["sweet_spot_pct"].mean()) if not last30.empty else np.nan,
        "pa_per_game_last14":       float(last14["pa"].mean())             if not last14.empty else np.nan,
        "h_per_pa_vs_hand_last60":  np.nan,
        "opp_k_pct":                np.nan,
        "opp_hard_hit_pct_allowed": np.nan,
        "opp_xba_allowed":          np.nan,
        "park_factor": float(_PARK_FACTORS.get(home_team_abbr, 1.0)),
        "is_home":     float(int(is_home)),
    }


def _nan_feats(home_team_abbr: str, is_home: bool) -> dict:
    return {
        "h_per_pa_last7":           np.nan,
        "h_per_pa_last14":          np.nan,
        "h_per_pa_last30":          np.nan,
        "h_per_pa_season":          np.nan,
        "barrel_rate_last30":       np.nan,
        "hard_hit_pct_last30":      np.nan,
        "xba_last30":               np.nan,
        "avg_exit_velo_last30":     np.nan,
        "sweet_spot_pct_last30":    np.nan,
        "pa_per_game_last14":       np.nan,
        "h_per_pa_vs_hand_last60":  np.nan,
        "opp_k_pct":                np.nan,
        "opp_hard_hit_pct_allowed": np.nan,
        "opp_xba_allowed":          np.nan,
        "park_factor": float(_PARK_FACTORS.get(home_team_abbr, 1.0)),
        "is_home":     float(int(is_home)),
    }


# ---------------------------------------------------------------------------
# DraftKings batter hit lines — disk-cached, throttled
# ---------------------------------------------------------------------------

def _get_batter_hit_lines(force_refresh: bool = False) -> dict[str, dict]:
    """
    Fetch DK batter hit prop lines from Odds API (batter_hits market).
    Uses a 2-hour disk cache and 30-minute force-refresh throttle.
    Returns {name_lower: {line, over_odds, under_odds, book,
                          home_team_abbr, away_team_abbr}}.
    """
    global _last_hit_fetch_ts

    if force_refresh:
        age = time.time() - _last_hit_fetch_ts
        if age < _HIT_REFRESH_MIN_INTERVAL:
            print(f"  [hitting] force_refresh throttled — last fetch was {int(age / 60)}m ago")
            force_refresh = False

    if not force_refresh:
        cached = _load_hit_disk_cache()
        if cached is not None:
            return cached

    try:
        from backend.app.data.odds_api import _get as _odds_get, PREFERRED_BOOKS
    except ImportError:
        from app.data.odds_api import _get as _odds_get, PREFERRED_BOOKS

    SPORT  = "baseball_mlb"
    MARKET = "batter_hits"

    print("[hitting_pipeline] Fetching DK batter hit lines from Odds API...")
    try:
        events = _odds_get(f"/sports/{SPORT}/events", {"regions": "us"})
    except Exception as exc:
        print(f"[hitting_pipeline] Could not fetch events: {exc}")
        return {}

    if not isinstance(events, list):
        return {}

    def _book_rank(bm):
        title = bm.get("title", "")
        try:
            return PREFERRED_BOOKS.index(title)
        except ValueError:
            return len(PREFERRED_BOOKS)

    result: dict[str, dict] = {}

    for event in events:
        event_id       = event.get("id")
        home_team_name = event.get("home_team", "")
        away_team_name = event.get("away_team", "")
        home_abbr = _TEAM_NAME_TO_ABBR.get(home_team_name.lower(), "")
        away_abbr = _TEAM_NAME_TO_ABBR.get(away_team_name.lower(), "")
        if not event_id:
            continue
        try:
            odds = _odds_get(
                f"/sports/{SPORT}/events/{event_id}/odds",
                {"regions": "us", "markets": MARKET, "oddsFormat": "american"},
            )
            bookmakers = sorted(odds.get("bookmakers", []), key=_book_rank)
            for bm in bookmakers:
                book = bm.get("title", "")
                for mkt in bm.get("markets", []):
                    if mkt.get("key") != MARKET:
                        continue
                    outcomes = mkt.get("outcomes", [])
                    for o in outcomes:
                        name  = (o.get("description") or "").strip()
                        point = o.get("point")
                        price = o.get("price")
                        label = (o.get("name") or "").lower()
                        if not name or point is None or "over" not in label:
                            continue
                        key = name.lower()
                        if key not in result:
                            result[key] = {
                                "line":           float(point),
                                "over_odds":      int(price) if price is not None else -115,
                                "under_odds":     -115,
                                "book":           book,
                                "home_team_abbr": home_abbr,
                                "away_team_abbr": away_abbr,
                            }
                    for o in outcomes:
                        name  = (o.get("description") or "").strip()
                        price = o.get("price")
                        label = (o.get("name") or "").lower()
                        key   = name.lower()
                        if key in result and result[key]["book"] == book and "under" in label and price is not None:
                            result[key]["under_odds"] = int(price)
        except Exception as exc:
            print(f"  [hitting_pipeline] event {event_id}: {exc}")

    print(f"[hitting_pipeline] {len(result)} batter hit lines fetched from API.")
    _save_hit_disk_cache(result)
    _last_hit_fetch_ts = time.time()
    return result


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def build_live_hitting_slate(
    game_date: Optional[str] = None,
    force_refresh: bool = False,
) -> list[dict]:
    """
    Build today's batter slate.

    1. Get DK batter hit lines (disk-cached, throttled — protects API credits).
    2. Get MLB confirmed lineups for team/opponent/home context + MLBAM IDs.
    3. Compute features: Statcast from parquet cache if available, otherwise
       MLB Stats API game logs (free, same API used for pitcher K% data).
    4. Return slate; model handles NaN features natively.
    """
    if game_date is None:
        game_date = date.today().isoformat()

    # Step 1 — DK lines (cached)
    lines = _get_batter_hit_lines(force_refresh=force_refresh)
    if not lines:
        print("[hitting_pipeline] No DK hit lines — returning empty slate.")
        return []

    # Step 2 — MLB lineup context for MLBAM IDs + team info (best effort)
    lineup_by_name: dict[str, dict] = {}
    try:
        try:
            from backend.app.data.mlb_api import get_todays_lineup_batters
        except ImportError:
            from app.data.mlb_api import get_todays_lineup_batters
        for b in get_todays_lineup_batters(game_date):
            lineup_by_name[_norm(b["full_name"])] = b
        print(f"[hitting_pipeline] {len(lineup_by_name)} confirmed lineup batters.")
    except Exception as exc:
        print(f"[hitting_pipeline] Lineup lookup skipped: {exc}")

    # Step 3 — Statcast from parquet cache (richer features; may be empty for current season)
    sc = _load_cached_statcast(days=95)
    batter_index: dict[int, pd.DataFrame] = {}
    if not sc.empty:
        game_df = _aggregate_batter_games(sc)
        game_df["game_date"] = pd.to_datetime(game_df["game_date"])
        batter_index = {
            int(bid): grp.reset_index(drop=True)
            for bid, grp in game_df.groupby("batter")
        }
        print(f"[hitting_pipeline] Statcast cache: {len(batter_index)} batters.")
    else:
        print("[hitting_pipeline] No cached Statcast — using MLB Stats API game logs.")

    # Step 4 — Build slate
    slate: list[dict] = []
    seen:  set[str]   = set()

    for name_lower, line_info in lines.items():
        if name_lower in seen:
            continue
        seen.add(name_lower)

        home_abbr    = line_info.get("home_team_abbr", "")
        away_abbr    = line_info.get("away_team_abbr", "")
        display_name = " ".join(w.capitalize() for w in name_lower.split())

        # Match to confirmed lineup entry (MLBAM ID + team context)
        lineup_entry = lineup_by_name.get(_norm(display_name))
        if lineup_entry is None:
            last = _norm(display_name).split()[-1] if display_name else ""
            for k, v in lineup_by_name.items():
                if last and k.split()[-1] == last:
                    lineup_entry = v
                    break

        if lineup_entry:
            mlbam_id       = lineup_entry["mlbam_id"]
            team_abbr      = lineup_entry["team_abbr"]
            opponent_abbr  = lineup_entry["opponent_abbr"]
            is_home        = lineup_entry["is_home"]
            home_team_abbr = lineup_entry["home_team_abbr"]
        else:
            # No lineup yet — resolve MLBAM ID from season leaderboard (free MLB API)
            mlbam_id       = _resolve_batter_mlbam(name_lower)
            team_abbr      = home_abbr or "???"
            opponent_abbr  = away_abbr or "???"
            is_home        = True
            home_team_abbr = home_abbr

        # Feature priority: Statcast cache → MLB Stats API game log → NaN
        sc_history = batter_index.get(mlbam_id) if mlbam_id else None
        if sc_history is not None and not sc_history.empty:
            feats = _compute_batter_features_sc(mlbam_id, sc_history, is_home, home_team_abbr)
        elif mlbam_id:
            feats = _features_from_mlb_log(mlbam_id, is_home, home_team_abbr)
        else:
            feats = _nan_feats(home_team_abbr, is_home)

        slate.append({
            "batter_name":   display_name,
            "mlbam_id":      mlbam_id,
            "team":          team_abbr,
            "opponent_abbr": opponent_abbr,
            "is_home":       is_home,
            "has_line":      True,
            "book":          line_info.get("book", "DraftKings"),
            "line":          line_info["line"],
            "over_odds":     line_info["over_odds"],
            "under_odds":    line_info["under_odds"],
            "features":      feats,
        })

    print(f"[hitting_pipeline] Slate: {len(slate)} batters.")
    return slate
