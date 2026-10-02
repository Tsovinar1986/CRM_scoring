"""Braintree subscriptions and license delivery for the seller storefront.

Starter is free (no plan). Pro and Advanced each have a monthly and an annual
Braintree plan (create them with backend/scripts/create_braintree_plans.py).
Checkout happens in-page with Braintree's Drop-in card form: the browser gets
a client token from /braintree/client-token, tokenizes the card, and posts the
nonce to /braintree/subscribe, which creates the customer and subscription and
returns the license key straight away. A fresh key is issued on every renewal
(via the webhook), each one valid a little past the next billing date -- so a
cancelled subscription simply stops getting fresh keys.
"""

import json
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import braintree
from braintree.exceptions.braintree_error import BraintreeError
from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, EmailStr, Field
from starlette.concurrency import run_in_threadpool

from .. import storage
from ..auth import get_current_tenant, get_optional_tenant
from ..config import (
    BILLING_CURRENCY,
    BRAINTREE_ENVIRONMENT,
    BRAINTREE_MERCHANT_ID,
    BRAINTREE_PLAN_ADVANCED_ANNUAL,
    BRAINTREE_PLAN_ADVANCED_MONTHLY,
    BRAINTREE_PLAN_PRO_ANNUAL,
    BRAINTREE_PLAN_PRO_MONTHLY,
    BRAINTREE_PRIVATE_KEY,
    BRAINTREE_PUBLIC_KEY,
    HOSTED_MODE,
    LICENSE_PRIVATE_KEY,
    LICENSE_VALIDITY_DAYS_ANNUAL,
    LICENSE_VALIDITY_DAYS_MONTHLY,
    PRICE_ADVANCED_ANNUAL,
    PRICE_ADVANCED_MONTHLY,
    PRICE_PRO_ANNUAL,
    PRICE_PRO_MONTHLY,
    RATE_LIMIT_AUTH,
)
from ..middleware import limiter
from ..services.license_email import send_license_email

_LICENSING_DIR = Path(__file__).resolve().parents[3] / "licensing"
sys.path.insert(0, str(_LICENSING_DIR))
from issue_license import issue_license  # noqa: E402

router = APIRouter(prefix="/api/billing", tags=["billing"])
_ISSUED_LICENSES_LOG = _LICENSING_DIR / "issued_licenses.jsonl"
# The in-page checkout and the webhooks can both try to fulfil the same
# billing period at nearly the same moment -- serialise the check-then-issue
# so one payment never produces two keys.
_fulfil_lock = threading.Lock()

Tier = Literal["pro", "advanced"]
Interval = Literal["monthly", "annual"]


def _configured() -> bool:
    return bool(BRAINTREE_MERCHANT_ID and BRAINTREE_PUBLIC_KEY and BRAINTREE_PRIVATE_KEY)


def _gateway() -> braintree.BraintreeGateway:
    if not _configured():
        raise HTTPException(status_code=503, detail="Braintree isn't configured on this deployment.")
    return braintree.BraintreeGateway(
        braintree.Configuration(
            environment=braintree.Environment.parse_environment(BRAINTREE_ENVIRONMENT),
            merchant_id=BRAINTREE_MERCHANT_ID,
            public_key=BRAINTREE_PUBLIC_KEY,
            private_key=BRAINTREE_PRIVATE_KEY,
        )
    )


def _plans() -> dict[tuple[str, str], str]:
    return {
        ("pro", "monthly"): BRAINTREE_PLAN_PRO_MONTHLY,
        ("pro", "annual"): BRAINTREE_PLAN_PRO_ANNUAL,
        ("advanced", "monthly"): BRAINTREE_PLAN_ADVANCED_MONTHLY,
        ("advanced", "annual"): BRAINTREE_PLAN_ADVANCED_ANNUAL,
    }


def _plan_for(tier: str, interval: str) -> str:
    return _plans().get((tier, interval), "")


def _tier_for_plan(plan_id: str) -> tuple[str, str] | None:
    """Map a Braintree plan id back to (tier, interval); None if it isn't ours."""
    for key, value in _plans().items():
        if value and value == plan_id:
            return key
    return None


def _validity_days(interval: str) -> int:
    return LICENSE_VALIDITY_DAYS_ANNUAL if interval == "annual" else LICENSE_VALIDITY_DAYS_MONTHLY


def _already_issued(transaction_id: str) -> bool:
    if not _ISSUED_LICENSES_LOG.exists():
        return False
    with _ISSUED_LICENSES_LOG.open() as log:
        for line in log:
            try:
                if json.loads(line).get("transaction_id") == transaction_id:
                    return True
            except json.JSONDecodeError:
                continue
    return False


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
    # Checkout doesn't ask for an email, so the licensee may be a cardholder
    # name or customer id -- those keys are only in the log above.
    emailed = "@" in email and send_license_email(email, license_key, interval)
    logger.info(
        "Issued license for {} ({}){}",
        email,
        interval,
        "" if emailed else " — not emailed, see licensing/issued_licenses.jsonl",
    )
    return license_key


def _get_subscription(subscription_id: str):
    try:
        return _gateway().subscription.find(subscription_id)
    except braintree.exceptions.NotFoundError:
        raise HTTPException(status_code=404, detail="Braintree subscription not found.")
    except BraintreeError as exc:
        logger.warning("Couldn't fetch Braintree subscription {}: {!r}", subscription_id, exc)
        raise HTTPException(status_code=502, detail="Couldn't look up the Braintree subscription.")


def _licensee(subscription) -> str:
    """Who the key is issued to: the customer's email if Braintree has one,
    else the cardholder name, else the Braintree customer id."""
    try:
        gateway = _gateway()
        payment_method = gateway.payment_method.find(subscription.payment_method_token)
        customer = gateway.customer.find(payment_method.customer_id)
        return (
            customer.email
            or getattr(payment_method, "cardholder_name", None)
            or f"Braintree customer {payment_method.customer_id}"
        )
    except BraintreeError as exc:
        logger.warning("Couldn't look up the customer for subscription {}: {!r}", subscription.id, exc)
        raise HTTPException(status_code=502, detail="Couldn't look up the Braintree customer.")


def _fulfil(subscription, licensee: str | None = None) -> dict:
    """Issue a key for the subscription's current billing period, at most once.

    A period is identified by (subscription id, paid-through date): checkout
    and the first SubscriptionChargedSuccessfully webhook share one, and each
    successful renewal charge moves paid_through_date forward, so it gets a
    fresh key.
    """
    if subscription.status != braintree.Subscription.Status.Active:
        raise HTTPException(status_code=409, detail="Braintree subscription isn't active.")

    plan = _tier_for_plan(subscription.plan_id)
    if plan is None:
        logger.error("Braintree subscription {} is on unknown plan {}.", subscription.id, subscription.plan_id)
        raise HTTPException(status_code=400, detail="Braintree subscription is for an unknown plan.")
    tier, interval = plan

    email = licensee or _licensee(subscription)

    transaction_id = f"{subscription.id}@{subscription.paid_through_date}"
    with _fulfil_lock:
        if _already_issued(transaction_id):
            return {"status": "duplicate"}
        license_key = _issue_and_deliver(email, interval, tier, transaction_id)
    return {"status": "ok", "email": email, "tier": tier, "plan": interval, "license_key": license_key}


def _result_error(result) -> str:
    """A buyer-safe explanation of a failed Braintree call."""
    verification = getattr(result, "credit_card_verification", None)
    if verification is not None and verification.status == "processor_declined":
        return "Your card was declined. Please try a different card."
    if verification is not None and verification.status == "gateway_rejected":
        return "Your card couldn't be verified. Check the CVV and postal code and try again."
    return result.message or "Braintree couldn't process the payment."


class SubscribeRequest(BaseModel):
    interval: Interval
    tier: Tier = "pro"
    # Optional: checkout doesn't ask for it, but if given the key (and every
    # renewal key) is emailed there too.
    email: EmailStr | None = None
    payment_method_nonce: str = Field(min_length=1, max_length=512)
    device_data: str | None = Field(default=None, max_length=10_000)


@router.get("/config")
def billing_config():
    plans = {f"{tier}_{interval}": plan_id or None for (tier, interval), plan_id in _plans().items()}
    return {
        "checkout_available": _configured() and all(plans.values()),
        "plans": plans,
        "currency": BILLING_CURRENCY,
        "environment": BRAINTREE_ENVIRONMENT,
        "price_monthly": PRICE_PRO_MONTHLY or None,
        "price_annual": PRICE_PRO_ANNUAL or None,
        "price_advanced_monthly": PRICE_ADVANCED_MONTHLY or None,
        "price_advanced_annual": PRICE_ADVANCED_ANNUAL or None,
    }


@router.get("/braintree/client-token")
def braintree_client_token():
    # Short-lived and public by design -- Drop-in needs it in the browser to
    # tokenize the card. The private key never leaves the server.
    try:
        return {"client_token": _gateway().client_token.generate()}
    except BraintreeError as exc:
        logger.warning("Couldn't generate a Braintree client token: {!r}", exc)
        raise HTTPException(status_code=502, detail="Couldn't connect to Braintree.")


@router.post("/braintree/subscribe")
@limiter.limit(RATE_LIMIT_AUTH)
def braintree_subscribe(
    request: Request,
    payload: SubscribeRequest,
    tenant: storage.Tenant | None = Depends(get_optional_tenant),
):
    """Vault the buyer's card and start the subscription; returns the key.

    On the hosted deployment, subscribing from inside a workspace also
    upgrades that workspace (until the subscription ends -- see the webhook).
    """
    plan_id = _plan_for(payload.tier, payload.interval)
    if not plan_id:
        raise HTTPException(status_code=503, detail="Billing plans aren't configured on this deployment.")
    gateway = _gateway()

    customer_params = {
        "payment_method_nonce": payload.payment_method_nonce,
        "credit_card": {"options": {"verify_card": True}},
    }
    if payload.email:
        customer_params["email"] = payload.email
    if payload.device_data:
        customer_params["device_data"] = payload.device_data
    try:
        customer = gateway.customer.create(customer_params)
        if not customer.is_success:
            logger.info("Braintree customer create failed for {}: {}", payload.email or "(no email)", customer.message)
            raise HTTPException(status_code=402, detail=_result_error(customer))

        token = customer.customer.payment_methods[0].token
        created = gateway.subscription.create({"payment_method_token": token, "plan_id": plan_id})
    except BraintreeError as exc:
        logger.warning("Braintree checkout failed for {}: {!r}", payload.email or "(no email)", exc)
        raise HTTPException(status_code=502, detail="Couldn't connect to Braintree.")
    if not created.is_success:
        logger.info("Braintree subscription create failed for {}: {}", payload.email or "(no email)", created.message)
        raise HTTPException(status_code=402, detail=_result_error(created))

    subscription = created.subscription
    workspace = HOSTED_MODE and tenant is not None and tenant.id != storage.DEFAULT_TENANT_ID
    if workspace:
        storage.set_tenant_subscription(tenant.id, payload.tier, subscription.id)
        logger.info("Workspace {} upgraded to {} ({})", tenant.id, payload.tier, subscription.id)
    result = _fulfil(subscription, licensee=payload.email or (tenant.email if workspace else None))
    return {**result, "workspace_upgraded": workspace}


def _paid_until(subscription) -> float | None:
    """End of the last paid day, as epoch seconds (None if unknown)."""
    paid_through = getattr(subscription, "paid_through_date", None)
    if isinstance(paid_through, str):
        paid_through = date.fromisoformat(paid_through)
    if not isinstance(paid_through, date):
        return None
    day_after = datetime.combine(paid_through + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return day_after.timestamp()


def cancel_at_braintree(subscription_id: str):
    """Stops future charges on a subscription. Returns it (None if Braintree
    no longer has it); raises 502 if it couldn't be cancelled, so callers
    never go on as if billing had stopped when it hasn't."""
    gateway = _gateway()
    try:
        subscription = gateway.subscription.find(subscription_id)
        if subscription.status != braintree.Subscription.Status.Canceled:
            result = gateway.subscription.cancel(subscription_id)
            if not result.is_success:
                logger.warning("Couldn't cancel {}: {}", subscription_id, result.message)
                raise HTTPException(status_code=502, detail="Braintree couldn't cancel the subscription.")
        return subscription
    except braintree.exceptions.NotFoundError:
        return None
    except BraintreeError as exc:
        logger.warning("Couldn't cancel {}: {!r}", subscription_id, exc)
        raise HTTPException(status_code=502, detail="Couldn't connect to Braintree.")


@router.post("/subscription/cancel")
def cancel_workspace_subscription(tenant: storage.Tenant = Depends(get_current_tenant)):
    """Self-serve cancel for a hosted workspace. Stops future charges; the
    workspace keeps its plan until the end of the period already paid for."""
    subscription_id = storage.get_tenant_subscription_id(tenant.id)
    if not subscription_id:
        raise HTTPException(status_code=404, detail="This workspace has no active subscription.")
    subscription = cancel_at_braintree(subscription_id)

    access_until = _paid_until(subscription) if subscription is not None else None
    storage.end_tenant_subscription(subscription_id, access_until)
    logger.info("Workspace {} cancelled {} (access until {})", tenant.id, subscription_id, access_until)
    return {"status": "cancelled", "access_until": access_until}


@router.post("/braintree/webhook")
async def braintree_webhook(request: Request):
    """Renewals, plus a fallback if the checkout response never reached the buyer.

    Add https://<backend>/api/billing/braintree/webhook in the Braintree
    Control Panel (Settings -> Webhooks) for "Subscription Charged
    Successfully" and "Subscription Went Active".
    """
    form = await request.form()
    signature, payload = form.get("bt_signature"), form.get("bt_payload")
    if not isinstance(signature, str) or not isinstance(payload, str):
        raise HTTPException(status_code=400, detail="Missing Braintree webhook signature or payload.")
    # Everything below makes blocking Braintree API calls -- keep them off
    # the event loop.
    return await run_in_threadpool(_handle_webhook, signature, payload)


def _parse_webhook(signature: str, payload: str):
    try:
        return _gateway().webhook_notification.parse(signature, payload)
    except braintree.exceptions.InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid Braintree webhook signature.")


def _handle_webhook(signature: str, payload: str) -> dict:
    notification = _parse_webhook(signature, payload)
    kind = notification.kind
    Kind = braintree.WebhookNotification.Kind
    if kind in (Kind.SubscriptionCanceled, Kind.SubscriptionExpired):
        # A hosted workspace keeps its plan until the paid period ends (if
        # cancelled early), then drops to Starter; a self-hosted buyer's last
        # key just runs out, since no renewal will issue a new one.
        until = _paid_until(notification.subscription) if kind == Kind.SubscriptionCanceled else None
        storage.end_tenant_subscription(notification.subscription.id, until)
        logger.info("Braintree {} for subscription {}", kind, notification.subscription.id)
        return {"status": "ok"}
    if kind not in (Kind.SubscriptionChargedSuccessfully, Kind.SubscriptionWentActive):
        if kind == Kind.Check:
            return {"status": "ok"}  # the Control Panel's "Check URL" test
        # Past due etc.: nothing to do until it's charged or cancelled.
        subscription = getattr(notification, "subscription", None)
        logger.info("Braintree {} for subscription {}", kind, getattr(subscription, "id", None))
        return {"status": "ignored"}

    # Re-read the subscription rather than trusting the payload's snapshot, so
    # paid_through_date reflects the charge that was just made.
    subscription_id = notification.subscription.id
    try:
        result = _fulfil(_get_subscription(subscription_id))
    except HTTPException as exc:
        # 4xx here means the subscription itself is unusable -- acknowledge
        # it so Braintree stops retrying. 5xx/502s propagate and it retries.
        if exc.status_code < 500:
            logger.warning("Braintree webhook {} for {} not fulfilled: {}", kind, subscription_id, exc.detail)
            return {"status": "rejected"}
        raise
    return {"status": result["status"]}
