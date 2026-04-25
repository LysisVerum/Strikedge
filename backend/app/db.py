import json
import sqlite3
import threading
from pathlib import Path

DB_PATH       = Path(__file__).parent.parent / "artifacts" / "strikedge.db"
_local        = threading.local()

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    """Return a per-thread SQLite connection, creating it if needed."""
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.commit()
    return _local.conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    email                   TEXT PRIMARY KEY,
    tier                    TEXT NOT NULL DEFAULT 'free',
    stripe_customer_id      TEXT,
    stripe_subscription_id  TEXT,
    premium_expires_at      TEXT,
    weekly_tokens           INTEGER NOT NULL DEFAULT 1,
    tokens_reset_at         TEXT,
    created_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token       TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS unlocked_picks (
    email        TEXT NOT NULL,
    date         TEXT NOT NULL,
    pitcher_name TEXT NOT NULL,
    PRIMARY KEY (email, date, pitcher_name)
);

CREATE INDEX IF NOT EXISTS idx_sessions_email     ON sessions(email);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_email  ON auth_tokens(email);
CREATE INDEX IF NOT EXISTS idx_unlocked_email_date ON unlocked_picks(email, date);
"""


def init_db():
    """Create tables, then migrate any existing JSON files."""
    db = get_db()
    db.executescript(_SCHEMA)
    db.commit()
    _migrate_json()


# ---------------------------------------------------------------------------
# JSON -> SQLite migration (runs once, then renames files to .bak)
# ---------------------------------------------------------------------------

_ARTIFACTS = Path(__file__).parent.parent / "artifacts"


def _migrate_json():
    _migrate_users()
    _migrate_sessions()
    _migrate_auth_tokens()


def _migrate_users():
    path = _ARTIFACTS / "users.json"
    if not path.exists():
        return

    db   = get_db()
    data = json.loads(path.read_text(encoding="utf-8"))

    for email, u in data.items():
        existing = db.execute("SELECT email FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            continue

        db.execute("""
            INSERT OR IGNORE INTO users
                (email, tier, stripe_customer_id, stripe_subscription_id,
                 premium_expires_at, weekly_tokens, tokens_reset_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            email,
            u.get("tier", "free"),
            u.get("stripe_customer_id"),
            u.get("stripe_subscription_id"),
            u.get("premium_expires_at"),
            u.get("weekly_tokens", 1),
            u.get("tokens_reset_at"),
            u.get("created_at", "2026-01-01T00:00:00+00:00"),
        ))

        # Migrate unlocked picks embedded in the user record
        for date_str, pitchers in u.get("unlocked_picks", {}).items():
            for pitcher in pitchers:
                db.execute("""
                    INSERT OR IGNORE INTO unlocked_picks (email, date, pitcher_name)
                    VALUES (?, ?, ?)
                """, (email, date_str, pitcher))

    db.commit()
    path.rename(path.with_suffix(".json.bak"))
    print("[db] Migrated users.json -> SQLite")


def _migrate_sessions():
    path = _ARTIFACTS / "sessions.json"
    if not path.exists():
        return

    db   = get_db()
    data = json.loads(path.read_text(encoding="utf-8"))

    for token, s in data.items():
        db.execute("""
            INSERT OR IGNORE INTO sessions (token, email, expires_at)
            VALUES (?, ?, ?)
        """, (token, s.get("email", ""), s.get("expires_at", "")))

    db.commit()
    path.rename(path.with_suffix(".json.bak"))
    print("[db] Migrated sessions.json -> SQLite")


def _migrate_auth_tokens():
    path = _ARTIFACTS / "auth_tokens.json"
    if not path.exists():
        return

    db   = get_db()
    data = json.loads(path.read_text(encoding="utf-8"))

    for token, t in data.items():
        db.execute("""
            INSERT OR IGNORE INTO auth_tokens (token, email, expires_at)
            VALUES (?, ?, ?)
        """, (token, t.get("email", ""), t.get("expires_at", "")))

    db.commit()
    path.rename(path.with_suffix(".json.bak"))
    print("[db] Migrated auth_tokens.json -> SQLite")


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

def purge_expired():
    """Delete expired sessions and auth tokens. Call periodically."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    db  = get_db()
    db.execute("DELETE FROM sessions    WHERE expires_at < ?", (now,))
    db.execute("DELETE FROM auth_tokens WHERE expires_at < ?", (now,))
    db.commit()
