"""PayPal subscriptions (services/paypal_billing.py behind routers/billing.py)."""

import json

import pytest

from app.routers import billing
from app.services import paypal_billing
from app.services.paypal_billing import PayPalBilling, subscription_view
from app.services.stripe_billing import BillingError

NEXT_BILLING = "2026-11-28T10:00:00Z"
NEXT_BILLING_EPOCH = 1795860000


def _paypal_subscription(sub_id="I-ABC123", status="ACTIVE", next_billing=NEXT_BILLING, custom_id="pro|monthly|", **extra):
    return {
        "id": sub_id,
        "status": status,
        "custom_id": custom_id,
        "plan_id": "P-1",
        "subscriber": {"email_address": "buyer@example.com"},
        "billing_info": {"next_billing_time": next_billing} if next_billing else {},
        **extra,
    }


class FakePayPal:
    """Answers PayPalBilling._req like the PayPal API would; records requests."""

    def __init__(self):
        self.requests = []
        self.products = []
        self.plans = []
        self.subscriptions = {}
        self.cancelled = []

    def __call__(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs.get("json")))
        if path == "/v1/catalogs/products":
            if method == "GET":
                return {"products": self.products}
            self.products.append({"id": "PROD-1", "name": kwargs["json"]["name"]})
            return self.products[-1]
        if path == "/v1/billing/plans":
            if method == "GET":
                return {"plans": self.plans}
            plan = {"id": f"P-{len(self.plans) + 1}", "name": kwargs["json"]["name"], "status": "ACTIVE", "body": kwargs["json"]}
            self.plans.append(plan)
            return plan
        if path == "/v1/billing/subscriptions" and method == "POST":
            self.last_subscription = kwargs["json"]
            return {"id": "I-NEW1", "links": [{"rel": "approve", "href": "https://www.paypal.com/webapps/billing/subscriptions?ba_token=BA-1"}]}
        if path.startswith("/v1/billing/subscriptions/") and path.endswith("/cancel"):
            self.cancelled.append(path.split("/")[4])
            return {}
        if path.startswith("/v1/billing/subscriptions/"):
            sub_id = path.rsplit("/", 1)[1]
            if sub_id not in self.subscriptions:
                raise BillingError(404, "Not found at PayPal.")
            return self.subscriptions[sub_id]
        if path == "/v1/notifications/verify-webhook-signature":
            return {"verification_status": "SUCCESS" if kwargs["json"]["transmission_sig"] == "good" else "FAILURE"}
        raise AssertionError(f"unexpected PayPal call {method} {path}")


@pytest.fixture
def paypal_mode(monkeypatch, tmp_path):
    fake = FakePayPal()
    monkeypatch.setattr(PayPalBilling, "_req", lambda self, method, path, **kw: fake(method, path, **kw))
    monkeypatch.setattr(PayPalBilling, "_plan_ids", {})
    monkeypatch.setattr(billing, "PAYPAL_CLIENT_ID", "client")
    monkeypatch.setattr(billing, "PAYPAL_CLIENT_SECRET", "top-secret")
    monkeypatch.setattr(billing, "PAYPAL_WEBHOOK_ID", "WH-1")
    monkeypatch.setattr(billing, "_ISSUED_LICENSES_LOG", tmp_path / "issued.jsonl")
    billing.limiter.reset()
    issued = []

    def fake_issue(email, interval, tier, transaction_id):
        issued.append((transaction_id, email, tier, interval))
        with billing._ISSUED_LICENSES_LOG.open("a") as log:
            log.write(json.dumps({"transaction_id": transaction_id, "license_key": f"key-{len(issued)}"}) + "\n")
        return f"key-{len(issued)}"

    monkeypatch.setattr(billing, "_issue_and_deliver", fake_issue)
    fake.issued = issued
    return fake


def _webhook(client, event, sig="good"):
    headers = {
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-cert-url": "https://api.paypal.com/cert.pem",
        "paypal-transmission-id": "t-1",
        "paypal-transmission-sig": sig,
        "paypal-transmission-time": "2026-10-28T10:00:00Z",
    }
    return client.post("/api/billing/paypal/webhook", json=event, headers=headers)


def test_config_reports_paypal(client, paypal_mode):
    body = client.get("/api/billing/config").json()
    assert body["paypal_available"] is True
    assert "top-secret" not in json.dumps(body)


def test_paypal_unavailable_without_keys(client, monkeypatch):
    monkeypatch.setattr(billing, "PAYPAL_CLIENT_ID", "")
    assert client.get("/api/billing/config").json()["paypal_available"] is False
    assert client.post("/api/billing/paypal/checkout", json={"interval": "monthly"}).status_code == 503


def test_checkout_creates_product_and_plan_once_and_returns_paypal_url(client, monkeypatch, paypal_mode):
    monkeypatch.setattr(billing, "APP_BASE_URL", "https://app.example.com")

    first = client.post("/api/billing/paypal/checkout", json={"tier": "advanced", "interval": "annual"}, headers={"Accept-Language": "ru"})
    client.post("/api/billing/paypal/checkout", json={"tier": "advanced", "interval": "annual"})

    assert first.json() == {"url": "https://www.paypal.com/webapps/billing/subscriptions?ba_token=BA-1", "subscription_id": "I-NEW1"}
    assert len(paypal_mode.products) == 1 and len(paypal_mode.plans) == 1
    plan = paypal_mode.plans[0]["body"]
    assert plan["billing_cycles"][0]["frequency"] == {"interval_unit": "YEAR", "interval_count": 1}
    assert plan["billing_cycles"][0]["pricing_scheme"]["fixed_price"] == {"value": "384.00", "currency_code": "USD"}
    sent = paypal_mode.last_subscription
    assert sent["custom_id"] == "advanced|annual|"
    assert sent["application_context"]["return_url"] == "https://app.example.com/?paypal=1"
    assert sent["application_context"]["shipping_preference"] == "NO_SHIPPING"


def test_checkout_from_the_website_returns_to_its_thank_you_page(client, monkeypatch, paypal_mode):
    monkeypatch.setattr(billing, "STOREFRONT_URL", "https://crmscoring.com")
    client.post("/api/billing/paypal/checkout", json={"tier": "pro", "interval": "monthly", "source": "site"})
    assert paypal_mode.last_subscription["application_context"]["return_url"] == "https://crmscoring.com/thank-you.html?paypal=1"


def test_confirming_an_active_subscription_issues_the_key_once(client, paypal_mode):
    paypal_mode.subscriptions["I-ABC123"] = _paypal_subscription()

    first = client.get("/api/billing/paypal/subscription/I-ABC123").json()
    again = client.get("/api/billing/paypal/subscription/I-ABC123").json()

    assert first["status"] == "ok" and first["license_key"] == "key-1" and first["email"] == "buyer@example.com"
    assert again == first
    assert paypal_mode.issued == [(f"I-ABC123@{NEXT_BILLING_EPOCH}", "buyer@example.com", "pro", "monthly")]


def test_a_subscription_awaiting_approval_isnt_fulfilled(client, paypal_mode):
    paypal_mode.subscriptions["I-ABC123"] = _paypal_subscription(status="APPROVAL_PENDING")

    assert client.get("/api/billing/paypal/subscription/I-ABC123").status_code == 409
    assert paypal_mode.issued == []


def test_subscription_id_must_look_like_one(client, paypal_mode):
    assert client.get("/api/billing/paypal/subscription/sub_123").status_code == 422


def test_renewal_payment_webhook_issues_a_fresh_key(client, paypal_mode):
    paypal_mode.subscriptions["I-ABC123"] = _paypal_subscription()
    _webhook(client, {"event_type": "BILLING.SUBSCRIPTION.ACTIVATED", "resource": {"id": "I-ABC123"}})
    duplicate = _webhook(client, {"event_type": "PAYMENT.SALE.COMPLETED", "resource": {"billing_agreement_id": "I-ABC123"}})
    paypal_mode.subscriptions["I-ABC123"] = _paypal_subscription(next_billing="2026-12-28T10:00:00Z")
    renewal = _webhook(client, {"event_type": "PAYMENT.SALE.COMPLETED", "resource": {"billing_agreement_id": "I-ABC123"}})

    assert duplicate.json() == {"status": "duplicate"}
    assert renewal.json() == {"status": "ok"}
    assert len(paypal_mode.issued) == 2


def test_cancellation_webhooks_end_the_workspace_plan(client, monkeypatch, paypal_mode):
    ended = []
    monkeypatch.setattr(billing.storage, "end_tenant_subscription", lambda sub_id, until: ended.append((sub_id, until)))

    _webhook(client, {"event_type": "BILLING.SUBSCRIPTION.CANCELLED", "resource": _paypal_subscription(status="CANCELLED")})
    _webhook(client, {"event_type": "BILLING.SUBSCRIPTION.EXPIRED", "resource": _paypal_subscription(status="EXPIRED", next_billing=None)})

    assert ended == [("I-ABC123", NEXT_BILLING_EPOCH), ("I-ABC123", None)]


def test_webhook_with_a_bad_signature_is_rejected(client, paypal_mode):
    response = _webhook(client, {"event_type": "PAYMENT.SALE.COMPLETED", "resource": {"billing_agreement_id": "I-ABC123"}}, sig="forged")
    assert response.status_code == 400
    assert paypal_mode.issued == []


def test_webhook_unavailable_without_a_webhook_id(client, monkeypatch, paypal_mode):
    monkeypatch.setattr(billing, "PAYPAL_WEBHOOK_ID", "")
    assert _webhook(client, {"event_type": "PAYMENT.SALE.COMPLETED", "resource": {}}).status_code == 503


def test_other_paypal_events_are_ignored(client, paypal_mode):
    assert _webhook(client, {"event_type": "CHECKOUT.ORDER.APPROVED", "resource": {}}).json() == {"status": "ignored"}


def test_cancelling_a_paypal_subscription_keeps_the_paid_period(paypal_mode):
    paypal_mode.subscriptions["I-ABC123"] = _paypal_subscription()

    view = billing.cancel_subscription("I-ABC123")

    assert paypal_mode.cancelled == ["I-ABC123"]
    assert view["cancel_at_period_end"] is True
    assert view["current_period_end"] == NEXT_BILLING_EPOCH


def test_subscription_view_reads_the_custom_id():
    view = subscription_view(_paypal_subscription(custom_id="advanced|annual|tenant42"))
    assert view["metadata"] == {"tier": "advanced", "interval": "annual", "tenant_id": "tenant42"}
    assert view["status"] == "active"
    assert paypal_billing._epoch(NEXT_BILLING) == NEXT_BILLING_EPOCH
