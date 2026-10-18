import json
import time

import pytest
from fastapi import HTTPException

from app.routers import billing
from app.services.stripe_billing import BillingError

PERIOD_END = 1_790_000_000


def _subscription(sub_id="sub_1", tier="pro", interval="monthly", status="active", period_end=PERIOD_END, **extra):
    return {
        "id": sub_id,
        "object": "subscription",
        "status": status,
        "customer_email": "buyer@example.com",
        "metadata": {"tier": tier, "interval": interval},
        "current_period_end": period_end,
        "cancel_at_period_end": False,
        **extra,
    }


def _session(session_id="cs_1", subscription_id="sub_1", **overrides):
    return {"id": session_id, "mode": "subscription", "status": "complete", "subscription_id": subscription_id, **overrides}


class FakeStripe:
    """Stands in for services/stripe_billing.StripeBilling; records what checkout sent."""

    def __init__(self):
        self.created_sessions = []
        self.sessions = {}
        self.subscriptions = {}
        self.cancelled = []

    def create_checkout(self, **params):
        self.created_sessions.append(params)
        return {"id": "cs_new", "url": "https://checkout.stripe.com/c/pay/cs_new"}

    def get_checkout(self, session_id):
        if session_id not in self.sessions:
            raise BillingError(404, "Checkout session not found.")
        return self.sessions[session_id]

    def get_subscription(self, sub_id):
        if sub_id not in self.subscriptions:
            raise BillingError(404, "Subscription not found.")
        return self.subscriptions[sub_id]

    def cancel_subscription(self, sub_id, at_period_end=True):
        if sub_id not in self.subscriptions:
            raise BillingError(404, "Subscription not found.")
        self.cancelled.append((sub_id, at_period_end))
        sub = self.subscriptions[sub_id]
        return {**sub, "cancel_at_period_end": True} if at_period_end else {**sub, "status": "canceled"}


@pytest.fixture
def stripe_stub(monkeypatch, tmp_path):
    """Stub Stripe and license issuing; records every issued transaction id."""
    issued = []
    fake = FakeStripe()
    monkeypatch.setattr(billing, "_ISSUED_LICENSES_LOG", tmp_path / "issued.jsonl")
    monkeypatch.setattr(billing, "STRIPE_SECRET_KEY", "sk_test_top-secret")
    monkeypatch.setattr(billing, "_api", lambda: fake)
    billing.limiter.reset()

    def fake_issue(email, interval, tier, transaction_id):
        issued.append((transaction_id, tier, interval))
        with billing._ISSUED_LICENSES_LOG.open("a") as log:
            log.write(json.dumps({"transaction_id": transaction_id, "license_key": f"key-{len(issued)}"}) + "\n")
        return f"key-{len(issued)}"

    monkeypatch.setattr(billing, "_issue_and_deliver", fake_issue)
    fake.issued = issued
    return fake


def _webhook(client, monkeypatch, kind, obj):
    # The event as services/stripe_billing.py hands it over after translating Stripe's.
    monkeypatch.setattr(billing, "_parse_stripe_webhook", lambda payload, signature: {"type": kind, "data": {"object": obj}})
    monkeypatch.setattr(billing, "_translate", lambda event: event)
    return client.post("/api/billing/stripe/webhook", content=b"{}", headers={"stripe-signature": "sig"})


def _paid(sub):
    return {"object": "payment", "status": "succeeded", "subscription_id": sub["id"], "subscription": sub}


def test_billing_config_shows_prices_but_no_secrets(client, stripe_stub):
    body = client.get("/api/billing/config").json()

    assert body["checkout_available"] is True
    assert body["environment"] == "test"
    assert body["price_monthly"] == "20.00"
    assert "top-secret" not in json.dumps(body)


def test_billing_config_unavailable_without_key(client, monkeypatch):
    monkeypatch.setattr(billing, "STRIPE_SECRET_KEY", "")

    assert client.get("/api/billing/config").json()["checkout_available"] is False


def test_api_requires_key(monkeypatch):
    monkeypatch.setattr(billing, "STRIPE_SECRET_KEY", "")

    with pytest.raises(HTTPException) as exc:
        billing._api()
    assert exc.value.status_code == 503


def test_checkout_from_the_app_returns_to_the_app(client, monkeypatch, stripe_stub):
    monkeypatch.setattr(billing, "APP_BASE_URL", "https://app.example.com/")

    response = client.post("/api/billing/checkout", json={"tier": "advanced", "interval": "annual"})

    assert response.json() == {"url": "https://checkout.stripe.com/c/pay/cs_new", "session_id": "cs_new"}
    params = stripe_stub.created_sessions[0]
    assert params["mode"] == "subscription"
    assert params["interval"] == "year"
    assert params["amount"] == 38400
    assert params["currency"] == "USD"
    assert params["success_url"] == "https://app.example.com/?checkout={CHECKOUT_SESSION_ID}"
    assert params["cancel_url"] == "https://app.example.com/#plans"
    assert params["metadata"] == {"tier": "advanced", "interval": "annual"}


def test_checkout_from_the_website_returns_to_its_thank_you_page(client, monkeypatch, stripe_stub):
    monkeypatch.setattr(billing, "STOREFRONT_URL", "https://crmscoring.com")

    client.post("/api/billing/checkout", json={"tier": "pro", "interval": "monthly", "source": "site"})

    params = stripe_stub.created_sessions[0]
    assert params["success_url"] == "https://crmscoring.com/thank-you.html?session_id={CHECKOUT_SESSION_ID}"
    assert params["cancel_url"] == "https://crmscoring.com/#pricing"
    assert params["amount"] == 2000 and params["interval"] == "month"


def test_checkout_rejects_unknown_plan(client, stripe_stub):
    assert client.post("/api/billing/checkout", json={"tier": "gold", "interval": "monthly"}).status_code == 422


def test_checkout_when_stripe_is_down(client, stripe_stub, monkeypatch):
    def down(**params):
        raise BillingError(502, "Couldn't reach Stripe")

    monkeypatch.setattr(stripe_stub, "create_checkout", down)

    assert client.post("/api/billing/checkout", json={"interval": "monthly"}).status_code == 502


def test_session_returns_the_license_and_a_reload_shows_the_same_key(client, stripe_stub):
    stripe_stub.sessions["cs_1"] = _session()
    stripe_stub.subscriptions["sub_1"] = _subscription()

    first = client.get("/api/billing/session/cs_1").json()
    again = client.get("/api/billing/session/cs_1").json()

    assert first == {
        "status": "ok",
        "email": "buyer@example.com",
        "tier": "pro",
        "plan": "monthly",
        "license_key": "key-1",
        "workspace_upgraded": False,
    }
    assert again == first
    assert stripe_stub.issued == [(f"sub_1@{PERIOD_END}", "pro", "monthly")]


def test_session_must_be_paid(client, stripe_stub):
    stripe_stub.sessions["cs_1"] = _session(status="open", subscription_id=None)

    response = client.get("/api/billing/session/cs_1")

    assert response.status_code == 409
    assert stripe_stub.issued == []


def test_session_not_found(client, stripe_stub):
    assert client.get("/api/billing/session/cs_missing").status_code == 404


def test_session_id_must_look_like_one(client, stripe_stub):
    assert client.get("/api/billing/session/not-a-session").status_code == 422


def test_issue_and_deliver_only_emails_real_addresses(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(billing, "_ISSUED_LICENSES_LOG", tmp_path / "issued.jsonl")
    monkeypatch.setattr(billing, "LICENSE_PRIVATE_KEY", "unused")
    monkeypatch.setattr(billing, "issue_license", lambda email, **kw: f"key-for-{email}")
    monkeypatch.setattr(billing, "send_license_email", lambda email, key, interval: sent.append(email) or True)

    billing._issue_and_deliver("Stripe subscription sub_1", "monthly", "pro", "sub_1@a")
    billing._issue_and_deliver("jane@example.com", "monthly", "pro", "sub_1@b")

    assert sent == ["jane@example.com"]
    assert "key-for-Stripe subscription sub_1" in (tmp_path / "issued.jsonl").read_text()


def test_licensee_falls_back_to_the_subscription_id():
    assert billing._licensee(_subscription(customer_email=None)) == "Stripe subscription sub_1"


def test_fulfil_rejects_unknown_plan(stripe_stub):
    with pytest.raises(HTTPException) as exc:
        billing._fulfil(_subscription(tier="gold"))
    assert exc.value.status_code == 400
    assert stripe_stub.issued == []


def test_fulfil_waits_for_active_status(stripe_stub):
    with pytest.raises(HTTPException) as exc:
        billing._fulfil(_subscription(status="past_due"))
    assert exc.value.status_code == 409


def test_return_from_checkout_then_first_payment_webhook_issue_one_key(client, monkeypatch, stripe_stub):
    stripe_stub.sessions["cs_1"] = _session()
    stripe_stub.subscriptions["sub_1"] = _subscription()

    returned = client.get("/api/billing/session/cs_1")
    paid = _webhook(client, monkeypatch, "payment.succeeded", _paid(_subscription()))

    assert returned.json()["status"] == "ok"
    assert paid.json() == {"status": "duplicate"}
    assert len(stripe_stub.issued) == 1


def test_webhook_payment_is_a_fallback_if_the_buyer_never_returns(client, monkeypatch, stripe_stub):
    response = _webhook(client, monkeypatch, "payment.succeeded", _paid(_subscription()))

    assert response.json() == {"status": "ok"}
    assert len(stripe_stub.issued) == 1


def test_webhook_renewal_issues_a_fresh_key(client, monkeypatch, stripe_stub):
    _webhook(client, monkeypatch, "payment.succeeded", _paid(_subscription(period_end=PERIOD_END)))
    renewal = _webhook(client, monkeypatch, "payment.succeeded", _paid(_subscription(period_end=PERIOD_END + 2_592_000)))

    assert renewal.json() == {"status": "ok"}
    assert [tx for tx, _, _ in stripe_stub.issued] == [f"sub_1@{PERIOD_END}", f"sub_1@{PERIOD_END + 2_592_000}"]


def test_webhook_acknowledges_unusable_subscription(client, monkeypatch, stripe_stub):
    response = _webhook(client, monkeypatch, "payment.succeeded", _paid(_subscription(tier="gold")))

    assert response.json() == {"status": "rejected"}
    assert stripe_stub.issued == []


def test_webhook_ignores_other_events(client, monkeypatch, stripe_stub):
    failed = _webhook(client, monkeypatch, "payment.failed", _paid(_subscription()))
    one_off = _webhook(client, monkeypatch, "payment.succeeded", {"object": "payment", "subscription": None})

    assert failed.json() == {"status": "ignored"}
    assert one_off.json() == {"status": "ignored"}
    assert stripe_stub.issued == []



def test_webhook_requires_signature_header(client, stripe_stub):
    assert client.post("/api/billing/stripe/webhook", content=b"{}").status_code == 400




def test_cancel_stops_renewal_at_period_end(stripe_stub):
    stripe_stub.subscriptions["sub_1"] = _subscription()

    billing.cancel_subscription("sub_1")

    assert stripe_stub.cancelled == [("sub_1", True)]


def test_cancel_immediately(stripe_stub):
    stripe_stub.subscriptions["sub_1"] = _subscription()

    billing.cancel_subscription("sub_1", immediately=True)

    assert stripe_stub.cancelled == [("sub_1", False)]


def test_cancel_of_a_subscription_stripe_no_longer_has(stripe_stub):
    assert billing.cancel_subscription("sub_gone") is None


def test_cancel_raises_if_stripe_is_down(stripe_stub, monkeypatch):
    def down(sub_id, at_period_end=True):
        raise BillingError(500, "boom")

    monkeypatch.setattr(stripe_stub, "cancel_subscription", down)

    with pytest.raises(HTTPException) as exc:
        billing.cancel_subscription("sub_1")
    assert exc.value.status_code == 502
