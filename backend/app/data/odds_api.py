"""
The Odds API client for MLB pitcher strikeout props.

Live lines:      get_sp_strikeout_lines()  -> {pitcher_name_lower: {...}}
Historical:      get_historical_lines(date_str) -> same shape, for a past date

Requires ODDS_API_KEY in backend/.env
"""
import json
import os
import time
import urllib.request
import urllib.parse
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

BASE_URL = "https://api.the-odds-api.com/v4"
SPORT    = "baseball_mlb"
MARKET   = "pitcher_strikeouts"
REGIONS  = "us"
FMT      = "american"

_cache: dict = {}
_MEM_TTL = 7200  # 2 hours in-memory

_ARTIFACTS = Path(__file__).parent.parent.parent / "artifacts"
_DISK_TTL  = 7200  # 2 hours before disk cache is considered stale

_credits_remaining: int | None = None


def get_credits_remaining() -> int | None:
    """Return the last known remaining credit count from response headers."""
    return _credits_remaining


def _api_key() -> str:
    key = os.getenv("ODDS_API_KEY", "")
    if not key or key == "your_key_here":
        raise RuntimeError("ODDS_API_KEY not set in backend/.env")
    return key


def _get(path: str, params: dict = None) -> dict | list:
    global _credits_remaining
    params = params or {}
    params["apiKey"] = _api_key()
    url = f"{BASE_URL}{path}?" + urllib.parse.urlencode(params)

    entry = _cache.get(url)
    if entry and time.time() - entry["ts"] < _MEM_TTL:
        return entry["data"]

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            remaining = r.headers.get("x-requests-remaining")
            used      = r.headers.get("x-requests-used")
            if remaining is not None:
                _credits_remaining = int(remaining)
                print(f"  [odds-api] credits used={used} remaining={remaining}")
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise urllib.error.HTTPError(e.url, e.code, f"{e.reason} — {body}", e.headers, None)
    _cache[url] = {"ts": time.time(), "data": data}
    return data


# ---------------------------------------------------------------------------
# Disk cache for today's lines — survives server restarts
# ---------------------------------------------------------------------------

def _disk_cache_path() -> Path:
    return _ARTIFACTS / f"lines_cache_{date.today().isoformat()}.json"


def _load_disk_cache() -> dict | None:
    """Return cached lines if they exist and are less than _DISK_TTL seconds old."""
    path = _disk_cache_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - payload.get("ts", 0)
        if age < _DISK_TTL:
            print(f"  [odds-api] disk cache hit ({int(age)}s old) — skipping API calls")
            return payload["lines"]
    except Exception:
        pass
    return None


def _save_disk_cache(lines: dict):
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = _disk_cache_path()
    path.write_text(
        json.dumps({"ts": time.time(), "lines": lines}, indent=2),
        encoding="utf-8",
    )
    # Remove stale cache files from previous dates
    for old in _ARTIFACTS.glob("lines_cache_*.json"):
        if old != path:
            try:
                old.unlink()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_events(events: list) -> dict[str, dict]:
    """
    Parse event odds objects into {pitcher_name_lower: {line, over_odds, under_odds, book}}.
    """
    result: dict[str, dict] = {}
    for event in events:
        for bookmaker in event.get("bookmakers", []):
            book = bookmaker.get("title", "")
            for market in bookmaker.get("markets", []):
                if market.get("key") != MARKET:
                    continue
                outcomes = market.get("outcomes", [])
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
                # second pass: fill under_odds
                for outcome in outcomes:
                    name  = (outcome.get("description") or outcome.get("name") or "").strip()
                    price = outcome.get("price")
                    label = (outcome.get("name") or "").lower()
                    key   = name.lower()
                    if key in result and "under" in label and price is not None:
                        result[key]["under_odds"] = int(price)
    return result


# ---------------------------------------------------------------------------
# Live lines
# ---------------------------------------------------------------------------

def get_sp_strikeout_lines(force_refresh: bool = False) -> dict[str, dict]:
    """
    Fetch today's pitcher strikeout O/U lines.
    Player props require the per-event endpoint (bulk endpoint only supports game markets).

    Uses a disk cache (2-hour TTL) to avoid burning credits on every refresh.
    Pass force_refresh=True to bypass the cache.

    Returns:
        {"gerrit cole": {"line": 7.5, "over_odds": -130, "under_odds": 110, "book": "DraftKings"}}
    """
    if not force_refresh:
        cached = _load_disk_cache()
        if cached is not None:
            return cached

    events = _get(f"/sports/{SPORT}/events", {"regions": REGIONS})
    if not isinstance(events, list):
        return {}

    result: dict[str, dict] = {}
    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue
        try:
            odds = _get(f"/sports/{SPORT}/events/{event_id}/odds", {
                "regions":    REGIONS,
                "markets":    MARKET,
                "oddsFormat": FMT,
            })
            result.update(_parse_events([odds]))
        except Exception as e:
            print(f"  [odds-api] event {event_id}: {e}")

    print(f"  [odds-api] {len(result)} pitcher K lines fetched from API.")
    _save_disk_cache(result)
    return result


# ---------------------------------------------------------------------------
# Historical lines (for backtesting)
# ---------------------------------------------------------------------------

def get_historical_lines(date_str: str) -> dict[str, dict]:
    """
    Fetch historical pitcher strikeout lines for a given date.
    Player props require the per-event endpoint.

    Returns same shape as get_sp_strikeout_lines().
    """
    ts = f"{date_str}T12:00:00Z"

    data = _get(f"/historical/sports/{SPORT}/events", {
        "date":       ts,
        "regions":    REGIONS,
        "oddsFormat": FMT,
    })
    events = data.get("data", []) if isinstance(data, dict) else data
    if not isinstance(events, list):
        return {}

    result: dict[str, dict] = {}
    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue
        try:
            odds = _get(f"/historical/sports/{SPORT}/events/{event_id}/odds", {
                "date":       ts,
                "regions":    REGIONS,
                "markets":    MARKET,
                "oddsFormat": FMT,
            })
            if isinstance(odds, dict):
                odds = odds.get("data", odds)
            result.update(_parse_events([odds]))
        except Exception as e:
            print(f"  [odds-api] {event_id} on {date_str}: {e}")

    return result


# ---------------------------------------------------------------------------
# Name matching
# ---------------------------------------------------------------------------

def match_line_to_starter(pitcher_name: str, lines: dict[str, dict]) -> dict | None:
    """Fuzzy-match a starter's full name against the lines dict (last-name fallback)."""
    name_lower = pitcher_name.lower().strip()
    if name_lower in lines:
        return lines[name_lower]
    last = name_lower.split()[-1] if name_lower else ""
    for key, val in lines.items():
        if last and key.split()[-1] == last:
            return val
    for key, val in lines.items():
        if last and last in key:
            return val
    return None
