from datetime import datetime, timezone, timedelta
from backend.app.db import get_db


def _next_monday_utc() -> str:
    now        = datetime.now(timezone.utc)
    days_ahead = (7 - now.weekday()) % 7 or 7
    nxt        = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.isoformat()


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def get_user(email: str) -> dict | None:
    row = get_db().execute(
        "SELECT * FROM users WHERE email = ?", (email.lower(),)
    ).fetchone()
    return dict(row) if row else None


def upsert_user(email: str, **kwargs) -> dict:
    db  = get_db()
    key = email.lower()

    exists = db.execute("SELECT 1 FROM users WHERE email = ?", (key,)).fetchone()
    if not exists:
        db.execute("""
            INSERT INTO users (email, tier, weekly_tokens, created_at)
            VALUES (?, 'free', 1, ?)
        """, (key, datetime.now(timezone.utc).isoformat()))

    if kwargs:
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        db.execute(f"UPDATE users SET {cols} WHERE email = ?",
                   (*kwargs.values(), key))

    db.commit()
    return get_user(key)


def set_premium(email: str, stripe_customer_id: str, stripe_subscription_id: str, expires_at: str) -> dict:
    return upsert_user(
        email,
        tier                   = "premium",
        stripe_customer_id     = stripe_customer_id,
        stripe_subscription_id = stripe_subscription_id,
        premium_expires_at     = expires_at,
    )


def set_free(email: str) -> dict:
    return upsert_user(email, tier="free")


def renew_premium(subscription_id: str, expires_at: str):
    db = get_db()
    db.execute("""
        UPDATE users SET premium_expires_at = ?
        WHERE stripe_subscription_id = ?
    """, (expires_at, subscription_id))
    db.commit()


def get_tier(email: str) -> str:
    row = get_db().execute(
        "SELECT tier, premium_expires_at FROM users WHERE email = ?",
        (email.lower(),)
    ).fetchone()
    if not row or row["tier"] != "premium":
        return "free"
    exp = row["premium_expires_at"]
    if exp:
        try:
            if datetime.fromisoformat(exp) < datetime.now(timezone.utc):
                return "free"
        except ValueError:
            return "free"
    return "premium"


def find_by_subscription(subscription_id: str) -> dict | None:
    row = get_db().execute(
        "SELECT * FROM users WHERE stripe_subscription_id = ?",
        (subscription_id,)
    ).fetchone()
    return dict(row) if row else None


def all_users() -> list[dict]:
    return [dict(r) for r in get_db().execute("SELECT * FROM users").fetchall()]


# ---------------------------------------------------------------------------
# Weekly token system
# ---------------------------------------------------------------------------

def get_token_info(email: str) -> dict:
    """Return token count, auto-resetting if the week has rolled over."""
    db  = get_db()
    key = email.lower()
    row = db.execute(
        "SELECT weekly_tokens, tokens_reset_at FROM users WHERE email = ?", (key,)
    ).fetchone()

    if not row:
        return {"tokens_remaining": 0, "tokens_reset_at": None}

    now       = datetime.now(timezone.utc)
    tokens    = row["weekly_tokens"]
    reset_str = row["tokens_reset_at"]

    if reset_str:
        try:
            if now >= datetime.fromisoformat(reset_str):
                reset_str = _next_monday_utc()
                tokens    = 1
                db.execute("""
                    UPDATE users SET weekly_tokens = 1, tokens_reset_at = ? WHERE email = ?
                """, (reset_str, key))
                db.commit()
        except ValueError:
            pass
    else:
        reset_str = _next_monday_utc()
        db.execute("""
            UPDATE users SET weekly_tokens = 1, tokens_reset_at = ? WHERE email = ?
        """, (reset_str, key))
        db.commit()
        tokens = 1

    return {"tokens_remaining": tokens, "tokens_reset_at": reset_str}


def use_token(email: str, pitcher_name: str, date_str: str) -> bool:
    """Spend one token to unlock a pick. Returns False if no tokens left."""
    db  = get_db()
    key = email.lower()

    row = db.execute(
        "SELECT weekly_tokens, tokens_reset_at FROM users WHERE email = ?", (key,)
    ).fetchone()
    if not row:
        return False

    tokens    = row["weekly_tokens"]
    reset_str = row["tokens_reset_at"]
    now       = datetime.now(timezone.utc)

    if reset_str:
        try:
            if now >= datetime.fromisoformat(reset_str):
                tokens = 1
                db.execute("""
                    UPDATE users SET weekly_tokens = 1, tokens_reset_at = ? WHERE email = ?
                """, (_next_monday_utc(), key))
        except ValueError:
            pass

    if tokens <= 0:
        db.commit()
        return False

    db.execute("UPDATE users SET weekly_tokens = weekly_tokens - 1 WHERE email = ?", (key,))
    db.execute("""
        INSERT OR IGNORE INTO unlocked_picks (email, date, pitcher_name)
        VALUES (?, ?, ?)
    """, (key, date_str, pitcher_name))
    db.commit()
    return True


def get_unlocked_today(email: str, date_str: str) -> list[str]:
    rows = get_db().execute(
        "SELECT pitcher_name FROM unlocked_picks WHERE email = ? AND date = ?",
        (email.lower(), date_str)
    ).fetchall()
    return [r["pitcher_name"] for r in rows]
