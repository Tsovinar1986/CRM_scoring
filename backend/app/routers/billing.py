"""Stripe subscriptions and license delivery for the seller storefront.

Starter is free (no plan). Pro and Advanced each bill monthly or annually.
Checkout happens on Stripe's own hosted page: POST /stripe/checkout creates a
Checkout Session for the chosen plan and returns its URL; after paying, Stripe
sends the buyer back -- to the app (/?checkout=<session id>) or the website's
thank-you.html -- which calls GET /stripe/session/<id> to confirm the payment
and get the license key. Card details never touch our servers. A fresh key is
issued for every paid billing period (via the webhook), each one valid a
little past the next billing date -- so a cancelled subscription simply stops
getting fresh keys.
"""

import json
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Literal

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import Path as PathParam
from loguru import logger
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import storage
from ..auth import get_current_tenant, get_optional_tenant
from ..config import (
    APP_BASE_URL,
    BILLING_CURRENCY,
    HOSTED_MODE,
    LICENSE_PRIVATE_KEY,
    LICENSE_VALIDITY_DAYS_ANNUAL,
    LICENSE_VALIDITY_DAYS_MONTHLY,
    PRICE_ADVANCED_ANNUAL,
    PRICE_ADVANCED_MONTHLY,
    PRICE_PRO_ANNUAL,
    PRICE_PRO_MONTHLY,
    RATE_LIMIT_AUTH,
    STOREFRONT_URL,
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
)
from ..middleware import limiter
from ..services.license_email import send_license_email

_LICENSING_DIR = Path(__file__).resolve().parents[3] / "licensing"
sys.path.insert(0, str(_LICENSING_DIR))
from issue_license import issue_license  # noqa: E402

router = APIRouter(prefix="/api/billing", tags=["billing"])
_ISSUED_LICENSES_LOG = _LICENSING_DIR / "issued_licenses.jsonl"
# The buyer's return from checkout and the webhooks can both try to fulfil
# the same billing period at nearly the same moment -- serialise the
# check-then-issue so one payment never produces two keys.
_fulfil_lock = threading.Lock()

Tier = Literal["pro", "advanced"]
Interval = Literal["monthly", "annual"]
_PRODUCT_NAMES = {"pro": "CRM Scoring Pro", "advanced": "CRM Scoring Advanced"}
_STRIPE_INTERVALS = {"monthly": "month", "annual": "year"}
# Stripe states in which a subscription grants its plan and earns keys.
_ACTIVE = ("active", "trialing")


def _configured() -> bool:
    return bool(STRIPE_SECRET_KEY)


def _api():
    if not _configured():
        raise HTTPException(status_code=503, detail="Stripe isn't configured on this deployment.")
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


def _prices() -> dict[tuple[str, str], str]:
    return {
        ("pro", "monthly"): PRICE_PRO_MONTHLY,
        ("pro", "annual"): PRICE_PRO_ANNUAL,
        ("advanced", "monthly"): PRICE_ADVANCED_MONTHLY,
        ("advanced", "annual"): PRICE_ADVANCED_ANNUAL,
    }


def _amount_cents(tier: str, interval: str) -> int:
    return int(Decimal(_prices()[(tier, interval)]) * 100)


def _lookup_key(tier: str, interval: str) -> str:
    # The amount is part of the key: Stripe prices can't be edited, so a new
    # amount in config means a new price, while existing subscribers keep theirs.
    return f"crm-scoring-{tier}-{interval}-{_amount_cents(tier, interval)}-{BILLING_CURRENCY.lower()}"


_price_ids: dict[str, str] = {}
_price_lock = threading.Lock()


def _price_id(tier: str, interval: str) -> str:
    """The Stripe price for a plan, created the first time the plan is sold."""
    key = _lookup_key(tier, interval)
    with _price_lock:
        if key in _price_ids:
            return _price_ids[key]
        api = _api()
        try:
            found = api.Price.list(lookup_keys=[key], active=True, limit=1).data
            if found:
                price_id = found[0].id
            else:
                price_id = api.Price.create(
                    currency=BILLING_CURRENCY.lower(),
                    unit_amount=_amount_cents(tier, interval),
                    recurring={"interval": _STRIPE_INTERVALS[interval]},
                    lookup_key=key,
                    product_data={"name": _PRODUCT_NAMES[tier]},
                    metadata={"tier": tier, "interval": interval},
                ).id
                logger.info("Created Stripe price {} ({})", price_id, key)
        except stripe.StripeError as exc:
            logger.warning("Couldn't find or create the Stripe price {}: {!r}", key, exc)
            raise HTTPException(status_code=502, detail="Couldn't connect to Stripe.")
        _price_ids[key] = price_id
        return price_id


def _validity_days(interval: str) -> int:
    return LICENSE_VALIDITY_DAYS_ANNUAL if interval == "annual" else LICENSE_VALIDITY_DAYS_MONTHLY


def _issued_record(transaction_id: str) -> dict | None:
    if not _ISSUED_LICENSES_LOG.exists():
        return None
    with _ISSUED_LICENSES_LOG.open() as log:
        for line in log:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("transaction_id") == transaction_id:
                return record
    return None


def _issue_and_deliver(email: str, interval: str, tier: str, transaction_id: str) -> str:
    if not LICENSE_PRIVATE_KEY:
        logger.error("Payment received for {} but LICENSE_PRIVATE_KEY isn't set.", email)
        raise HTTPException(status_code=500, detail="License signing key not configured on this deployment.")

    license_key = issue_license(
        email,
        plan=interval,
        private_key_b64=LICENSE_PRIVATE_KEY,
        days=_validity_days(interval),
        tier=tier,
    )
    _ISSUED_LICENSES_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _ISSUED_LICENSES_LOG.open("a") as log:
        log.write(
            json.dumps(
                {
                    "email": email,
                    "license_key": license_key,
                    "issued_at": time.time(),
                    "transaction_id": transaction_id,
                }
            )
            + "\n"
        )
    emailed = "@" in email and send_license_email(email, license_key, interval)
    logger.info(
        "Issued license for {} ({}){}",
        email,
        interval,
        "" if emailed else " — not emailed, see licensing/issued_licenses.jsonl",
    )
    return license_key


def _period_end(subscription) -> int | None:
    """End of the subscription's current paid period, as epoch seconds. Newer
    Stripe API versions keep it on the subscription item, older ones on the
    subscription itself."""
    for item in (subscription.get("items") or {}).get("data") or []:
        if item.get("current_period_end"):
            return int(item["current_period_end"])
    end = subscription.get("current_period_end")
    return int(end) if end else None


def _plan_of(subscription) -> tuple[str, str] | None:
    """(tier, interval) of one of our subscriptions; None if it isn't ours."""
    sources = [subscription.get("metadata") or {}]
    sources += [(item.get("price") or {}).get("metadata") or {} for item in (subscription.get("items") or {}).get("data") or []]
    for metadata in sources:
        plan = (metadata.get("tier"), metadata.get("interval"))
        if plan in _prices():
            return plan
    return None


def _get_session(session_id: str):
    try:
        return _api().checkout.Session.retrieve(session_id, expand=["subscription", "subscription.customer"])
    except stripe.InvalidRequestError as exc:
        if exc.code == "resource_missing":
            raise HTTPException(status_code=404, detail="Checkout session not found.")
        logger.warning("Couldn't fetch Stripe checkout session {}: {!r}", session_id, exc)
        raise HTTPException(status_code=502, detail="Couldn't look up the checkout session.")
    except stripe.StripeError as exc:
        logger.warning("Couldn't fetch Stripe checkout session {}: {!r}", session_id, exc)
        raise HTTPException(status_code=502, detail="Couldn't connect to Stripe.")


def _get_subscription(subscription_id: str):
    try:
        return _api().Subscription.retrieve(subscription_id, expand=["customer"])
    except stripe.InvalidRequestError as exc:
        if exc.code == "resource_missing":
            raise HTTPException(status_code=404, detail="Stripe subscription not found.")
        logger.warning("Couldn't fetch Stripe subscription {}: {!r}", subscription_id, exc)
        raise HTTPException(status_code=502, detail="Couldn't look up the Stripe subscription.")
    except stripe.StripeError as exc:
        logger.warning("Couldn't fetch Stripe subscription {}: {!r}", subscription_id, exc)
        raise HTTPException(status_code=502, detail="Couldn't connect to Stripe.")


def _licensee(subscription, session=None) -> str:
    """Who the key is issued to: the email the buyer gave Stripe Checkout,
    else the Stripe customer's email, else the customer id."""
    email = ((session or {}).get("customer_details") or {}).get("email")
    if email:
        return email
    customer = subscription.get("customer")
    if isinstance(customer, str):
        try:
            customer = _api().Customer.retrieve(customer)
        except stripe.StripeError as exc:
            logger.warning("Couldn't look up the customer for subscription {}: {!r}", subscription.get("id"), exc)
            raise HTTPException(status_code=502, detail="Couldn't look up the Stripe customer.")
    return (customer or {}).get("email") or f"Stripe customer {(customer or {}).get('id')}"


def _fulfil(subscription, licensee: str) -> dict:
    """Issue a key for the subscription's current billing period, at most once.

    A period is identified by (subscription id, period end): the buyer's
    return from checkout and the first invoice.paid webhook share one, and
    each renewal moves the period end forward, so it gets a fresh key. A
    period that already has one comes back as "duplicate", with that key.
    """
    if subscription.get("status") not in _ACTIVE:
        raise HTTPException(status_code=409, detail="Stripe subscription isn't active.")

    plan = _plan_of(subscription)
    if plan is None:
        logger.error("Stripe subscription {} isn't for a CRM Scoring plan.", subscription.get("id"))
        raise HTTPException(status_code=400, detail="Stripe subscription is for an unknown plan.")
    tier, interval = plan

    transaction_id = f"{subscription['id']}@{_period_end(subscription)}"
    with _fulfil_lock:
        record = _issued_record(transaction_id)
        if record is not None:
            status, license_key = "duplicate", record.get("license_key")
        else:
            status, license_key = "ok", _issue_and_deliver(licensee, interval, tier, transaction_id)
    return {"status": status, "email": licensee, "tier": tier, "plan": interval, "license_key": license_key}


def _activate_workspace(subscription) -> bool:
    """Hosted deployment: puts the workspace that started this checkout on
    the plan it paid for. True if this subscription belongs to a workspace."""
    tenant_id = (subscription.get("metadata") or {}).get("tenant_id")
    plan = _plan_of(subscription)
    if not (HOSTED_MODE and tenant_id and plan):
        return False
    # Never re-upgrade a workspace whose subscription was since cancelled
    # (e.g. the buyer reloads the page they returned to).
    if subscription.get("status") in _ACTIVE and not subscription.get("cancel_at_period_end"):
        if storage.get_tenant_subscription_id(tenant_id) != subscription["id"]:
            storage.set_tenant_subscription(tenant_id, plan[0], subscription["id"])
            logger.info("Workspace {} upgraded to {} ({})", tenant_id, plan[0], subscription["id"])
    return True


class CheckoutRequest(BaseModel):
    interval: Interval
    tier: Tier = "pro"
    # Where the buyer started: the app (returns there) or the website (its thank-you page).
    source: Literal["app", "site"] = "app"


@router.get("/config")
def billing_config():
    return {
        "checkout_available": _configured(),
        "currency": BILLING_CURRENCY,
        "environment": "live" if STRIPE_SECRET_KEY.startswith(("sk_live_", "rk_live_")) else "test",
        "price_monthly": PRICE_PRO_MONTHLY or None,
        "price_annual": PRICE_PRO_ANNUAL or None,
        "price_advanced_monthly": PRICE_ADVANCED_MONTHLY or None,
        "price_advanced_annual": PRICE_ADVANCED_ANNUAL or None,
    }


@router.post("/stripe/checkout")
@limiter.limit(RATE_LIMIT_AUTH)
def stripe_checkout(
    request: Request,
    payload: CheckoutRequest,
    tenant: storage.Tenant | None = Depends(get_optional_tenant),
):
    """Starts a Stripe Checkout for the plan; returns the payment page URL.

    On the hosted deployment, subscribing from inside a workspace also
    upgrades that workspace once paid (until the subscription ends -- see
    the webhook).
    """
    metadata = {"tier": payload.tier, "interval": payload.interval}
    workspace = HOSTED_MODE and tenant is not None and tenant.id != storage.DEFAULT_TENANT_ID
    if workspace:
        metadata["tenant_id"] = tenant.id

    if payload.source == "site":
        success_url = f"{STOREFRONT_URL.rstrip('/')}/thank-you.html?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{STOREFRONT_URL.rstrip('/')}/#pricing"
    else:
        success_url = f"{APP_BASE_URL.rstrip('/')}/?checkout={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{APP_BASE_URL.rstrip('/')}/#plans"

    params = {
        "mode": "subscription",
        "line_items": [{"price": _price_id(payload.tier, payload.interval), "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
    }
    if workspace and tenant.email:
        params["customer_email"] = tenant.email
    try:
        session = _api().checkout.Session.create(**params)
    except stripe.StripeError as exc:
        logger.warning("Couldn't start Stripe checkout for {} {}: {!r}", payload.tier, payload.interval, exc)
        raise HTTPException(status_code=502, detail="Couldn't connect to Stripe.")
    return {"url": session["url"], "session_id": session["id"]}


@router.get("/stripe/session/{session_id}")
@limiter.limit(RATE_LIMIT_AUTH)
def stripe_session(request: Request, session_id: str = PathParam(max_length=255, pattern=r"^cs_[A-Za-z0-9_]+$")):
    """Confirms a finished checkout and returns its license key.

    Called by the page Stripe sends the buyer back to. Only the buyer has the
    session id, so a reload shows the same key again instead of a new one.
    """
    session = _get_session(session_id)
    if (
        session.get("mode") != "subscription"
        or session.get("status") != "complete"
        or session.get("payment_status") not in ("paid", "no_payment_required")
    ):
        raise HTTPException(status_code=409, detail="This payment isn't complete yet.")

    subscription = session.get("subscription")
    if isinstance(subscription, str):
        subscription = _get_subscription(subscription)
    upgraded = _activate_workspace(subscription)
    result = _fulfil(subscription, _licensee(subscription, session))
    if result["status"] == "duplicate" and result["license_key"]:
        result["status"] = "ok"
    return {**result, "workspace_upgraded": upgraded}


def cancel_at_stripe(subscription_id: str, *, immediately: bool = False):
    """Stops future charges on a subscription -- at the end of the paid
    period, or right away (e.g. the account is being deleted). Returns the
    subscription (None if Stripe no longer has it); raises 502 if it couldn't
    be cancelled, so callers never go on as if billing had stopped when it hasn't."""
    api = _api()
    try:
        subscription = api.Subscription.retrieve(subscription_id)
        if subscription.get("status") in ("canceled", "incomplete_expired"):
            return subscription
        if immediately:
            return api.Subscription.cancel(subscription_id)
        if subscription.get("cancel_at_period_end"):
            return subscription
        return api.Subscription.modify(subscription_id, cancel_at_period_end=True)
    except stripe.InvalidRequestError as exc:
        if exc.code == "resource_missing":
            return None
        logger.warning("Couldn't cancel {}: {!r}", subscription_id, exc)
        raise HTTPException(status_code=502, detail="Stripe couldn't cancel the subscription.")
    except stripe.StripeError as exc:
        logger.warning("Couldn't cancel {}: {!r}", subscription_id, exc)
        raise HTTPException(status_code=502, detail="Couldn't connect to Stripe.")


@router.post("/subscription/cancel")
def cancel_workspace_subscription(tenant: storage.Tenant = Depends(get_current_tenant)):
    """Self-serve cancel for a hosted workspace. Stops future charges; the
    workspace keeps its plan until the end of the period already paid for."""
    subscription_id = storage.get_tenant_subscription_id(tenant.id)
    if not subscription_id:
        raise HTTPException(status_code=404, detail="This workspace has no active subscription.")
    subscription = cancel_at_stripe(subscription_id)

    access_until = _period_end(subscription) if subscription is not None else None
    storage.end_tenant_subscription(subscription_id, access_until)
    logger.info("Workspace {} cancelled {} (access until {})", tenant.id, subscription_id, access_until)
    return {"status": "cancelled", "access_until": access_until}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Renewals and cancellations, plus a fallback if the buyer never made it
    back from checkout.

    In the Stripe Dashboard (Developers -> Webhooks) add
    https://<backend>/api/billing/stripe/webhook for checkout.session.completed,
    invoice.paid, customer.subscription.updated and
    customer.subscription.deleted, and set its signing secret as
    STRIPE_WEBHOOK_SECRET.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing Stripe webhook signature.")
    # Everything below makes blocking Stripe API calls -- keep them off the
    # event loop.
    return await run_in_threadpool(_handle_webhook, payload, signature)


def _parse_webhook(payload: bytes, signature: str):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Stripe webhooks aren't configured on this deployment.")
    try:
        return stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature.")


def _invoice_subscription_id(invoice) -> str | None:
    # API 2025-03-31 and later: invoice.parent.subscription_details.subscription;
    # earlier versions: invoice.subscription.
    details = (invoice.get("parent") or {}).get("subscription_details") or {}
    subscription = details.get("subscription") or invoice.get("subscription")
    return subscription if isinstance(subscription, str) else (subscription or {}).get("id")


def _handle_webhook(payload: bytes, signature: str) -> dict:
    event = _parse_webhook(payload, signature)
    kind = event["type"]
    obj = event["data"]["object"]

    if kind == "customer.subscription.deleted":
        storage.end_tenant_subscription(obj["id"], None)
        logger.info("Stripe subscription {} ended", obj["id"])
        return {"status": "ok"}
    if kind == "customer.subscription.updated":
        # A hosted workspace keeps its plan until the paid period ends if it
        # was cancelled early, then drops to Starter; a self-hosted buyer's
        # last key just runs out, since no renewal will issue a new one.
        if obj.get("status") in ("canceled", "unpaid", "incomplete_expired"):
            storage.end_tenant_subscription(obj["id"], None)
        elif obj.get("cancel_at_period_end"):
            storage.end_tenant_subscription(obj["id"], _period_end(obj))
        return {"status": "ok"}

    if kind == "checkout.session.completed":
        if obj.get("mode") != "subscription":
            return {"status": "ignored"}
        session = _get_session(obj["id"])
        subscription = session.get("subscription")
        if isinstance(subscription, str):
            subscription = _get_subscription(subscription)
        _activate_workspace(subscription)
        licensee_of = lambda: _licensee(subscription, session)  # noqa: E731
    elif kind == "invoice.paid":
        subscription_id = _invoice_subscription_id(obj)
        if not subscription_id:
            return {"status": "ignored"}
        # Re-read the subscription so its period reflects the invoice just paid.
        subscription = _get_subscription(subscription_id)
        licensee_of = lambda: obj.get("customer_email") or _licensee(subscription)  # noqa: E731
    else:
        # Failed payments etc.: nothing to do until it's paid or cancelled.
        logger.info("Stripe {} ignored", kind)
        return {"status": "ignored"}

    try:
        result = _fulfil(subscription, licensee_of())
    except HTTPException as exc:
        # 4xx here means the subscription itself is unusable -- acknowledge
        # it so Stripe stops retrying. 5xx/502s propagate and it retries.
        if exc.status_code < 500:
            logger.warning("Stripe {} for {} not fulfilled: {}", kind, subscription.get("id"), exc.detail)
            return {"status": "rejected"}
        raise
    return {"status": result["status"]}
