"""Stripe subscriptions and license delivery for the seller storefront.

Starter is free (no plan). Pro and Advanced each bill monthly or annually.
Checkout happens on Stripe's hosted page: POST /checkout creates a checkout
session for the chosen plan and returns its URL; after paying, the buyer is
sent back -- to the app (/?checkout=<session id>) or the website's
thank-you.html -- which calls GET /session/<id> to confirm the payment and
get the license key. Card details never touch our servers. A fresh key is
issued for every paid billing period (via the webhook), each one valid a
little past the next billing date -- so a cancelled subscription simply
stops getting fresh keys.

The Stripe calls themselves live in services/stripe_billing.py, which hands
back plain checkout-session and subscription dicts; its webhook events are
translated into the few events _handle_event acts on.
"""

import json
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Literal

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
    PAYPAL_CLIENT_ID,
    PAYPAL_CLIENT_SECRET,
    PAYPAL_MODE,
    PAYPAL_WEBHOOK_ID,
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
)
from ..middleware import limiter
from ..services.license_email import send_license_email
from ..i18n import request_lang
from ..services.paypal_billing import PayPalBilling
from ..services.stripe_billing import BillingError, StripeBilling

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
_INTERVALS = {"monthly": "month", "annual": "year"}


def _configured() -> bool:
    return bool(STRIPE_SECRET_KEY)


def _api() -> StripeBilling:
    if not _configured():
        raise HTTPException(status_code=503, detail="Checkout isn't configured on this deployment.")
    return StripeBilling(STRIPE_SECRET_KEY)


def _paypal_configured() -> bool:
    return bool(PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)


def _paypal() -> PayPalBilling:
    if not _paypal_configured():
        raise HTTPException(status_code=503, detail="PayPal isn't configured on this deployment.")
    return PayPalBilling(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_MODE)


def _is_paypal(subscription_id: str) -> bool:
    # PayPal subscription ids look like I-ABC123...; Stripe's start with sub_.
    return subscription_id.startswith("I-")


def _call(what: str, fn, *args, **kwargs):
    """Runs a Stripe call, turning its errors into HTTP ones: 404 stays 404,
    anything else is a 502 so callers never carry on as if it had worked."""
    try:
        return fn(*args, **kwargs)
    except BillingError as exc:
        if exc.status == 404:
            raise HTTPException(status_code=404, detail=f"{what.capitalize()} not found.")
        logger.warning("Stripe: couldn't {}: {}", what, exc)
        raise HTTPException(status_code=502, detail="Couldn't connect to the payment service.")


def _prices() -> dict[tuple[str, str], str]:
    return {
        ("pro", "monthly"): PRICE_PRO_MONTHLY,
        ("pro", "annual"): PRICE_PRO_ANNUAL,
        ("advanced", "monthly"): PRICE_ADVANCED_MONTHLY,
        ("advanced", "annual"): PRICE_ADVANCED_ANNUAL,
    }


def _amount_cents(tier: str, interval: str) -> int:
    return int(Decimal(_prices()[(tier, interval)]) * 100)


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


def _plan_of(subscription: dict) -> tuple[str, str] | None:
    """(tier, interval) of one of our subscriptions; None if it isn't ours."""
    metadata = subscription.get("metadata") or {}
    plan = (metadata.get("tier"), metadata.get("interval"))
    return plan if plan in _prices() else None


def _licensee(subscription: dict) -> str:
    """Who the key is issued to: the buyer's email, else the subscription id."""
    return subscription.get("customer_email") or f"Stripe subscription {subscription['id']}"


def _fulfil(subscription: dict) -> dict:
    """Issue a key for the subscription's current billing period, at most once.

    A period is identified by (subscription id, period end): the buyer's
    return from checkout and the first payment.succeeded webhook share one,
    and each renewal moves the period end forward, so it gets a fresh key. A
    period that already has one comes back as "duplicate", with that key.
    """
    if subscription.get("status") != "active":
        raise HTTPException(status_code=409, detail="Subscription isn't active.")

    plan = _plan_of(subscription)
    if plan is None:
        logger.error("Subscription {} isn't for a CRM Scoring plan.", subscription.get("id"))
        raise HTTPException(status_code=400, detail="Subscription is for an unknown plan.")
    tier, interval = plan

    licensee = _licensee(subscription)
    transaction_id = f"{subscription['id']}@{subscription['current_period_end']}"
    with _fulfil_lock:
        record = _issued_record(transaction_id)
        if record is not None:
            status, license_key = "duplicate", record.get("license_key")
        else:
            status, license_key = "ok", _issue_and_deliver(licensee, interval, tier, transaction_id)
    return {"status": status, "email": licensee, "tier": tier, "plan": interval, "license_key": license_key}


def _activate_workspace(subscription: dict) -> bool:
    """Hosted deployment: puts the workspace that started this checkout on
    the plan it paid for. True if this subscription belongs to a workspace."""
    tenant_id = (subscription.get("metadata") or {}).get("tenant_id")
    plan = _plan_of(subscription)
    if not (HOSTED_MODE and tenant_id and plan):
        return False
    # Never re-upgrade a workspace whose subscription was since cancelled
    # (e.g. the buyer reloads the page they returned to).
    if subscription.get("status") == "active" and not subscription.get("cancel_at_period_end"):
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
        "paypal_available": _paypal_configured(),
        "currency": BILLING_CURRENCY,
        "environment": "live" if STRIPE_SECRET_KEY.startswith(("sk_live_", "rk_live_")) else "test",
        "price_monthly": PRICE_PRO_MONTHLY or None,
        "price_annual": PRICE_PRO_ANNUAL or None,
        "price_advanced_monthly": PRICE_ADVANCED_MONTHLY or None,
        "price_advanced_annual": PRICE_ADVANCED_ANNUAL or None,
    }


@router.post("/checkout")
@limiter.limit(RATE_LIMIT_AUTH)
def checkout(
    request: Request,
    payload: CheckoutRequest,
    tenant: storage.Tenant | None = Depends(get_optional_tenant),
):
    """Starts a checkout for the plan; returns the payment page URL.

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

    session = _call(
        "start checkout",
        _api().create_checkout,
        amount=_amount_cents(payload.tier, payload.interval),
        currency=BILLING_CURRENCY,
        description=f"{_PRODUCT_NAMES[payload.tier]} ({payload.interval})",
        mode="subscription",
        interval=_INTERVALS[payload.interval],
        customer_email=tenant.email if workspace and tenant.email else None,
        metadata=metadata,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return {"url": session["url"], "session_id": session["id"]}


@router.get("/session/{session_id}")
@limiter.limit(RATE_LIMIT_AUTH)
def checkout_session(request: Request, session_id: str = PathParam(max_length=255, pattern=r"^cs_[A-Za-z0-9_]+$")):
    """Confirms a finished checkout and returns its license key.

    Called by the page the buyer is sent back to. Only the buyer has the
    session id, so a reload shows the same key again instead of a new one.
    """
    api = _api()
    session = _call("look up the checkout session", api.get_checkout, session_id)
    if session.get("mode") != "subscription" or session.get("status") != "complete" or not session.get("subscription_id"):
        raise HTTPException(status_code=409, detail="This payment isn't complete yet.")

    subscription = _call("look up the subscription", api.get_subscription, session["subscription_id"])
    upgraded = _activate_workspace(subscription)
    result = _fulfil(subscription)
    if result["status"] == "duplicate" and result["license_key"]:
        result["status"] = "ok"
    return {**result, "workspace_upgraded": upgraded}


def cancel_subscription(subscription_id: str, *, immediately: bool = False) -> dict | None:
    """Stops future charges on a subscription -- at the end of the paid
    period, or right away (e.g. the account is being deleted). Returns the
    subscription (None if Stripe no longer has it); raises 502 if it couldn't
    be cancelled, so callers never go on as if billing had stopped when it hasn't."""
    try:
        provider = _paypal() if _is_paypal(subscription_id) else _api()
        return provider.cancel_subscription(subscription_id, at_period_end=not immediately)
    except BillingError as exc:
        if exc.status == 404:
            return None
        logger.warning("Couldn't cancel {}: {}", subscription_id, exc)
        raise HTTPException(status_code=502, detail="Couldn't connect to the payment service.")


@router.post("/subscription/cancel")
def cancel_workspace_subscription(tenant: storage.Tenant = Depends(get_current_tenant)):
    """Self-serve cancel for a hosted workspace. Stops future charges; the
    workspace keeps its plan until the end of the period already paid for."""
    subscription_id = storage.get_tenant_subscription_id(tenant.id)
    if not subscription_id:
        raise HTTPException(status_code=404, detail="This workspace has no active subscription.")
    subscription = cancel_subscription(subscription_id)

    access_until = subscription["current_period_end"] if subscription is not None else None
    storage.end_tenant_subscription(subscription_id, access_until)
    logger.info("Workspace {} cancelled {} (access until {})", tenant.id, subscription_id, access_until)
    return {"status": "cancelled", "access_until": access_until}


@router.post("/paypal/checkout")
@limiter.limit(RATE_LIMIT_AUTH)
def paypal_checkout(
    request: Request,
    payload: CheckoutRequest,
    tenant: storage.Tenant | None = Depends(get_optional_tenant),
):
    """Starts a PayPal subscription for the plan; returns PayPal's approval
    page URL. PayPal sends the buyer back with ?subscription_id=..., and the
    page they land on confirms it through /paypal/subscription/<id>."""
    metadata = {"tier": payload.tier, "interval": payload.interval}
    workspace = HOSTED_MODE and tenant is not None and tenant.id != storage.DEFAULT_TENANT_ID
    if workspace:
        metadata["tenant_id"] = tenant.id
    if payload.source == "site":
        return_url = f"{STOREFRONT_URL.rstrip('/')}/thank-you.html?paypal=1"
        cancel_url = f"{STOREFRONT_URL.rstrip('/')}/#pricing"
    else:
        return_url = f"{APP_BASE_URL.rstrip('/')}/?paypal=1"
        cancel_url = f"{APP_BASE_URL.rstrip('/')}/#plans"
    started = _call(
        "start PayPal checkout",
        _paypal().create_subscription,
        amount=_amount_cents(payload.tier, payload.interval),
        description=f"{_PRODUCT_NAMES[payload.tier]} ({payload.interval})",
        currency=BILLING_CURRENCY,
        interval=_INTERVALS[payload.interval],
        metadata=metadata,
        return_url=return_url,
        cancel_url=cancel_url,
        customer_email=tenant.email if workspace and tenant.email else None,
        lang=request_lang(request),
    )
    return {"url": started["url"], "subscription_id": started["id"]}


@router.get("/paypal/subscription/{subscription_id}")
@limiter.limit(RATE_LIMIT_AUTH)
def paypal_subscription(request: Request, subscription_id: str = PathParam(max_length=64, pattern=r"^I-[A-Z0-9]+$")):
    """Confirms an approved PayPal subscription and returns its license key
    (or that the workspace was upgraded). A reload shows the same key again."""
    subscription = _call("look up the PayPal subscription", _paypal().get_subscription, subscription_id)
    if subscription["status"] != "active":
        raise HTTPException(status_code=409, detail="This payment isn't complete yet.")
    upgraded = _activate_workspace(subscription)
    result = _fulfil(subscription)
    if result["status"] == "duplicate" and result["license_key"]:
        result["status"] = "ok"
    return {**result, "workspace_upgraded": upgraded}


@router.post("/paypal/webhook")
async def paypal_webhook(request: Request):
    """Renewals and cancellations of PayPal subscriptions, plus a fallback if
    the buyer never made it back. In the PayPal developer dashboard (Apps &
    Credentials -> your app -> Webhooks) add
    https://<backend>/api/billing/paypal/webhook for BILLING.SUBSCRIPTION.ACTIVATED,
    BILLING.SUBSCRIPTION.CANCELLED, BILLING.SUBSCRIPTION.EXPIRED,
    BILLING.SUBSCRIPTION.SUSPENDED and PAYMENT.SALE.COMPLETED, and set its id
    as PAYPAL_WEBHOOK_ID.
    """
    try:
        event = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")
    headers = {k.lower(): v for k, v in request.headers.items()}
    # Verifying and re-reading the subscription are blocking PayPal calls.
    return await run_in_threadpool(_handle_paypal_webhook, headers, event)


def _verify_paypal_webhook(headers: dict, event: dict) -> None:
    if not (_paypal_configured() and PAYPAL_WEBHOOK_ID):
        raise HTTPException(status_code=503, detail="Webhooks aren't configured on this deployment.")
    if not _call("verify the PayPal webhook", _paypal().verify_webhook, headers, event, PAYPAL_WEBHOOK_ID):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")


def _handle_paypal_webhook(headers: dict, event: dict) -> dict:
    _verify_paypal_webhook(headers, event)
    translated = _call("handle the webhook", _paypal().translate_event, event)
    if translated is None:
        logger.info("PayPal {} ignored", event.get("event_type"))
        return {"status": "ignored"}
    return _handle_event(translated)


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Renewals and cancellations, plus a fallback if the buyer never made it
    back from checkout. In the Stripe Dashboard (Developers -> Webhooks)
    add https://<backend>/api/billing/stripe/webhook for
    checkout.session.completed, invoice.paid, customer.subscription.updated
    and customer.subscription.deleted, and set its signing secret as
    STRIPE_WEBHOOK_SECRET.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing webhook signature.")
    # Re-reading the subscription is a blocking Stripe call -- keep it off the event loop.
    return await run_in_threadpool(_handle_stripe_webhook, payload, signature)


def _parse_stripe_webhook(payload: bytes, signature: str):
    if not (STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET):
        raise HTTPException(status_code=503, detail="Webhooks aren't configured on this deployment.")
    try:
        return StripeBilling.parse_webhook(payload, signature, STRIPE_WEBHOOK_SECRET)
    except Exception:  # ValueError or stripe.SignatureVerificationError
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")


def _handle_stripe_webhook(payload: bytes, signature: str) -> dict:
    event = _parse_stripe_webhook(payload, signature)
    translated = _call("handle the webhook", _translate, event)
    if translated is None:
        logger.info("Stripe {} ignored", event["type"])
        return {"status": "ignored"}
    return _handle_event(translated)


def _translate(event) -> dict | None:
    return StripeBilling(STRIPE_SECRET_KEY).translate_event(event)


def _handle_event(event: dict) -> dict:
    """A verified Stripe event, translated by services/stripe_billing.py."""
    kind = event["type"]
    obj = event["data"]["object"]

    if kind == "subscription.canceled":
        storage.end_tenant_subscription(obj["id"], None)
        logger.info("Subscription {} ended", obj["id"])
        return {"status": "ok"}
    if kind == "subscription.updated":
        # A hosted workspace keeps its plan until the paid period ends if it
        # was cancelled early, then drops to Starter; a self-hosted buyer's
        # last key just runs out, since no renewal will issue a new one.
        if obj.get("cancel_at_period_end"):
            storage.end_tenant_subscription(obj["id"], obj["current_period_end"])
        return {"status": "ok"}
    if kind != "payment.succeeded" or not obj.get("subscription"):
        # Failed payments, one-off payments etc.: nothing to do.
        logger.info("Billing event {} ignored", kind)
        return {"status": "ignored"}

    # The first payment and every renewal: a fresh key for the new period.
    subscription = obj["subscription"]
    _activate_workspace(subscription)
    try:
        result = _fulfil(subscription)
    except HTTPException as exc:
        # 4xx here means the subscription itself is unusable -- acknowledge
        # it so Stripe stops retrying. 5xx propagate and it retries.
        if exc.status_code < 500:
            logger.warning("Billing event {} for {} not fulfilled: {}", kind, subscription.get("id"), exc.detail)
            return {"status": "rejected"}
        raise
    return {"status": result["status"]}
