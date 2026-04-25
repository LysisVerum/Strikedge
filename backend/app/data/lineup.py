"""
Lineup-based opponent K rate.

Replaces team-level opp_k_pct with the weighted K rate of the actual
9 batters in the lineup for that specific game — much more precise.

Uses prior-season batter K rates to avoid leakage (same rule as opp_k_pct).
Both batter stats and game lineups are cached to disk.
"""
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

ARTIFACT_DIR = Path(__file__).parent.parent.parent / "artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)

BASE = "https://statsapi.mlb.com/api/v1"
_LEAGUE_K_PCT = 0.225


def _get(path: str, params: dict = None) -> dict:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read())


# ---------------------------------------------------------------------------
# Batter season K rates  {player_id: k_pct}
# ---------------------------------------------------------------------------

def get_season_batter_k_pcts(season: int) -> dict:
    """
    Returns {player_id: k_pct} for all batters with >= 50 PA in a season.
    Cached to artifacts/batter_k_pcts_{season}.json.
    """
    cache_path = ARTIFACT_DIR / f"batter_k_pcts_{season}.json"
    if cache_path.exists():
        return {int(k): v for k, v in json.loads(cache_path.read_text()).items()}

    print(f"  Fetching batter K rates for {season}...")
    result = {}
    offset = 0
    limit  = 1000

    while True:
        data = _get("/stats", {
            "stats":    "season",
            "group":    "hitting",
            "season":   season,
            "sportId":  1,
            "gameType": "R",
            "limit":    limit,
            "offset":   offset,
        })
        splits = data.get("stats", [{}])[0].get("splits", [])
        if not splits:
            break
        for s in splits:
            stat = s.get("stat", {})
            pa   = int(stat.get("plateAppearances", 0))
            so   = int(stat.get("strikeOuts", 0))
            pid  = s.get("player", {}).get("id")
            if pid and pa >= 50:
                result[pid] = round(so / pa, 4)
        if len(splits) < limit:
            break
        offset += limit
        time.sleep(0.1)

    cache_path.write_text(json.dumps(result))
    print(f"    {len(result)} batters cached for {season}")
    return result


# ---------------------------------------------------------------------------
# Season game lineups  {game_pk: {"home": [ids], "away": [ids]}}
# ---------------------------------------------------------------------------

def get_season_lineups(season: int) -> dict:
    """
    Returns {game_pk: {"home": [player_id, ...], "away": [player_id, ...]}}
    for every regular-season game. Fetches month-by-month and caches to
    artifacts/lineups_{season}.json.
    """
    cache_path = ARTIFACT_DIR / f"lineups_{season}.json"
    if cache_path.exists():
        raw = json.loads(cache_path.read_text())
        return {int(k): v for k, v in raw.items()}

    print(f"  Fetching season lineups for {season}...")
    result = {}

    months = [
        (f"{season}-03-01", f"{season}-03-31"),
        (f"{season}-04-01", f"{season}-04-30"),
        (f"{season}-05-01", f"{season}-05-31"),
        (f"{season}-06-01", f"{season}-06-30"),
        (f"{season}-07-01", f"{season}-07-31"),
        (f"{season}-08-01", f"{season}-08-31"),
        (f"{season}-09-01", f"{season}-09-30"),
        (f"{season}-10-01", f"{season}-10-15"),
    ]

    for start, end in months:
        try:
            data = _get("/schedule", {
                "sportId":   1,
                "startDate": start,
                "endDate":   end,
                "gameType":  "R",
                "hydrate":   "lineups",
            })
            for date_entry in data.get("dates", []):
                for game in date_entry.get("games", []):
                    gid      = game.get("gamePk")
                    lineups  = game.get("lineups", {})
                    home_ids = [p["id"] for p in lineups.get("homePlayers", []) if p.get("id")]
                    away_ids = [p["id"] for p in lineups.get("awayPlayers", []) if p.get("id")]
                    if gid and (home_ids or away_ids):
                        result[gid] = {"home": home_ids, "away": away_ids}
            time.sleep(0.15)
        except Exception as e:
            print(f"    WARN lineups {start}: {e}")

    cache_path.write_text(json.dumps(result))
    print(f"    {len(result)} games with lineups cached for {season}")
    return result


# ---------------------------------------------------------------------------
# Compute lineup-weighted K rate
# ---------------------------------------------------------------------------

def compute_lineup_k_pct(
    player_ids: list,
    batter_k_pcts: dict,
    fallback: float = _LEAGUE_K_PCT,
) -> float:
    """
    Average K% of the batters in the lineup.
    Only uses batters with known prior-season K rates; fills gaps with fallback.
    Returns fallback if lineup is empty.
    """
    if not player_ids:
        return fallback
    rates = [batter_k_pcts.get(pid, fallback) for pid in player_ids]
    return round(sum(rates) / len(rates), 4)
