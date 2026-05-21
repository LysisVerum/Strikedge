import os
from datetime import datetime, timezone
from pathlib import Path

_PRICE_ID_PATH = Path(__file__).parent.parent / "artifacts" / "stripe_price_id.txt"

PREMIUM_PRICE_CAD = 2500   # $25.00 CAD in cents


def _stripe():
    import stripe as _s
    _s.api_key = os.environ["STRIPE_SECRET_KEY"]
    return _s


def _attr(obj, key, default=None):
    """Safe attribute access for Stripe SDK objects (v5+ removed .get())."""
    try:
        return getattr(obj, key, default)
    except Exception:
        return default


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
    print(f"[stripe] Created product {product.id}, price {price.id} — set STRIPE_PRICE_ID={price.id} in Railway")
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
        email = (_attr(metadata, "email") or "").strip()
    if email:
        return email

    customer_id = _attr(sess, "customer")
    if customer_id:
        try:
            customer = s.Customer.retrieve(customer_id)
            email = (_attr(customer, "email") or "").strip()
        except Exception as exc:
            print(f"[stripe] Could not retrieve customer {customer_id}: {exc}")

    return email


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Process a Stripe webhook event and update user subscription state."""
    from backend.app import users as user_store

    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not webhook_secret:
        print("[stripe] WARNING: STRIPE_WEBHOOK_SECRET not set — webhook signature not verified")
        return {"error": "STRIPE_WEBHOOK_SECRET not configured"}

    s = _stripe()

    try:
        event = s.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as exc:
        print(f"[stripe] Webhook signature error: {exc}")
        return {"error": str(exc)}

    etype = event["type"]
    print(f"[stripe] Webhook received: {etype}")

    if etype == "checkout.session.completed":
        sess   = event["data"]["object"]
        email  = _email_from_session(sess, s)
        sub_id = _attr(sess, "subscription")

        if not email:
            print(f"[stripe] checkout.session.completed: could not determine email — session {_attr(sess, 'id')}")
            return {"status": "skipped", "reason": "no email"}

        if not sub_id:
            print(f"[stripe] checkout.session.completed: no subscription ID — session {_attr(sess, 'id')}")
            return {"status": "skipped", "reason": "no subscription"}

        try:
            sub        = s.Subscription.retrieve(sub_id)
            expires_at = datetime.fromtimestamp(
                _attr(sub, "current_period_end"), tz=timezone.utc
            ).isoformat()
            user_store.set_premium(
                email,
                stripe_customer_id     = _attr(sess, "customer", ""),
                stripe_subscription_id = sub_id,
                expires_at             = expires_at,
            )
            print(f"[stripe] Set {email} to premium, expires {expires_at}")
        except Exception as exc:
            print(f"[stripe] Failed to set premium for {email}: {exc}")
            return {"error": str(exc)}

    elif etype in ("customer.subscription.deleted", "customer.subscription.paused"):
        sub    = event["data"]["object"]
        sub_id = _attr(sub, "id")
        user   = user_store.find_by_subscription(sub_id)
        if user:
            user_store.set_free(user["email"])
            print(f"[stripe] Downgraded {user['email']} to free (sub {sub_id} {etype})")
        else:
            print(f"[stripe] {etype}: no user found for sub {sub_id}")

    elif etype in ("invoice.payment_succeeded", "invoice.paid"):
        invoice = event["data"]["object"]
        sub_id  = _attr(invoice, "subscription")
        if sub_id:
            try:
                sub        = s.Subscription.retrieve(sub_id)
                expires_at = datetime.fromtimestamp(
                    _attr(sub, "current_period_end"), tz=timezone.utc
                ).isoformat()
                user_store.renew_premium(sub_id, expires_at)
                print(f"[stripe] Renewed premium for sub {sub_id}, expires {expires_at}")
            except Exception as exc:
                print(f"[stripe] Failed to renew premium for sub {sub_id}: {exc}")

    elif etype == "customer.subscription.updated":
        sub    = event["data"]["object"]
        sub_id = _attr(sub, "id")
        if _attr(sub, "status") == "active":
            user = user_store.find_by_subscription(sub_id)
            if user:
                expires_at = datetime.fromtimestamp(
                    _attr(sub, "current_period_end"), tz=timezone.utc
                ).isoformat()
                user_store.renew_premium(sub_id, expires_at)
                print(f"[stripe] Subscription updated for {user['email']}, expires {expires_at}")

    return {"status": "handled", "type": etype}
