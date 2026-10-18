"""Stripe billing (services/stripe_billing.py behind routers/billing.py)."""

import json
import time
from types import SimpleNamespace

import pytest
import stripe
from fastapi import HTTPException

from app.routers import billing
from app.services import stripe_billing
from app.services.stripe_billing import BillingError, StripeBilling, subscription_view

PERIOD_END = 1_790_000_000


def _stripe_subscription(sub_id="sub_1", status="active", period_end=PERIOD_END, **extra):
    return {
        "id": sub_id,
        "status": status,
        "metadata": {"tier": "pro", "interval": "monthly"},
        "items": {"data": [{"current_period_end": period_end}]},
        "customer": {"id": "cus_1", "email": "buyer@example.com"},
        "cancel_at_period_end": False,
        **extra,
    }


class FakeStripe:
    """Stands in for the stripe module's resources."""

    def __init__(self):
        self.prices = {}
        self.created_prices = []
        self.created_sessions = []
        self.sessions = {}
        self.subscriptions = {}
        self.modified = []
        self.cancelled = []

    def install(self, monkeypatch):
        monkeypatch.setattr(stripe.Price, "list", self.list_prices)
        monkeypatch.setattr(stripe.Price, "create", self.create_price)
        monkeypatch.setattr(stripe.checkout.Session, "create", self.create_session)
        monkeypatch.setattr(stripe.checkout.Session, "retrieve", self.get_session)
        monkeypatch.setattr(stripe.Subscription, "retrieve", self.get_subscription)
        monkeypatch.setattr(stripe.Subscription, "modify", self.modify)
        monkeypatch.setattr(stripe.Subscription, "cancel", self.cancel)
        monkeypatch.setattr(StripeBilling, "_price_ids", {})

    def list_prices(self, lookup_keys, **kwargs):
        return SimpleNamespace(data=[SimpleNamespace(id=self.prices[k]) for k in lookup_keys if k in self.prices])

    def create_price(self, **params):
        self.created_prices.append(params)
        self.prices[params["lookup_key"]] = f"price_{len(self.prices) + 1}"
        return SimpleNamespace(id=self.prices[params["lookup_key"]])

    def create_session(self, **params):
        self.created_sessions.append(params)
        return {"id": "cs_test_new", "url": "https://checkout.stripe.com/c/pay/cs_test_new"}

    def get_session(self, session_id, **kwargs):
        if session_id not in self.sessions:
            raise stripe.InvalidRequestError("No such checkout session", "id", code="resource_missing")
        return self.sessions[session_id]

    def get_subscription(self, sub_id, **kwargs):
        if sub_id not in self.subscriptions:
            raise stripe.InvalidRequestError("No such subscription", "id", code="resource_missing")
        return self.subscriptions[sub_id]

    def modify(self, sub_id, **params):
        self.modified.append((sub_id, params.get("cancel_at_period_end")))
        return {**self.subscriptions[sub_id], "cancel_at_period_end": True}

    def cancel(self, sub_id, **kwargs):
        self.cancelled.append(sub_id)
        return {**self.subscriptions[sub_id], "status": "canceled"}


@pytest.fixture
def stripe_mode(monkeypatch, tmp_path):
    """Billing on Stripe with a fake Stripe; records every issued key."""
    fake = FakeStripe()
    fake.install(monkeypatch)
    issued = []
    monkeypatch.setattr(billing, "STRIPE_SECRET_KEY", "sk_test_top-secret")
    monkeypatch.setattr(billing, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(billing, "_ISSUED_LICENSES_LOG", tmp_path / "issued.jsonl")
    billing.limiter.reset()

    def fake_issue(email, interval, tier, transaction_id):
        issued.append((transaction_id, email, tier, interval))
        with billing._ISSUED_LICENSES_LOG.open("a") as log:
            log.write(json.dumps({"transaction_id": transaction_id, "license_key": f"key-{len(issued)}"}) + "\n")
        return f"key-{len(issued)}"

    monkeypatch.setattr(billing, "_issue_and_deliver", fake_issue)
    fake.issued = issued
    return fake


def _stripe_webhook(client, monkeypatch, kind, obj):
    monkeypatch.setattr(billing, "_parse_stripe_webhook", lambda payload, signature: {"type": kind, "data": {"object": obj}})
    return client.post("/api/billing/stripe/webhook", content=b"{}", headers={"stripe-signature": "sig"})



def test_config_reports_stripe_checkout(client, stripe_mode):
    body = client.get("/api/billing/config").json()

    assert body["checkout_available"] is True
    assert body["environment"] == "test"
    assert "top-secret" not in json.dumps(body)


def test_checkout_creates_the_price_once_and_returns_stripe_url(client, monkeypatch, stripe_mode):
    monkeypatch.setattr(billing, "APP_BASE_URL", "https://app.example.com")

    first = client.post("/api/billing/checkout", json={"tier": "advanced", "interval": "annual"})
    client.post("/api/billing/checkout", json={"tier": "advanced", "interval": "annual"})

    assert first.json() == {"url": "https://checkout.stripe.com/c/pay/cs_test_new", "session_id": "cs_test_new"}
    assert len(stripe_mode.created_prices) == 1
    price = stripe_mode.created_prices[0]
    assert price["unit_amount"] == 38400
    assert price["recurring"] == {"interval": "year"}
    assert price["lookup_key"] == "crm-scoring-advanced-annual-38400-usd"
    assert price["product_data"] == {"name": "CRM Scoring Advanced"}
    session = stripe_mode.created_sessions[0]
    assert session["success_url"] == "https://app.example.com/?checkout={CHECKOUT_SESSION_ID}"
    assert session["subscription_data"] == {"metadata": {"tier": "advanced", "interval": "annual"}}


def test_return_from_checkout_issues_the_key_once(client, stripe_mode):
    stripe_mode.sessions["cs_test_1"] = {
        "id": "cs_test_1", "mode": "subscription", "status": "complete", "payment_status": "paid", "subscription": "sub_1",
        "customer_details": {"email": "buyer@example.com"},
    }
    stripe_mode.subscriptions["sub_1"] = _stripe_subscription()

    first = client.get("/api/billing/session/cs_test_1").json()
    again = client.get("/api/billing/session/cs_test_1").json()

    assert first["status"] == "ok"
    assert first["email"] == "buyer@example.com"
    assert first["license_key"] == "key-1"
    assert again == first
    assert stripe_mode.issued == [(f"sub_1@{PERIOD_END}", "buyer@example.com", "pro", "monthly")]


def test_unpaid_session_isnt_fulfilled(client, stripe_mode):
    stripe_mode.sessions["cs_test_1"] = {"id": "cs_test_1", "mode": "subscription", "status": "open", "payment_status": "unpaid"}

    assert client.get("/api/billing/session/cs_test_1").status_code == 409
    assert stripe_mode.issued == []


def test_unknown_session_is_404(client, stripe_mode):
    assert client.get("/api/billing/session/cs_test_missing").status_code == 404


def test_cancel_at_period_end_and_immediately(stripe_mode):
    stripe_mode.subscriptions["sub_1"] = _stripe_subscription()

    view = billing.cancel_subscription("sub_1")
    billing.cancel_subscription("sub_1", immediately=True)

    assert view["cancel_at_period_end"] is True
    assert view["current_period_end"] == PERIOD_END
    assert stripe_mode.modified == [("sub_1", True)]
    assert stripe_mode.cancelled == ["sub_1"]


def test_cancel_of_a_subscription_stripe_no_longer_has(stripe_mode):
    assert billing.cancel_subscription("sub_gone") is None


def test_subscription_view_reads_old_and_new_api_shapes():
    old = {"id": "s", "status": "trialing", "items": {"data": []}, "current_period_end": 7, "customer": "cus_1"}
    view = subscription_view(old)

    assert view["status"] == "active"
    assert view["current_period_end"] == 7
    assert view["customer_email"] is None


def test_invoice_subscription_id_reads_old_and_new_api_shapes():
    assert stripe_billing._invoice_subscription_id({"parent": {"subscription_details": {"subscription": "sub_new"}}}) == "sub_new"
    assert stripe_billing._invoice_subscription_id({"subscription": "sub_old"}) == "sub_old"
    assert stripe_billing._invoice_subscription_id({}) is None


def test_webhook_invoice_paid_issues_a_fresh_key_per_period(client, monkeypatch, stripe_mode):
    invoice = {"parent": {"subscription_details": {"subscription": "sub_1"}}}
    stripe_mode.subscriptions["sub_1"] = _stripe_subscription(period_end=PERIOD_END)
    first = _stripe_webhook(client, monkeypatch, "invoice.paid", invoice)
    duplicate = _stripe_webhook(client, monkeypatch, "invoice.paid", invoice)
    stripe_mode.subscriptions["sub_1"] = _stripe_subscription(period_end=PERIOD_END + 2_592_000)
    renewal = _stripe_webhook(client, monkeypatch, "invoice.paid", invoice)

    assert [r.json()["status"] for r in (first, duplicate, renewal)] == ["ok", "duplicate", "ok"]
    assert len(stripe_mode.issued) == 2


def test_webhook_checkout_completed_is_a_fallback(client, monkeypatch, stripe_mode):
    stripe_mode.subscriptions["sub_1"] = _stripe_subscription()

    response = _stripe_webhook(client, monkeypatch, "checkout.session.completed", {"mode": "subscription", "subscription": "sub_1"})

    assert response.json() == {"status": "ok"}


def test_webhook_rejects_an_unusable_subscription(client, monkeypatch, stripe_mode):
    stripe_mode.subscriptions["sub_1"] = _stripe_subscription(status="past_due")

    assert _stripe_webhook(client, monkeypatch, "invoice.paid", {"subscription": "sub_1"}).json() == {"status": "rejected"}


def test_webhook_cancellations_end_the_workspace_plan(client, monkeypatch, stripe_mode):
    ended = []
    monkeypatch.setattr(billing.storage, "end_tenant_subscription", lambda sub_id, until: ended.append((sub_id, until)))

    _stripe_webhook(client, monkeypatch, "customer.subscription.updated", _stripe_subscription(cancel_at_period_end=True))
    _stripe_webhook(client, monkeypatch, "customer.subscription.deleted", _stripe_subscription(status="canceled"))

    assert ended == [("sub_1", PERIOD_END), ("sub_1", None)]


def test_webhook_ignores_other_events(client, monkeypatch, stripe_mode):
    assert _stripe_webhook(client, monkeypatch, "invoice.payment_failed", {}).json() == {"status": "ignored"}


def test_webhook_requires_signature_header(client, stripe_mode):
    assert client.post("/api/billing/stripe/webhook", content=b"{}").status_code == 400


def test_webhook_signature_is_checked_by_stripe(monkeypatch, stripe_mode):
    payload = json.dumps({"id": "evt_1", "object": "event", "type": "invoice.paid", "data": {"object": {}}})
    timestamp = int(time.time())
    signature = stripe.WebhookSignature._compute_signature(f"{timestamp}.{payload}", "whsec_test")

    assert billing._parse_stripe_webhook(payload.encode(), f"t={timestamp},v1={signature}")["type"] == "invoice.paid"
    with pytest.raises(HTTPException) as exc:
        billing._parse_stripe_webhook(payload.encode(), f"t={timestamp},v1=forged")
    assert exc.value.status_code == 400


def test_stripe_errors_become_billing_errors(monkeypatch):
    def boom(*args, **kwargs):
        raise stripe.APIConnectionError("network down")

    monkeypatch.setattr(stripe.Subscription, "retrieve", boom)

    with pytest.raises(BillingError) as exc:
        StripeBilling("sk_test_x").get_subscription("sub_1")
    assert exc.value.status == 502
