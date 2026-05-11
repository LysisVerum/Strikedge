"""
MLB Stats API wrapper.

All data comes from statsapi.mlb.com — free, no auth required.
We cache aggressively since the API is slow and rate-limits heavy usage.
"""
import time
import json
import unicodedata
import urllib.request
import urllib.parse
from datetime import date, timedelta
from functools import lru_cache


def _ascii(s: str) -> str:
    """Strip accents and normalize to plain ASCII lowercase."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()

BASE = "https://statsapi.mlb.com/api/v1"
_cache: dict = {}
_TTL = 3600  # 1 hour for most endpoints; schedule uses shorter TTL


def _get(path: str, params: dict = None) -> dict:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    key = url
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < _TTL:
        return entry["data"]
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read())
    _cache[key] = {"ts": time.time(), "data": data}
    return data


# ---------------------------------------------------------------------------
# Pitcher game logs
# ---------------------------------------------------------------------------

def get_pitcher_game_log(mlbam_id: int, season: int) -> list[dict]:
    """
    Returns a list of game-level pitching stats for one pitcher in one season.
    Each dict has: date, SO, IP, BF, opponent_id, opponent_name, is_home.
    """
    data = _get(f"/people/{mlbam_id}/stats", {
        "stats": "gameLog",
        "season": season,
        "group": "pitching",
    })
    stats_list = data.get("stats", [])
    splits = stats_list[0].get("splits", []) if stats_list else []
    rows = []
    for s in splits:
        st = s.get("stat", {})
        opponent = s.get("opponent", {})
        team = s.get("team", {})
        game = s.get("game", {})
        gs = int(st.get("gamesStarted", 0))
        rows.append({
            "date":          s.get("date", ""),
            "season":        season,
            "mlbam_id":      mlbam_id,
            "game_pk":       str(game.get("gamePk", "")),
            "is_start":      gs,
            "SO":            int(st.get("strikeOuts", 0)),
            "IP":            float(st.get("inningsPitched", 0)),
            "BF":            int(st.get("battersFaced", 0)),
            "H":             int(st.get("hits", 0)),
            "BB":            int(st.get("baseOnBalls", 0)),
            "HR":            int(st.get("homeRuns", 0)),
            "opponent_id":   opponent.get("id"),
            "opponent_name": opponent.get("name", ""),
            "team_id":       team.get("id"),
            "is_home":       s.get("isHome", True),
        })
    return rows


def get_pitcher_multi_season_log(mlbam_id: int, seasons: list[int]) -> list[dict]:
    rows = []
    for season in seasons:
        try:
            rows.extend(get_pitcher_game_log(mlbam_id, season))
        except Exception:
            pass
    return sorted(rows, key=lambda r: r["date"])


# ---------------------------------------------------------------------------
# Season pitching leaderboard (to get pitcher IDs)
# ---------------------------------------------------------------------------

def get_season_sp_ids(season: int, min_gs: int = 5) -> list[dict]:
    """
    Returns list of {mlbam_id, full_name, team} for all SPs with >= min_gs starts.
    """
    data = _get("/stats", {
        "stats":      "season",
        "group":      "pitching",
        "season":     season,
        "sportId":    1,
        "playerPool": "All",
        "limit":      500,
    })
    results = []
    for s in data.get("stats", [{}])[0].get("splits", []):
        stat = s.get("stat", {})
        gs = int(stat.get("gamesStarted", 0))
        if gs >= min_gs:
            p = s.get("player", {})
            results.append({
                "mlbam_id":  p.get("id"),
                "full_name": p.get("fullName", ""),
                "team":      s.get("team", {}).get("abbreviation", ""),
                "GS":        gs,
                "season":    season,
            })
    return results


# ---------------------------------------------------------------------------
# Team batting K% (opponent strength)
# ---------------------------------------------------------------------------

def get_team_k_pct(season: int) -> dict[int, float]:
    """
    Returns {team_id: k_pct} for all MLB teams in a given season.
    k_pct = strikeOuts / plateAppearances (batting side).
    """
    data = _get("/teams/stats", {
        "season":  season,
        "group":   "hitting",
        "stats":   "season",
        "sportId": 1,
    })
    result = {}
    for s in data.get("stats", [{}])[0].get("splits", []):
        stat = s.get("stat", {})
        team_id = s.get("team", {}).get("id")
        pa = int(stat.get("plateAppearances", 0))
        so = int(stat.get("strikeOuts", 0))
        if pa > 0 and team_id:
            result[team_id] = so / pa
    return result


def get_team_id_map(season: int = 2024) -> dict[str, int]:
    """Returns {abbreviation: team_id}."""
    data = _get("/teams", {"sportId": 1, "season": season})
    return {t.get("abbreviation", ""): t.get("id") for t in data.get("teams", [])}


# ---------------------------------------------------------------------------
# Today's probable starters
# ---------------------------------------------------------------------------

def get_todays_starters(game_date: str = None) -> list[dict]:
    """
    Returns list of probable starters for today's MLB schedule.
    Each dict: pitcher_name, mlbam_id, team, opponent_id, opponent_name,
               opponent_abbr, park_team, is_home, game_time.
    """
    if game_date is None:
        game_date = date.today().isoformat()

    data = _get("/schedule", {
        "sportId":   1,
        "date":      game_date,
        "gameType":  "R",
        "hydrate":   "probablePitcher,team,lineups",
    })

    starters = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            lineups = game.get("lineups", {})
            home_lineup = [p["id"] for p in lineups.get("homePlayers", []) if p.get("id")]
            away_lineup = [p["id"] for p in lineups.get("awayPlayers", []) if p.get("id")]

            for side in ("away", "home"):
                other = "home" if side == "away" else "away"
                team_data = game["teams"][side]
                opp_data  = game["teams"][other]
                pitcher   = team_data.get("probablePitcher", {})
                if not pitcher:
                    continue
                # Opponent lineup = batters facing this pitcher
                opp_lineup = home_lineup if side == "away" else away_lineup
                starters.append({
                    "pitcher_name":   pitcher.get("fullName", ""),
                    "mlbam_id":       pitcher.get("id"),
                    "team":           team_data["team"].get("abbreviation", ""),
                    "team_id":        team_data["team"].get("id"),
                    "opponent_name":  opp_data["team"].get("name", ""),
                    "opponent_abbr":  opp_data["team"].get("abbreviation", ""),
                    "opponent_id":    opp_data["team"].get("id"),
                    "park_team":      game["teams"]["home"]["team"].get("abbreviation", ""),
                    "is_home":        side == "home",
                    "game_time":      game.get("gameDate", ""),
                    "opp_lineup_ids": opp_lineup,
                })
    return starters


# ---------------------------------------------------------------------------
# Team matchup map (all games today, no probable pitcher required)
# ---------------------------------------------------------------------------

def get_team_matchups_today(game_date: str = None) -> dict[str, dict]:
    """
    Returns {team_abbr: {"opponent_id": int, "opponent_abbr": str, "is_home": bool}}
    for every team with a game today, regardless of whether probable pitchers are set.
    Used to fill opponent info for DK-augmented starters the MLB API hasn't announced yet.
    """
    if game_date is None:
        game_date = date.today().isoformat()

    data = _get("/schedule", {
        "sportId":  1,
        "date":     game_date,
        "gameType": "R",
        "hydrate":  "team",
    })

    result = {}
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            for side in ("away", "home"):
                other     = "home" if side == "away" else "away"
                team_data = game["teams"][side]
                opp_data  = game["teams"][other]
                abbr      = team_data.get("team", {}).get("abbreviation", "")
                if abbr:
                    result[abbr] = {
                        "opponent_id":   opp_data.get("team", {}).get("id"),
                        "opponent_abbr": opp_data.get("team", {}).get("abbreviation", ""),
                        "opponent_name": opp_data.get("team", {}).get("name", ""),
                        "is_home":       side == "home",
                        "game_time":     game.get("gameDate", ""),
                    }
    return result


# ---------------------------------------------------------------------------
# Today's confirmed batting lineups
# ---------------------------------------------------------------------------

def get_todays_lineup_batters(game_date: str = None) -> list[dict]:
    """
    Returns all confirmed batting lineup members for today's games.
    Each dict: mlbam_id, full_name, team_abbr, opponent_abbr, home_team_abbr, is_home.
    Returns empty list when lineups have not yet been submitted.
    Reuses the cached schedule response from get_todays_starters() when called same day.
    """
    if game_date is None:
        game_date = date.today().isoformat()

    data = _get("/schedule", {
        "sportId":  1,
        "date":     game_date,
        "gameType": "R",
        "hydrate":  "probablePitcher,team,lineups",
    })

    batters = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            lineups      = game.get("lineups", {})
            home_players = lineups.get("homePlayers", [])
            away_players = lineups.get("awayPlayers", [])
            if not home_players and not away_players:
                continue

            home_abbr = game["teams"]["home"]["team"].get("abbreviation", "")
            away_abbr = game["teams"]["away"]["team"].get("abbreviation", "")

            for player in home_players:
                pid = player.get("id")
                if pid:
                    batters.append({
                        "mlbam_id":       int(pid),
                        "full_name":      player.get("fullName", ""),
                        "team_abbr":      home_abbr,
                        "opponent_abbr":  away_abbr,
                        "home_team_abbr": home_abbr,
                        "is_home":        True,
                    })

            for player in away_players:
                pid = player.get("id")
                if pid:
                    batters.append({
                        "mlbam_id":       int(pid),
                        "full_name":      player.get("fullName", ""),
                        "team_abbr":      away_abbr,
                        "opponent_abbr":  home_abbr,
                        "home_team_abbr": home_abbr,
                        "is_home":        False,
                    })

    return batters


# ---------------------------------------------------------------------------
# Pitcher lookup by name
# ---------------------------------------------------------------------------

def search_pitcher(query: str, season: int = 2024) -> list[dict]:
    """Fuzzy name search against season leaderboard. Accent-insensitive."""
    q = _ascii(query)
    all_sps = get_season_sp_ids(season, min_gs=1)
    return [p for p in all_sps if q in _ascii(p["full_name"])][:8]
