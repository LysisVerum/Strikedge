"""
Umpire strikeout rate feature.

Builds a historical K-rate per home plate umpire from MLB API boxscores
and Statcast pitch data. Cached to artifacts/umpire_stats.json.

Usage:
    from app.data.umpire import get_umpire_k_rate, get_game_umpire_id

    # Historical (training): umpire's K rate going into a specific date
    k_rate = get_umpire_k_rate(umpire_id=503586, before_date='2024-05-01')

    # Live: today's home plate umpire for a specific game
    umpire_id = get_game_umpire_id(game_pk=745457)
"""
import json
import urllib.request
import time
from pathlib import Path
from datetime import date

CACHE_PATH   = Path(__file__).parent.parent.parent / "artifacts" / "umpire_stats.json"
LEAGUE_K_PCT = 0.222  # fallback league average K rate


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def _save_cache(data: dict):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, indent=2))


def get_game_umpire_id(game_pk: int) -> int | None:
    """Fetch the home plate umpire ID for a specific game from MLB API."""
    url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        for o in data.get("officials", []):
            if o.get("officialType") == "Home Plate":
                return int(o["official"]["id"])
    except Exception:
        pass
    return None


def get_schedule_umpire_id(game_pk: int, game_date: str) -> int | None:
    """Get home plate umpire from schedule endpoint (works for today's games)."""
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={game_date}&hydrate=officials&gamePk={game_pk}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        for date_entry in data.get("dates", []):
            for game in date_entry.get("games", []):
                if game.get("gamePk") == game_pk:
                    for o in game.get("officials", []):
                        if o.get("officialType") == "Home Plate":
                            return int(o["official"]["id"])
    except Exception:
        pass
    return None


def _fetch_season_umpires(season: int) -> dict[str, int]:
    """
    Fetch all game_pk → umpire_id mappings for a season in bulk.
    Uses the schedule endpoint with officials hydrated — one call per month
    instead of one call per game.
    """
    import calendar
    result = {}
    for month in range(3, 11):
        _, last_day = calendar.monthrange(season, month)
        start = f"{season}-{month:02d}-01"
        end   = f"{season}-{month:02d}-{last_day:02d}"
        url   = (
            f"https://statsapi.mlb.com/api/v1/schedule"
            f"?sportId=1&startDate={start}&endDate={end}"
            f"&hydrate=officials&gameType=R"
        )
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.loads(r.read())
            for date_entry in data.get("dates", []):
                for game in date_entry.get("games", []):
                    gk = str(game.get("gamePk", ""))
                    for o in game.get("officials", []):
                        if o.get("officialType") == "Home Plate":
                            result[gk] = int(o["official"]["id"])
                            break
        except Exception as e:
            print(f"    [warn] {start}: {e}")
        time.sleep(0.2)
    return result


def build_umpire_stats(seasons: list[int]) -> dict:
    """
    Build per-umpire K rate stats from schedule endpoint (bulk) + Statcast.
    Uses SP-only plate appearances for K rate calculation.
    One schedule call per month instead of one boxscore call per game.
    """
    from pybaseball import statcast
    import pandas as pd

    cache = _load_cache()
    ump_games = cache.get("games", {})

    print(f"Building umpire stats for seasons {seasons}...")

    for season in seasons:
        print(f"\n  Season {season}...")

        # Step 1: bulk-fetch all umpire assignments for the season (~8 API calls)
        print(f"    Fetching umpire assignments...")
        season_ump_map = _fetch_season_umpires(season)
        print(f"    {len(season_ump_map)} games with umpire data")

        # Step 2: Statcast for this season (already cached by pybaseball)
        print(f"    Loading Statcast data...")
        sc = statcast(f"{season}-04-01", f"{season}-10-01")
        sc = sc[sc["game_type"] == "R"]

        # Step 3: SP-only K rate per game
        # Identify starter as the pitcher with the lowest pitch number in inning 1
        sp_ids = (
            sc[sc["inning"] == 1]
            .sort_values("pitch_number")
            .groupby(["game_pk", "inning_topbot"])["pitcher"]
            .first()
            .reset_index()
            .rename(columns={"pitcher": "sp_id"})
        )
        # Keep only SP plate appearances (their full outing, not just inning 1)
        sc_sp = sc.merge(sp_ids, on=["game_pk", "inning_topbot"])
        sc_sp = sc_sp[sc_sp["pitcher"] == sc_sp["sp_id"]]

        game_agg = (
            sc_sp.groupby("game_pk")
            .agg(
                game_date = ("game_date", "first"),
                total_k   = ("events", lambda x: (x == "strikeout").sum()),
                total_pa  = ("events", lambda x: x.notna().sum()),
            )
            .reset_index()
        )

        new_games = 0
        for _, row in game_agg.iterrows():
            gk = str(int(row["game_pk"]))
            if gk in ump_games:
                continue
            ump_id = season_ump_map.get(gk)
            if ump_id and row["total_pa"] > 0:
                ump_games[gk] = {
                    "date":      str(row["game_date"])[:10],
                    "umpire_id": ump_id,
                    "k_pct":     round(float(row["total_k"]) / float(row["total_pa"]), 4),
                    "total_k":   int(row["total_k"]),
                    "total_pa":  int(row["total_pa"]),
                }
                new_games += 1

        print(f"    {new_games} new games added")

    cache["games"] = ump_games
    _save_cache(cache)
    print(f"\nTotal games cached: {len(ump_games)}")
    return cache


def get_umpire_k_rate(umpire_id: int, before_date: str) -> float:
    """
    Returns the umpire's historical K rate across all games before before_date.
    Falls back to league average if no history.
    """
    cache = _load_cache()
    games = cache.get("games", {})

    total_k  = 0
    total_pa = 0
    for g in games.values():
        if g.get("umpire_id") == umpire_id and g.get("date", "") < before_date:
            total_k  += g.get("total_k", 0)
            total_pa += g.get("total_pa", 0)

    if total_pa < 500:  # need meaningful sample
        return LEAGUE_K_PCT
    return round(total_k / total_pa, 4)


def get_todays_umpires(game_date: str) -> dict[int, int]:
    """
    Returns {game_pk: umpire_id} for all games today.
    """
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={game_date}&hydrate=officials"
    result = {}
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        for date_entry in data.get("dates", []):
            for game in date_entry.get("games", []):
                game_pk = game.get("gamePk")
                for o in game.get("officials", []):
                    if o.get("officialType") == "Home Plate":
                        result[game_pk] = int(o["official"]["id"])
    except Exception as e:
        print(f"  [umpire] Could not fetch today's umpires: {e}")
    return result
