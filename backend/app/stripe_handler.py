import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_PRICE_ID_PATH = Path(__file__).parent.parent / "artifacts" / "stripe_price_id.txt"

PREMIUM_PRICE_CAD = 2500   # $25.00 CAD in cents


def _stripe():
    import stripe as _s
    _s.api_key = os.environ["STRIPE_SECRET_KEY"]
    return _s


def _log(msg: str):
    print(f"[stripe] {msg}", flush=True)


def _attr(obj, key, default=None):
    """Safe attribute access for Stripe SDK objects (v5+ removed .get())."""
    try:
        return getattr(obj, key, default)
    except Exception:
        return default


def _period_end_to_iso(period_end) -> str:
    """Convert Stripe current_period_end (int timestamp or datetime) to ISO string."""
    if period_end is None:
        return (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    if isinstance(period_end, datetime):
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
        return period_end.isoformat()
    return datetime.fromtimestamp(int(period_end), tz=timezone.utc).isoformat()


def get_or_create_price() -> str:
    """Return the recurring price ID.

    Resolution order:
      1. STRIPE_PRICE_ID env var (set this in Railway once the product exists)
      2. artifacts/stripe_price_id.txt  (local dev fallback)
      3. Create a new product + price in Stripe (first-time setup only)
    """
    env_price = os.environ.get("STRIPE_PRICE_ID", "").strip()
    if env_price:
        return env_price

    if _PRICE_ID_PATH.exists():
        price_id = _PRICE_ID_PATH.read_text().strip()
        if price_id:
            return price_id

    s = _stripe()
    product = s.Product.create(
        name        = "StrikeEdge Premium",
        description = "Full access to all daily MLB strikeout and hit prop picks",
    )
    price = s.Price.create(
        product     = product.id,
        currency    = "cad",
        unit_amount = PREMIUM_PRICE_CAD,
        recurring   = {"interval": "month"},
    )
    _PRICE_ID_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PRICE_ID_PATH.write_text(price.id, encoding="utf-8")
    _log(f"Created product {product.id}, price {price.id} — set STRIPE_PRICE_ID={price.id} in Railway")
    return price.id


def create_checkout_session(email: str, success_url: str, cancel_url: str) -> str:
    """Create a Stripe Checkout session and return the hosted URL."""
    s        = _stripe()
    price_id = get_or_create_price()

    session = s.checkout.Session.create(
        payment_method_types      = ["card"],
        mode                      = "subscription",
        customer_email            = email,
        line_items                = [{"price": price_id, "quantity": 1}],
        success_url               = success_url,
        cancel_url                = cancel_url,
        metadata                  = {"email": email},
        payment_method_collection = "if_required",
    )
    return session.url


def _email_from_session(sess, s) -> str:
    """Extract the subscriber email from a checkout.session object."""
    email = (_attr(sess, "customer_email") or "").strip()
    if email:
        return email

    metadata = _attr(sess, "metadata")
    if metadata:
        # metadata may be a StripeObject or plain dict
        if isinstance(metadata, dict):
            email = (metadata.get("email") or "").strip()
        else:
            email = (_attr(metadata, "email") or "").strip()
    if email:
        return email

    customer_id = _attr(sess, "customer")
    if customer_id:
        try:
            customer = s.Customer.retrieve(customer_id)
            email = (_attr(customer, "email") or "").strip()
        except Exception as exc:
            _log(f"Could not retrieve customer {customer_id}: {exc}")

    return email


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Process a Stripe webhook event and update user subscription state."""
    from backend.app import users as user_store

    _log(f"Webhook hit — sig header present: {bool(sig_header)}")

    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not webhook_secret:
        _log("WARNING: STRIPE_WEBHOOK_SECRET not set")
        return {"error": "STRIPE_WEBHOOK_SECRET not configured"}

    s = _stripe()

    try:
        event = s.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as exc:
        _log(f"Webhook signature error: {exc}")
        return {"error": str(exc)}

    etype = event["type"]
    _log(f"Webhook received: {etype}")

    try:
        if etype == "checkout.session.completed":
            sess   = event["data"]["object"]
            email  = _email_from_session(sess, s)
            sub_id = _attr(sess, "subscription")

            _log(f"checkout.session.completed — email={email!r} sub_id={sub_id!r}")

            if not email:
                _log(f"Could not determine email — session {_attr(sess, 'id')}")
                return {"status": "skipped", "reason": "no email"}

            if not sub_id:
                _log(f"No subscription ID — session {_attr(sess, 'id')}")
                return {"status": "skipped", "reason": "no subscription"}

            sub        = s.Subscription.retrieve(sub_id)
            expires_at = _period_end_to_iso(_attr(sub, "current_period_end"))
            user_store.set_premium(
                email,
                stripe_customer_id     = _attr(sess, "customer", ""),
                stripe_subscription_id = sub_id,
                expires_at             = expires_at,
            )
            _log(f"Set {email} to premium, expires {expires_at}")

        elif etype in ("customer.subscription.deleted", "customer.subscription.paused"):
            sub    = event["data"]["object"]
            sub_id = _attr(sub, "id")
            user   = user_store.find_by_subscription(sub_id)
            if user:
                user_store.set_free(user["email"])
                _log(f"Downgraded {user['email']} to free (sub {sub_id} {etype})")
            else:
                _log(f"{etype}: no user found for sub {sub_id}")

        elif etype in ("invoice.payment_succeeded", "invoice.paid"):
            invoice = event["data"]["object"]
            sub_id  = _attr(invoice, "subscription")
            if sub_id:
                sub        = s.Subscription.retrieve(sub_id)
                expires_at = _period_end_to_iso(_attr(sub, "current_period_end"))
                user_store.renew_premium(sub_id, expires_at)
                _log(f"Renewed premium for sub {sub_id}, expires {expires_at}")

        elif etype == "customer.subscription.updated":
            sub    = event["data"]["object"]
            sub_id = _attr(sub, "id")
            if _attr(sub, "status") == "active":
                user = user_store.find_by_subscription(sub_id)
                if user:
                    expires_at = _period_end_to_iso(_attr(sub, "current_period_end"))
                    user_store.renew_premium(sub_id, expires_at)
                    _log(f"Subscription updated for {user['email']}, expires {expires_at}")

        else:
            _log(f"Unhandled event type: {etype}")

    except Exception as exc:
        _log(f"Error processing {etype}: {exc}")
        return {"error": str(exc)}

    return {"status": "handled", "type": etype}
