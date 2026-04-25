"""
Fetches pitcher game logs and Statcast data via pybaseball.
Results are cached in-memory to avoid hammering Baseball Savant.
"""
import time
import functools
import pandas as pd
from pybaseball import pitching_stats, statcast_pitcher, playerid_lookup
from pybaseball import cache as pybb_cache

pybb_cache.enable()

_cache: dict = {}
_CACHE_TTL = 3600  # 1 hour


def _cached(key: str, ttl: int, fn):
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < ttl:
        return entry["data"]
    data = fn()
    _cache[key] = {"ts": time.time(), "data": data}
    return data


def get_season_pitching_stats(season: int) -> pd.DataFrame:
    key = f"pitching_stats_{season}"
    return _cached(key, _CACHE_TTL, lambda: pitching_stats(season, qual=20))


def get_pitcher_statcast(mlbam_id: int, start: str, end: str) -> pd.DataFrame:
    key = f"statcast_{mlbam_id}_{start}_{end}"
    return _cached(key, _CACHE_TTL, lambda: statcast_pitcher(start, end, mlbam_id))


def lookup_pitcher_id(last: str, first: str) -> int | None:
    result = playerid_lookup(last, first)
    if result.empty:
        return None
    row = result.iloc[0]
    return int(row["key_mlbam"])
