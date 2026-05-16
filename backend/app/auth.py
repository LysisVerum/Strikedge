import os
import secrets
from datetime import datetime, timezone, timedelta
from backend.app.db import get_db

_TOKEN_TTL_MINUTES = 15
_SESSION_TTL_DAYS  = 30


# ---------------------------------------------------------------------------
# Magic link
# ---------------------------------------------------------------------------

def generate_magic_link(email: str) -> bool:
    """Generate a one-time login token, email it via Resend, return True on success."""
    import resend

    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not set in environment")

    from_email = os.environ.get("RESEND_FROM_EMAIL", "").strip()
    if not from_email:
        raise RuntimeError(
            "RESEND_FROM_EMAIL is not set. "
            "Set it to a verified-domain address like noreply@yourdomain.com — "
            "onboarding@resend.dev only works for your own Resend account email."
        )

    key        = email.lower()
    token      = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_TTL_MINUTES)).isoformat()

    db = get_db()
    db.execute("DELETE FROM auth_tokens WHERE email = ?", (key,))
    db.execute(
        "INSERT INTO auth_tokens (token, email, expires_at) VALUES (?, ?, ?)",
        (token, key, expires_at),
    )
    db.commit()

    app_url = os.environ.get("APP_URL", "http://localhost:5000")
    link    = f"{app_url}/verify?token={token}"

    resend.api_key = api_key
    try:
        result = resend.Emails.send({
            "from":    from_email,
            "to":      [email],
            "subject": "Your StrikeEdge sign-in link",
            "html":    f"""
<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:2rem;background:#0d1117;color:#e6edf3;border-radius:12px">
  <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:1.5rem">
    <div style="width:28px;height:28px;border-radius:6px;background:linear-gradient(135deg,#1d9bf0,#0066cc);display:flex;align-items:center;justify-content:center">
      <span style="color:#fff;font-size:14px;font-weight:700">S</span>
    </div>
    <span style="font-weight:700;font-size:1.1rem">Strike<span style="color:#1d9bf0">Edge</span></span>
  </div>
  <h2 style="font-size:1.3rem;margin-bottom:0.75rem">Sign in to StrikeEdge</h2>
  <p style="color:#8b949e;line-height:1.6;margin-bottom:1.5rem">
    Click the button below to sign in. This link expires in {_TOKEN_TTL_MINUTES} minutes and can only be used once.
  </p>
  <a href="{link}"
     style="display:inline-block;padding:0.75rem 1.75rem;background:linear-gradient(135deg,#1d9bf0,#0066cc);color:#fff;border-radius:8px;text-decoration:none;font-weight:600;font-size:0.95rem">
    Sign In to StrikeEdge
  </a>
  <p style="color:#484f58;font-size:0.8rem;margin-top:2rem">
    If you didn't request this, you can safely ignore this email.
  </p>
</div>
""",
        })
    except Exception as exc:
        print(f"[auth] Resend send failed for {email}: {exc}")
        raise
    print(f"[auth] Magic link sent to {email} (from={from_email})")
    return True


def verify_magic_link(token: str) -> str | None:
    """Validate token, delete it, return the email on success or None."""
    db  = get_db()
    row = db.execute(
        "SELECT email, expires_at FROM auth_tokens WHERE token = ?", (token,)
    ).fetchone()

    if not row:
        return None

    db.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
    db.commit()

    try:
        if datetime.now(timezone.utc) > datetime.fromisoformat(row["expires_at"]):
            return None
    except ValueError:
        return None

    return row["email"]


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def create_session(email: str) -> str:
    db            = get_db()
    session_token = secrets.token_urlsafe(48)
    expires_at    = (datetime.now(timezone.utc) + timedelta(days=_SESSION_TTL_DAYS)).isoformat()
    db.execute(
        "INSERT INTO sessions (token, email, expires_at) VALUES (?, ?, ?)",
        (session_token, email.lower(), expires_at),
    )
    db.commit()
    return session_token


def get_session_email(session_token: str) -> str | None:
    db  = get_db()
    row = db.execute(
        "SELECT email, expires_at FROM sessions WHERE token = ?", (session_token,)
    ).fetchone()

    if not row:
        return None

    try:
        if datetime.now(timezone.utc) > datetime.fromisoformat(row["expires_at"]):
            db.execute("DELETE FROM sessions WHERE token = ?", (session_token,))
            db.commit()
            return None
    except ValueError:
        return None

    return row["email"]


def delete_session(session_token: str):
    db = get_db()
    db.execute("DELETE FROM sessions WHERE token = ?", (session_token,))
    db.commit()
