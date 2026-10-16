import json
import time
from types import SimpleNamespace

import pytest
import stripe
from fastapi import HTTPException

from app.routers import billing

PERIOD_END = 1_790_000_000


def _subscription(sub_id="sub1", tier="pro", interval="monthly", status="active", period_end=PERIOD_END, **extra):
    return {
        "id": sub_id,
        "status": status,
        "metadata": {"tier": tier, "interval": interval},
        "items": {"data": [{"current_period_end": period_end}]},
        "customer": {"id": "cus_1", "email": "buyer@example.com"},
        **extra,
    }


def _session(session_id="cs_test_1", subscription=None, **overrides):
    return {
        "id": session_id,
        "mode": "subscription",
        "status": "complete",
        "payment_status": "paid",
        "customer_details": {"email": "buyer@example.com"},
        "subscription": subscription if subscription is not None else _subscription(),
        **overrides,
    }


class FakeStripe:
    """Stands in for the stripe module; records what checkout sent."""

    def __init__(self):
        self.prices = {}  # lookup key -> price id
        self.created_prices = []
        self.created_sessions = []
        self.sessions = {}
        self.subscriptions = {}
        self.modified = []
        self.cancelled = []
        self.checkout = SimpleNamespace(Session=SimpleNamespace(create=self._create_session, retrieve=self._get_session))
        self.Price = SimpleNamespace(list=self._list_prices, create=self._create_price)
        self.Subscription = SimpleNamespace(retrieve=self._get_subscription, modify=self._modify, cancel=self._cancel)

    def _list_prices(self, lookup_keys, **kwargs):
        return SimpleNamespace(data=[SimpleNamespace(id=self.prices[k]) for k in lookup_keys if k in self.prices])

    def _create_price(self, **params):
        self.created_prices.append(params)
        self.prices[params["lookup_key"]] = f"price_{len(self.prices) + 1}"
        return SimpleNamespace(id=self.prices[params["lookup_key"]])

    def _create_session(self, **params):
        self.created_sessions.append(params)
        return {"id": "cs_test_new", "url": "https://checkout.stripe.com/c/pay/cs_test_new"}

    def _get_session(self, session_id, expand=None):
        if session_id not in self.sessions:
            raise stripe.InvalidRequestError("No such checkout session", "id", code="resource_missing")
        return self.sessions[session_id]

    def _get_subscription(self, subscription_id, expand=None):
        if subscription_id not in self.subscriptions:
            raise stripe.InvalidRequestError("No such subscription", "id", code="resource_missing")
        return self.subscriptions[subscription_id]

    def _modify(self, subscription_id, **params):
        self.modified.append((subscription_id, params))
        return {**self.subscriptions[subscription_id], **params}

    def _cancel(self, subscription_id):
        self.cancelled.append(subscription_id)
        return {**self.subscriptions[subscription_id], "status": "canceled"}


@pytest.fixture
def stripe_stub(monkeypatch, tmp_path):
    """Stub Stripe and license issuing; records every issued transaction id."""
    issued = []
    fake = FakeStripe()
    monkeypatch.setattr(billing, "_ISSUED_LICENSES_LOG", tmp_path / "issued.jsonl")
    monkeypatch.setattr(billing, "STRIPE_SECRET_KEY", "sk_test_top-secret")
    monkeypatch.setattr(billing, "_api", lambda: fake)
    monkeypatch.setattr(billing, "_price_ids", {})
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
    monkeypatch.setattr(billing, "_parse_webhook", lambda payload, signature: {"type": kind, "data": {"object": obj}})
    return client.post("/api/billing/stripe/webhook", content=b"{}", headers={"stripe-signature": "sig"})


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

    response = client.post("/api/billing/stripe/checkout", json={"tier": "advanced", "interval": "annual"})

    assert response.json() == {"url": "https://checkout.stripe.com/c/pay/cs_test_new", "session_id": "cs_test_new"}
    params = stripe_stub.created_sessions[0]
    assert params["mode"] == "subscription"
    assert params["success_url"] == "https://app.example.com/?checkout={CHECKOUT_SESSION_ID}"
    assert params["cancel_url"] == "https://app.example.com/#plans"
    assert params["subscription_data"] == {"metadata": {"tier": "advanced", "interval": "annual"}}
    assert stripe_stub.created_prices[0]["unit_amount"] == 38400
    assert stripe_stub.created_prices[0]["recurring"] == {"interval": "year"}


def test_checkout_from_the_website_returns_to_its_thank_you_page(client, monkeypatch, stripe_stub):
    monkeypatch.setattr(billing, "STOREFRONT_URL", "https://crmscoring.com")

    client.post("/api/billing/stripe/checkout", json={"tier": "pro", "interval": "monthly", "source": "site"})

    params = stripe_stub.created_sessions[0]
    assert params["success_url"] == "https://crmscoring.com/thank-you.html?session_id={CHECKOUT_SESSION_ID}"
    assert params["cancel_url"] == "https://crmscoring.com/#pricing"


def test_prices_are_created_once_then_reused(client, monkeypatch, stripe_stub):
    client.post("/api/billing/stripe/checkout", json={"interval": "monthly"})
    monkeypatch.setattr(billing, "_price_ids", {})  # e.g. after a restart: found again by lookup key
    client.post("/api/billing/stripe/checkout", json={"interval": "monthly"})

    assert len(stripe_stub.created_prices) == 1
    assert stripe_stub.created_prices[0]["lookup_key"] == "crm-scoring-pro-monthly-2000-usd"
    assert [s["line_items"][0]["price"] for s in stripe_stub.created_sessions] == ["price_1", "price_1"]


def test_checkout_rejects_unknown_plan(client, stripe_stub):
    assert client.post("/api/billing/stripe/checkout", json={"tier": "gold", "interval": "monthly"}).status_code == 422


def test_session_returns_the_license_and_a_reload_shows_the_same_key(client, stripe_stub):
    stripe_stub.sessions["cs_test_1"] = _session()

    first = client.get("/api/billing/stripe/session/cs_test_1").json()
    again = client.get("/api/billing/stripe/session/cs_test_1").json()

    assert first == {
        "status": "ok",
        "email": "buyer@example.com",
        "tier": "pro",
        "plan": "monthly",
        "license_key": "key-1",
        "workspace_upgraded": False,
    }
    assert again == first
    assert stripe_stub.issued == [(f"sub1@{PERIOD_END}", "pro", "monthly")]


def test_session_must_be_paid(client, stripe_stub):
    stripe_stub.sessions["cs_test_1"] = _session(status="open", payment_status="unpaid")

    response = client.get("/api/billing/stripe/session/cs_test_1")

    assert response.status_code == 409
    assert stripe_stub.issued == []


def test_session_not_found(client, stripe_stub):
    assert client.get("/api/billing/stripe/session/cs_test_missing").status_code == 404


def test_session_id_must_look_like_one(client, stripe_stub):
    assert client.get("/api/billing/stripe/session/not-a-session").status_code == 422


def test_issue_and_deliver_only_emails_real_addresses(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(billing, "_ISSUED_LICENSES_LOG", tmp_path / "issued.jsonl")
    monkeypatch.setattr(billing, "LICENSE_PRIVATE_KEY", "unused")
    monkeypatch.setattr(billing, "issue_license", lambda email, **kw: f"key-for-{email}")
    monkeypatch.setattr(billing, "send_license_email", lambda email, key, interval: sent.append(email) or True)

    billing._issue_and_deliver("Stripe customer cus_1", "monthly", "pro", "sub1@a")
    billing._issue_and_deliver("jane@example.com", "monthly", "pro", "sub1@b")

    assert sent == ["jane@example.com"]
    assert "key-for-Stripe customer cus_1" in (tmp_path / "issued.jsonl").read_text()


def test_fulfil_rejects_unknown_plan(stripe_stub):
    with pytest.raises(HTTPException) as exc:
        billing._fulfil(_subscription(tier="gold"), "buyer@example.com")
    assert exc.value.status_code == 400
    assert stripe_stub.issued == []


def test_fulfil_waits_for_active_status(stripe_stub):
    with pytest.raises(HTTPException) as exc:
        billing._fulfil(_subscription(status="incomplete"), "buyer@example.com")
    assert exc.value.status_code == 409


def test_period_end_reads_old_and_new_api_shapes():
    assert billing._period_end({"items": {"data": [{"current_period_end": 5}]}}) == 5
    assert billing._period_end({"items": {"data": []}, "current_period_end": 7}) == 7


def test_invoice_subscription_id_reads_old_and_new_api_shapes():
    assert billing._invoice_subscription_id({"parent": {"subscription_details": {"subscription": "sub_new"}}}) == "sub_new"
    assert billing._invoice_subscription_id({"subscription": "sub_old"}) == "sub_old"
    assert billing._invoice_subscription_id({}) is None


def test_return_from_checkout_then_first_invoice_webhook_issue_one_key(client, monkeypatch, stripe_stub):
    stripe_stub.sessions["cs_test_1"] = _session()
    stripe_stub.subscriptions["sub1"] = _subscription()

    returned = client.get("/api/billing/stripe/session/cs_test_1")
    paid = _webhook(client, monkeypatch, "invoice.paid", {"subscription": "sub1", "customer_email": "buyer@example.com"})

    assert returned.json()["status"] == "ok"
    assert paid.json() == {"status": "duplicate"}
    assert len(stripe_stub.issued) == 1


def test_webhook_checkout_completed_is_a_fallback(client, monkeypatch, stripe_stub):
    stripe_stub.sessions["cs_test_1"] = _session()

    response = _webhook(client, monkeypatch, "checkout.session.completed", {"id": "cs_test_1", "mode": "subscription"})

    assert response.json() == {"status": "ok"}
    assert len(stripe_stub.issued) == 1


def test_webhook_renewal_issues_a_fresh_key(client, monkeypatch, stripe_stub):
    invoice = {"parent": {"subscription_details": {"subscription": "sub1"}}, "customer_email": "buyer@example.com"}
    stripe_stub.subscriptions["sub1"] = _subscription(period_end=PERIOD_END)
    _webhook(client, monkeypatch, "invoice.paid", invoice)
    stripe_stub.subscriptions["sub1"] = _subscription(period_end=PERIOD_END + 2_592_000)
    renewal = _webhook(client, monkeypatch, "invoice.paid", invoice)

    assert renewal.json() == {"status": "ok"}
    assert [tx for tx, _, _ in stripe_stub.issued] == [f"sub1@{PERIOD_END}", f"sub1@{PERIOD_END + 2_592_000}"]


def test_webhook_acknowledges_unusable_subscription(client, monkeypatch, stripe_stub):
    stripe_stub.subscriptions["sub1"] = _subscription(status="past_due")

    response = _webhook(client, monkeypatch, "invoice.paid", {"subscription": "sub1"})

    assert response.json() == {"status": "rejected"}
    assert stripe_stub.issued == []


def test_webhook_ignores_other_events(client, monkeypatch, stripe_stub):
    response = _webhook(client, monkeypatch, "invoice.payment_failed", {"subscription": "sub1"})

    assert response.json() == {"status": "ignored"}
    assert stripe_stub.issued == []


def test_webhook_requires_signature_header(client, stripe_stub):
    assert client.post("/api/billing/stripe/webhook", content=b"{}").status_code == 400


def test_webhook_unavailable_without_secret(monkeypatch):
    monkeypatch.setattr(billing, "STRIPE_WEBHOOK_SECRET", "")

    with pytest.raises(HTTPException) as exc:
        billing._parse_webhook(b"{}", "t=1,v1=abc")
    assert exc.value.status_code == 503


def test_webhook_signature_is_checked_by_stripe(monkeypatch):
    """The real parser accepts a correctly signed event and rejects a forged one."""
    secret = "whsec_test"
    monkeypatch.setattr(billing, "STRIPE_WEBHOOK_SECRET", secret)
    payload = json.dumps({"id": "evt_1", "object": "event", "type": "invoice.paid", "data": {"object": {}}})
    timestamp = int(time.time())
    signature = stripe.WebhookSignature._compute_signature(f"{timestamp}.{payload}", secret)

    event = billing._parse_webhook(payload.encode(), f"t={timestamp},v1={signature}")
    assert event["type"] == "invoice.paid"

    with pytest.raises(HTTPException) as exc:
        billing._parse_webhook(payload.encode(), f"t={timestamp},v1=forged")
    assert exc.value.status_code == 400


def test_cancel_stops_renewal_at_period_end(stripe_stub):
    stripe_stub.subscriptions["sub1"] = _subscription()

    billing.cancel_at_stripe("sub1")

    assert stripe_stub.modified == [("sub1", {"cancel_at_period_end": True})]
    assert stripe_stub.cancelled == []


def test_cancel_immediately(stripe_stub):
    stripe_stub.subscriptions["sub1"] = _subscription()

    billing.cancel_at_stripe("sub1", immediately=True)

    assert stripe_stub.cancelled == ["sub1"]


def test_cancel_of_a_subscription_stripe_no_longer_has(stripe_stub):
    assert billing.cancel_at_stripe("sub_gone") is None
