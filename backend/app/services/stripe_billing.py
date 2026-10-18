"""The Stripe calls behind routers/billing.py.

Returns checkout sessions and subscriptions as plain dicts in the shape
billing.py works with, and raises BillingError on failure (404 if Stripe
doesn't have it).

Buyers pay on Stripe Checkout's hosted page. Prices are created the first
time a plan is sold and found again by a lookup key that includes the
amount, so nothing needs setting up in the Stripe Dashboard.
"""

import threading

import stripe



class BillingError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


_STRIPE_INTERVALS = {"month": "month", "year": "year"}
# Stripe states in which a subscription grants its plan and earns keys.
_ACTIVE = ("active", "trialing")
# States that mean it's over (no plan, no more keys).
_ENDED = ("canceled", "unpaid", "incomplete_expired")


def _period_end(subscription) -> int | None:
    """End of the current paid period, as epoch seconds. Newer Stripe API
    versions keep it on the subscription item, older ones on the subscription."""
    for item in (subscription.get("items") or {}).get("data") or []:
        if item.get("current_period_end"):
            return int(item["current_period_end"])
    end = subscription.get("current_period_end")
    return int(end) if end else None


def subscription_view(subscription) -> dict:
    """A Stripe subscription in the shape billing.py uses."""
    customer = subscription.get("customer")
    status = subscription.get("status")
    return {
        "id": subscription["id"],
        "object": "subscription",
        "status": "active" if status in _ACTIVE else status,
        "customer_email": customer.get("email") if isinstance(customer, dict) else None,
        "metadata": dict(subscription.get("metadata") or {}),
        "current_period_end": _period_end(subscription),
        "cancel_at_period_end": bool(subscription.get("cancel_at_period_end")),
    }


def _invoice_subscription_id(invoice) -> str | None:
    # API 2025-03-31 and later: invoice.parent.subscription_details.subscription;
    # earlier versions: invoice.subscription.
    details = (invoice.get("parent") or {}).get("subscription_details") or {}
    subscription = details.get("subscription") or invoice.get("subscription")
    return subscription if isinstance(subscription, str) else (subscription or {}).get("id")


class StripeBilling:
    _price_ids: dict[str, str] = {}
    _price_lock = threading.Lock()

    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    def _call(self, fn, *args, **kwargs):
        stripe.api_key = self.secret_key
        try:
            return fn(*args, **kwargs)
        except stripe.InvalidRequestError as exc:
            raise BillingError(404 if exc.code == "resource_missing" else 400, exc.user_message or str(exc)) from exc
        except stripe.StripeError as exc:
            raise BillingError(502, exc.user_message or str(exc)) from exc

    def _price_id(self, amount: int, currency: str, interval: str, name: str, metadata: dict) -> str:
        """The Stripe price for a plan, created the first time it's sold."""
        key = f"crm-scoring-{metadata.get('tier', 'plan')}-{metadata.get('interval', interval)}-{amount}-{currency.lower()}"
        with self._price_lock:
            if key not in self._price_ids:
                found = self._call(stripe.Price.list, lookup_keys=[key], active=True, limit=1).data
                if found:
                    self._price_ids[key] = found[0].id
                else:
                    self._price_ids[key] = self._call(
                        stripe.Price.create,
                        currency=currency.lower(),
                        unit_amount=amount,
                        recurring={"interval": _STRIPE_INTERVALS[interval]},
                        lookup_key=key,
                        product_data={"name": name},
                        metadata={k: v for k, v in metadata.items() if k in ("tier", "interval")},
                    ).id
            return self._price_ids[key]

    # --- Checkout and subscriptions ---

    def create_checkout(
        self,
        *,
        amount: int,
        description: str,
        success_url: str,
        cancel_url: str,
        currency: str = "USD",
        mode: str = "subscription",
        interval: str | None = None,
        customer_email: str | None = None,
        metadata: dict[str, str] | None = None,
            ) -> dict:
        if mode != "subscription" or interval not in _STRIPE_INTERVALS:
            raise BillingError(400, "Only monthly or yearly subscriptions are sold through Stripe.")
        metadata = metadata or {}
        name = description.split(" (")[0]
        params = {
            "mode": "subscription",
            "line_items": [{"price": self._price_id(amount, currency, interval, name, metadata), "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": metadata,
            "subscription_data": {"metadata": metadata},
        }
        if customer_email:
            params["customer_email"] = customer_email
        session = self._call(stripe.checkout.Session.create, **params)
        return {"id": session["id"], "url": session["url"]}

    def get_checkout(self, session_id: str) -> dict:
        session = self._call(stripe.checkout.Session.retrieve, session_id)
        paid = session.get("status") == "complete" and session.get("payment_status") in ("paid", "no_payment_required")
        subscription = session.get("subscription")
        return {
            "id": session["id"],
            "mode": session.get("mode"),
            "status": "complete" if paid else session.get("status"),
            "subscription_id": subscription if isinstance(subscription, str) else (subscription or {}).get("id"),
            "customer_email": (session.get("customer_details") or {}).get("email"),
        }

    def get_subscription(self, sub_id: str) -> dict:
        return subscription_view(self._call(stripe.Subscription.retrieve, sub_id, expand=["customer"]))

    def cancel_subscription(self, sub_id: str, at_period_end: bool = True) -> dict:
        subscription = self._call(stripe.Subscription.retrieve, sub_id, expand=["customer"])
        if subscription.get("status") not in _ENDED:
            if not at_period_end:
                subscription = self._call(stripe.Subscription.cancel, sub_id, expand=["customer"])
            elif not subscription.get("cancel_at_period_end"):
                subscription = self._call(stripe.Subscription.modify, sub_id, cancel_at_period_end=True, expand=["customer"])
        return subscription_view(subscription)

    # --- Webhooks ---

    @staticmethod
    def parse_webhook(payload: bytes, signature: str, secret: str):
        """The verified Stripe event; raises ValueError or
        stripe.SignatureVerificationError if it's forged or malformed."""
        return stripe.Webhook.construct_event(payload, signature, secret)

    def translate_event(self, event) -> dict | None:
        """A Stripe event as the event routers/billing.py handles
        (payment.succeeded, subscription.updated, subscription.canceled), or
        None if it needs no action."""
        kind = event["type"]
        obj = event["data"]["object"]
        if kind == "customer.subscription.deleted":
            return {"type": "subscription.canceled", "data": {"object": subscription_view(obj)}}
        if kind == "customer.subscription.updated":
            view = subscription_view(obj)
            ended = obj.get("status") in _ENDED
            return {"type": "subscription.canceled" if ended else "subscription.updated", "data": {"object": view}}

        if kind == "invoice.paid":
            sub_id = _invoice_subscription_id(obj)
        elif kind == "checkout.session.completed" and obj.get("mode") == "subscription":
            subscription = obj.get("subscription")
            sub_id = subscription if isinstance(subscription, str) else (subscription or {}).get("id")
        else:
            return None
        if not sub_id:
            return None
        # Re-read the subscription so its period reflects the payment just made.
        subscription = self.get_subscription(sub_id)
        return {"type": "payment.succeeded", "data": {"object": {"subscription_id": sub_id, "subscription": subscription}}}
