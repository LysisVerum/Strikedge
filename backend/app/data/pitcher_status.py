"""
Pitcher availability flags.
Detects pitchers who recently returned from the IL so users can account for
expected pitch-count limits that the K-rate model can't see.
"""
import json
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

_ARTIFACTS  = Path(__file__).parent.parent.parent / "artifacts"
_CACHE_FILE = _ARTIFACTS / "pitcher_status_cache.json"
_CACHE_TTL  = 3600  # 1 hour - activations don't change within a day


def _load_cache(as_of_date: str) -> dict | None:
    if not _CACHE_FILE.exists():
        return None
    try:
        payload = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        if payload.get("date") == as_of_date and time.time() - payload.get("ts", 0) < _CACHE_TTL:
            return payload["flags"]
    except Exception:
        pass
    return None


def _save_cache(as_of_date: str, flags: dict):
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(
        json.dumps({"date": as_of_date, "ts": time.time(), "flags": flags}, indent=2),
        encoding="utf-8",
    )


def get_pitcher_flags(as_of_date: str | None = None, lookback_days: int = 28) -> dict[int, dict]:
    """
    Returns {mlbam_id: {"flag": str, "detail": str, "severity": "high"|"medium"}}
    for pitchers who recently returned from the IL and may be on a pitch count.

    Checks MLB Stats API transactions for the last `lookback_days` days.
    Results are cached for 1 hour per calendar day.
    """
    today = as_of_date or date.today().isoformat()

    cached = _load_cache(today)
    if cached is not None:
        return {int(k): v for k, v in cached.items()}

    start = (date.fromisoformat(today) - timedelta(days=lookback_days)).isoformat()
    url = (
        f"https://statsapi.mlb.com/api/v1/transactions"
        f"?sportId=1&startDate={start}&endDate={today}"
    )

    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"  [pitcher-status] transaction fetch failed: {e}")
        return {}

    flags: dict[int, dict] = {}
    today_dt = date.fromisoformat(today)

    for txn in data.get("transactions", []):
        # MLB uses typeCode "SC" (roster status change) for all IL moves
        description = (txn.get("description") or "").lower()
        player      = txn.get("person") or txn.get("player") or {}
        player_id   = player.get("id")
        txn_date    = (txn.get("date") or "")[:10]

        if not player_id or not txn_date:
            continue

        # Only interested in IL activations
        if "activated" not in description or "injured list" not in description:
            continue

        try:
            days_ago = (today_dt - date.fromisoformat(txn_date)).days
        except ValueError:
            continue

        if "60-day" in description:
            if days_ago > 28:
                continue  # Long enough ago - likely fully ramped up
            severity = "high"
            detail   = f"Returned from 60-day IL {days_ago}d ago - likely on a pitch count"
        elif "15-day" in description:
            if days_ago > 14:
                continue  # Beyond the reasonable pitch-count window
            severity = "medium"
            detail   = f"Returned from 15-day IL {days_ago}d ago - may have a pitch count"
        else:
            # 10-day or 7-day IL - only flag first start or two back
            if days_ago > 7:
                continue
            severity = "low"
            detail   = f"Recently returned from IL ({days_ago}d ago)"

        # Keep the most recent activation per player
        existing = flags.get(player_id)
        if not existing or txn_date > existing.get("txn_date", ""):
            flags[player_id] = {
                "flag":     "IL_RETURN",
                "detail":   detail,
                "severity": severity,
                "txn_date": txn_date,
            }

    print(f"  [pitcher-status] {len(flags)} recently-activated pitchers flagged.")
    _save_cache(today, {str(k): v for k, v in flags.items()})
    return flags
