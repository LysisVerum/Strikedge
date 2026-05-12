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
_last_real_fetch_ts: float = 0.0   # epoch seconds of last actual API call
_FORCE_REFRESH_MIN_INTERVAL = 1800  # 30 minutes between force-refreshes

# Preferred sportsbook order — first available book wins per pitcher
PREFERRED_BOOKS = ["DraftKings", "FanDuel", "BetMGM", "Caesars", "PointsBet"]


def get_credits_remaining() -> int | None:
    """Return the last known remaining credit count from response headers."""
    return _credits_remaining


def invalidate_player_prop_cache():
    """Clear cached player-prop and events-list responses so next call hits the API."""
    keys = [k for k in list(_cache.keys()) if "/events" in k or "batter_hits" in k]
    for k in keys:
        _cache.pop(k, None)


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
    """Return cached lines if they exist, are less than _DISK_TTL seconds old,
    and use the current format (has over_book/under_book for line shopping)."""
    path = _disk_cache_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - payload.get("ts", 0)
        if age < _DISK_TTL:
            lines = payload["lines"]
            sample = next(iter(lines.values()), {}) if lines else {}
            if lines and "over_book" not in sample:
                print("  [odds-api] disk cache outdated format — forcing refresh")
                return None
            print(f"  [odds-api] disk cache hit ({int(age)}s old) — skipping API calls")
            return lines
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
    Collect all books' odds per player, then return the best over AND best under
    independently (line shopping).

    Result shape per player:
        {line, over_odds, over_book, under_odds, under_book, book, books_checked}

    "Best" is determined at the same consensus line (primary book's line) to keep
    the comparison apples-to-apples. Cross-line shopping requires model evaluation
    and is deferred to a future iteration.
    """
    # Pass 1 — gather every book's complete offer per player
    all_offers: dict[str, list[dict]] = {}

    for event in events:
        bookmakers = event.get("bookmakers", [])

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
                if market.get("key") != MARKET:
                    continue

                this_book: dict[str, dict] = {}
                for outcome in market.get("outcomes", []):
                    name  = (outcome.get("description") or outcome.get("name") or "").strip()
                    point = outcome.get("point")
                    price = outcome.get("price")
                    label = (outcome.get("name") or "").lower()
                    if not name or point is None or price is None:
                        continue
                    key = name.lower()
                    if key not in this_book:
                        this_book[key] = {"book": book, "line": float(point),
                                          "over_odds": None, "under_odds": None}
                    if "over" in label:
                        this_book[key]["over_odds"] = int(price)
                        this_book[key]["line"]      = float(point)
                    elif "under" in label:
                        this_book[key]["under_odds"] = int(price)

                for key, offer in this_book.items():
                    if offer["over_odds"] is None:
                        continue
                    if offer["under_odds"] is None:
                        offer["under_odds"] = -115
                    all_offers.setdefault(key, []).append(offer)

    # Pass 2 — pick best over and best under per player at the consensus line
    result: dict[str, dict] = {}
    for key, offers in all_offers.items():
        primary    = offers[0]                                          # highest-priority book
        same_line  = [o for o in offers if o["line"] == primary["line"]]
        best_over  = max(same_line, key=lambda o: o["over_odds"])
        best_under = max(same_line, key=lambda o: o["under_odds"])
        result[key] = {
            "line":          primary["line"],
            "over_odds":     best_over["over_odds"],
            "over_book":     best_over["book"],
            "under_odds":    best_under["under_odds"],
            "under_book":    best_under["book"],
            "book":          primary["book"],
            "books_checked": len(offers),
        }
    return result


# ---------------------------------------------------------------------------
# Live lines
# ---------------------------------------------------------------------------

def get_sp_strikeout_lines(force_refresh: bool = False) -> dict[str, dict]:
    """
    Fetch today's pitcher strikeout O/U lines.
    Player props require the per-event endpoint (bulk endpoint only supports game markets).

    Uses a disk cache (2-hour TTL) to avoid burning credits on every refresh.
    Pass force_refresh=True to bypass the cache, subject to a 30-minute throttle.

    Returns:
        {"gerrit cole": {"line": 7.5, "over_odds": -130, "under_odds": 110, "book": "DraftKings"}}
    """
    global _last_real_fetch_ts
    if force_refresh:
        age = time.time() - _last_real_fetch_ts
        if age < _FORCE_REFRESH_MIN_INTERVAL:
            print(f"  [odds-api] force_refresh throttled — last fetch was {int(age / 60)}m ago (min {_FORCE_REFRESH_MIN_INTERVAL // 60}m)")
            force_refresh = False

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
    _last_real_fetch_ts = time.time()
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
