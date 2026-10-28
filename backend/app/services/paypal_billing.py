"""The PayPal calls behind routers/billing.py (PayPal Subscriptions API).

Buyers approve a subscription on PayPal's own page and PayPal bills them
every month or year. Like services/stripe_billing.py, this hands back
subscriptions as plain dicts in the shape billing.py works with and raises
BillingError on failure (404 if PayPal doesn't have it).

The CRM Scoring product and its four plans are created in the PayPal
account the first time each plan is sold and found again by name, so
nothing needs setting up in the PayPal dashboard. A subscription carries
"tier|interval|tenant_id" in its custom_id, the way Stripe ones carry
metadata.
"""

import threading
import time
from datetime import datetime

import requests

from .stripe_billing import BillingError

_BASE = {"live": "https://api-m.paypal.com", "sandbox": "https://api-m.sandbox.paypal.com"}
_UNITS = {"month": "MONTH", "year": "YEAR"}
PRODUCT_NAME = "CRM Scoring"
# PayPal's own checkout pages come in Russian; Armenian isn't offered, so
# Armenian visitors get PayPal's default for their country.
_LOCALES = {"ru": "ru-RU", "en": "en-US"}


def _epoch(iso: str | None) -> int | None:
    if not iso:
        return None
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _metadata(custom_id: str | None) -> dict:
    tier, interval, tenant_id = ((custom_id or "") + "||").split("|")[:3]
    metadata = {"tier": tier, "interval": interval}
    if tenant_id:
        metadata["tenant_id"] = tenant_id
    return metadata


def subscription_view(subscription: dict) -> dict:
    """A PayPal subscription in the shape billing.py uses."""
    status = (subscription.get("status") or "").upper()
    return {
        "id": subscription["id"],
        "object": "subscription",
        "status": "active" if status == "ACTIVE" else status.lower(),
        "customer_email": (subscription.get("subscriber") or {}).get("email_address"),
        "metadata": _metadata(subscription.get("custom_id")),
        # PayPal moves next_billing_time forward with every payment, so it
        # marks the end of the period that's been paid for.
        "current_period_end": _epoch((subscription.get("billing_info") or {}).get("next_billing_time")),
        "cancel_at_period_end": status == "CANCELLED",
    }


class PayPalBilling:
    _token: tuple[str, float] | None = None
    _plan_ids: dict[str, str] = {}
    _lock = threading.Lock()

    def __init__(self, client_id: str, secret: str, mode: str = "live"):
        self.client_id = client_id
        self.secret = secret
        self.base = _BASE["sandbox" if mode == "sandbox" else "live"]

    # --- HTTP ---

    def _access_token(self) -> str:
        with self._lock:
            cached = PayPalBilling._token
            if cached and cached[1] > time.time() + 60:
                return cached[0]
            try:
                resp = requests.post(
                    f"{self.base}/v1/oauth2/token",
                    auth=(self.client_id, self.secret),
                    data={"grant_type": "client_credentials"},
                    timeout=20,
                )
            except requests.RequestException as exc:
                raise BillingError(502, f"Couldn't reach PayPal: {exc!r}") from exc
            if resp.status_code != 200:
                raise BillingError(502, f"PayPal rejected the API keys ({resp.status_code}).")
            body = resp.json()
            PayPalBilling._token = (body["access_token"], time.time() + int(body.get("expires_in", 300)))
            return body["access_token"]

    def _req(self, method: str, path: str, **kwargs) -> dict:
        headers = {"Authorization": f"Bearer {self._access_token()}", "Content-Type": "application/json"}
        try:
            resp = requests.request(method, f"{self.base}{path}", headers=headers, timeout=20, **kwargs)
        except requests.RequestException as exc:
            raise BillingError(502, f"Couldn't reach PayPal: {exc!r}") from exc
        if resp.status_code == 404:
            raise BillingError(404, "Not found at PayPal.")
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("message") or resp.text
            except ValueError:
                detail = resp.text
            raise BillingError(400 if resp.status_code < 500 else 502, f"PayPal: {detail}")
        return resp.json() if resp.content else {}

    # --- Product and plans ---

    def _product_id(self) -> str:
        found = self._req("GET", "/v1/catalogs/products", params={"page_size": 20}).get("products") or []
        for product in found:
            if product.get("name") == PRODUCT_NAME:
                return product["id"]
        return self._req(
            "POST", "/v1/catalogs/products", json={"name": PRODUCT_NAME, "type": "SERVICE", "category": "SOFTWARE"}
        )["id"]

    def _plan_id(self, name: str, amount_cents: int, currency: str, interval: str) -> str:
        """The PayPal plan for this price, created the first time it's sold.
        The amount is part of the name: a new price gets a new plan, existing
        subscribers stay on theirs."""
        key = f"{name} — {amount_cents / 100:.2f} {currency.upper()}"
        with self._lock:
            if key in PayPalBilling._plan_ids:
                return PayPalBilling._plan_ids[key]
        product_id = self._product_id()
        plans = self._req("GET", "/v1/billing/plans", params={"product_id": product_id, "page_size": 20}).get("plans") or []
        plan_id = next((p["id"] for p in plans if p.get("name") == key and p.get("status") == "ACTIVE"), None)
        if plan_id is None:
            plan_id = self._req(
                "POST",
                "/v1/billing/plans",
                json={
                    "product_id": product_id,
                    "name": key,
                    "status": "ACTIVE",
                    "billing_cycles": [
                        {
                            "frequency": {"interval_unit": _UNITS[interval], "interval_count": 1},
                            "tenure_type": "REGULAR",
                            "sequence": 1,
                            "total_cycles": 0,
                            "pricing_scheme": {
                                "fixed_price": {"value": f"{amount_cents / 100:.2f}", "currency_code": currency.upper()}
                            },
                        }
                    ],
                    "payment_preferences": {
                        "auto_bill_outstanding": True,
                        "setup_fee_failure_action": "CANCEL",
                        "payment_failure_threshold": 3,
                    },
                },
            )["id"]
        with self._lock:
            PayPalBilling._plan_ids[key] = plan_id
        return plan_id

    # --- Subscriptions ---

    def create_subscription(
        self,
        *,
        amount: int,
        description: str,
        currency: str,
        interval: str,
        metadata: dict,
        return_url: str,
        cancel_url: str,
        customer_email: str | None = None,
        lang: str = "en",
    ) -> dict:
        """Starts a subscription; returns its id and PayPal's approval page URL."""
        if interval not in _UNITS:
            raise BillingError(400, "Only monthly or yearly subscriptions are sold through PayPal.")
        body = {
            "plan_id": self._plan_id(description, amount, currency, interval),
            "custom_id": "|".join([metadata.get("tier", ""), metadata.get("interval", ""), metadata.get("tenant_id", "")]),
            "application_context": {
                "brand_name": "CRM Scoring",
                "user_action": "SUBSCRIBE_NOW",
                "shipping_preference": "NO_SHIPPING",
                "return_url": return_url,
                "cancel_url": cancel_url,
            },
        }
        if lang in _LOCALES:
            body["application_context"]["locale"] = _LOCALES[lang]
        if customer_email:
            body["subscriber"] = {"email_address": customer_email}
        created = self._req("POST", "/v1/billing/subscriptions", json=body)
        approve = next((link["href"] for link in created.get("links", []) if link.get("rel") == "approve"), None)
        if not approve:
            raise BillingError(502, "PayPal didn't return an approval link.")
        return {"id": created["id"], "url": approve}

    def get_subscription(self, sub_id: str) -> dict:
        return subscription_view(self._req("GET", f"/v1/billing/subscriptions/{sub_id}"))

    def cancel_subscription(self, sub_id: str, at_period_end: bool = True) -> dict:
        """PayPal cancels right away and stops future payments; the period
        already paid for keeps its end date, which billing.py honours."""
        view = self.get_subscription(sub_id)
        if view["status"] not in ("cancelled", "expired"):
            self._req("POST", f"/v1/billing/subscriptions/{sub_id}/cancel", json={"reason": "Cancelled by the customer"})
        return {**view, "status": "cancelled" if not at_period_end else view["status"], "cancel_at_period_end": True}

    # --- Webhooks ---

    def verify_webhook(self, headers: dict, event: dict, webhook_id: str) -> bool:
        result = self._req(
            "POST",
            "/v1/notifications/verify-webhook-signature",
            json={
                "auth_algo": headers.get("paypal-auth-algo"),
                "cert_url": headers.get("paypal-cert-url"),
                "transmission_id": headers.get("paypal-transmission-id"),
                "transmission_sig": headers.get("paypal-transmission-sig"),
                "transmission_time": headers.get("paypal-transmission-time"),
                "webhook_id": webhook_id,
                "webhook_event": event,
            },
        )
        return result.get("verification_status") == "SUCCESS"

    def translate_event(self, event: dict) -> dict | None:
        """A PayPal event as the event routers/billing.py handles, or None if
        it needs no action."""
        kind = event.get("event_type")
        resource = event.get("resource") or {}
        if kind in ("BILLING.SUBSCRIPTION.ACTIVATED", "PAYMENT.SALE.COMPLETED"):
            sub_id = resource.get("id") if kind.startswith("BILLING.") else resource.get("billing_agreement_id")
            if not sub_id:
                return None
            subscription = self.get_subscription(sub_id)
            return {"type": "payment.succeeded", "data": {"object": {"subscription_id": sub_id, "subscription": subscription}}}
        if kind == "BILLING.SUBSCRIPTION.CANCELLED":
            view = subscription_view(resource)
            # Keeps the plan to the end of the paid period when PayPal still
            # reports one; otherwise it ends now.
            if view["current_period_end"]:
                return {"type": "subscription.updated", "data": {"object": view}}
            return {"type": "subscription.canceled", "data": {"object": view}}
        if kind in ("BILLING.SUBSCRIPTION.EXPIRED", "BILLING.SUBSCRIPTION.SUSPENDED"):
            return {"type": "subscription.canceled", "data": {"object": subscription_view(resource)}}
        return None
