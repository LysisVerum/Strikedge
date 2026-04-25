import os
from datetime import datetime, timezone
from pathlib import Path

_PRICE_ID_PATH = Path(__file__).parent.parent / "artifacts" / "stripe_price_id.txt"

PREMIUM_PRICE_CAD = 2500   # $25.00 CAD in cents


def _stripe():
    import stripe as _s
    _s.api_key = os.environ["STRIPE_SECRET_KEY"]
    return _s


def get_or_create_price() -> str:
    """Return the recurring price ID, creating product + price if needed."""
    if _PRICE_ID_PATH.exists():
        price_id = _PRICE_ID_PATH.read_text().strip()
        if price_id:
            return price_id

    s = _stripe()

    product = s.Product.create(
        name        = "StrikeEdge Premium",
        description = "Full access to all daily MLB strikeout prop picks",
    )
    price = s.Price.create(
        product   = product.id,
        currency  = "cad",
        unit_amount = PREMIUM_PRICE_CAD,
        recurring = {"interval": "month"},
    )
    _PRICE_ID_PATH.write_text(price.id, encoding="utf-8")
    return price.id


def create_checkout_session(email: str, success_url: str, cancel_url: str) -> str:
    """Create a Stripe Checkout session and return the hosted URL."""
    s        = _stripe()
    price_id = get_or_create_price()

    session = s.checkout.Session.create(
        payment_method_types = ["card"],
        mode                 = "subscription",
        customer_email       = email,
        line_items           = [{"price": price_id, "quantity": 1}],
        success_url          = success_url,
        cancel_url           = cancel_url,
        metadata             = {"email": email},
    )
    return session.url


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Process a Stripe webhook event and update user subscription state."""
    from backend.app import users as user_store

    s              = _stripe()
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    try:
        event = s.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as exc:
        return {"error": str(exc)}

    etype = event["type"]

    if etype == "checkout.session.completed":
        sess  = event["data"]["object"]
        email = (
            sess.get("customer_email")
            or sess.get("metadata", {}).get("email", "")
        )
        sub_id = sess.get("subscription")
        if email and sub_id:
            sub        = s.Subscription.retrieve(sub_id)
            expires_at = datetime.fromtimestamp(
                sub["current_period_end"], tz=timezone.utc
            ).isoformat()
            user_store.set_premium(
                email,
                stripe_customer_id     = sess.get("customer", ""),
                stripe_subscription_id = sub_id,
                expires_at             = expires_at,
            )

    elif etype in ("customer.subscription.deleted", "customer.subscription.paused"):
        sub  = event["data"]["object"]
        user = user_store.find_by_subscription(sub["id"])
        if user:
            user_store.set_free(user["email"])

    elif etype == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        sub_id  = invoice.get("subscription")
        if sub_id:
            sub        = s.Subscription.retrieve(sub_id)
            expires_at = datetime.fromtimestamp(
                sub["current_period_end"], tz=timezone.utc
            ).isoformat()
            user_store.renew_premium(sub_id, expires_at)

    return {"status": "handled", "type": etype}
