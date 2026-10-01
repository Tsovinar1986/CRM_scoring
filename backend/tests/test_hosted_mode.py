"""HOSTED_MODE: the public deployment behind crmscoring.com's free trial."""

from types import SimpleNamespace

import braintree
import pytest

from app import config, storage
from app.routers import billing
from app.routers import leads as leads_router

CSV = "company_name,domain\nAcme,acme.com\n"


@pytest.fixture
def hosted(monkeypatch):
    monkeypatch.setattr(config, "HOSTED_MODE", True)
    monkeypatch.setattr("app.routers.accounts.HOSTED_MODE", True)
    monkeypatch.setattr("app.routers.billing.HOSTED_MODE", True)
    monkeypatch.setattr("app.main.HOSTED_MODE", True)
    # Scoring itself isn't under test -- keep uploads offline and fast.
    monkeypatch.setattr(leads_router, "enrich_lead", lambda lead: lead)
    monkeypatch.setattr(leads_router, "score_lead", lambda lead: _scored(lead))


def _scored(lead):
    from tests.conftest import make_scored_lead

    return make_scored_lead(company_name=lead.company_name, domain=lead.domain)


def _trial(client) -> dict:
    response = client.post("/api/accounts/trial")
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['api_key']}"}


def _upload(client, headers, body=CSV):
    return client.post("/api/leads/upload", headers=headers, files={"file": ("leads.csv", body, "text/csv")})


def test_no_workspace_key_is_refused(client, hosted):
    assert client.get("/api/leads").status_code == 401
    assert _upload(client, {}).status_code == 401


def test_license_status_never_exposes_the_sellers_license(client, hosted):
    body = client.get("/api/license").json()

    assert body == {
        "hosted": True, "licensed": False, "reason": "no_workspace", "customer_email": None,
        "plan": None, "tier": "starter", "trial_uploads_left": None,
    }


def test_trial_workspaces_are_private(client, hosted):
    alice, bob = _trial(client), _trial(client)

    _upload(client, alice)

    assert len(client.get("/api/leads", headers=alice).json()) == 1
    assert client.get("/api/leads", headers=bob).json() == []


def test_trial_has_its_own_upload_allowance(client, hosted, monkeypatch):
    monkeypatch.setattr("app.licensing.TRIAL_MAX_UPLOADS", 2)
    headers = _trial(client)

    assert _upload(client, headers).status_code == 200
    assert client.get("/api/license", headers=headers).json()["trial_uploads_left"] == 1
    assert _upload(client, headers).status_code == 200
    assert _upload(client, headers).status_code == 402
    assert client.get("/api/license", headers=headers).json()["reason"] == "trial_expired"
    # A fresh visitor isn't affected by someone else's usage.
    assert _upload(client, _trial(client)).status_code == 200


def test_trial_caps_rows_per_upload(client, hosted):
    rows = "".join(f"Co{i},co{i}.com\n" for i in range(25))

    response = _upload(client, _trial(client), "company_name,domain\n" + rows)

    assert response.headers["x-trial-limited-rows"] == "10"
    assert len(response.json()) == 10


def test_trial_endpoint_is_off_for_self_hosted_installs(client):
    assert client.post("/api/accounts/trial").status_code == 404


def test_trial_creation_is_rate_limited(client, hosted, monkeypatch):
    statuses = [client.post("/api/accounts/trial").status_code for _ in range(4)]

    assert statuses == [200, 200, 200, 429]


def test_subscribing_upgrades_the_workspace_and_cancelling_downgrades_it(client, hosted, monkeypatch, tmp_path):
    headers = _trial(client)
    tenant = storage.get_tenant_by_api_key(headers["Authorization"].removeprefix("Bearer "))
    subscription = SimpleNamespace(
        id="sub9", status="Active", plan_id="adv-m", paid_through_date="2026-10-25", payment_method_token="pm"
    )
    gateway = SimpleNamespace(
        customer=SimpleNamespace(create=lambda params: SimpleNamespace(
            is_success=True, customer=SimpleNamespace(payment_methods=[SimpleNamespace(token="pm")]))),
        subscription=SimpleNamespace(create=lambda params: SimpleNamespace(is_success=True, subscription=subscription)),
    )
    monkeypatch.setattr(billing, "_gateway", lambda: gateway)
    monkeypatch.setattr(billing, "BRAINTREE_PLAN_ADVANCED_MONTHLY", "adv-m")
    monkeypatch.setattr(billing, "_ISSUED_LICENSES_LOG", tmp_path / "issued.jsonl")
    monkeypatch.setattr(billing, "_issue_and_deliver", lambda *args: "key")
    monkeypatch.setattr(billing, "_licensee", lambda sub: "Jane Doe")

    response = client.post(
        "/api/billing/braintree/subscribe",
        headers=headers,
        json={"tier": "advanced", "interval": "monthly", "payment_method_nonce": "n"},
    )

    assert response.json()["workspace_upgraded"] is True
    assert client.get("/api/license", headers=headers).json()["tier"] == "advanced"

    notification = SimpleNamespace(kind=braintree.WebhookNotification.Kind.SubscriptionCanceled,
                                   subscription=SimpleNamespace(id="sub9"))
    monkeypatch.setattr(billing, "_parse_webhook", lambda signature, payload: notification)
    client.post("/api/billing/braintree/webhook", data={"bt_signature": "s", "bt_payload": "p"})

    assert storage.get_tenant_by_api_key(headers["Authorization"].removeprefix("Bearer ")).plan == "starter"
    assert tenant.plan == "starter"


def test_hosted_signup_starts_on_starter(client, hosted, monkeypatch):
    # No seller license needed: a hosted signup is a free workspace that
    # upgrades by paying, not an agency onboarding a client.
    monkeypatch.setattr("app.routers.accounts.verify_license", lambda: None)

    response = client.post(
        "/api/accounts/signup", json={"name": "Jo", "email": "jo@example.com", "password": "Sup3r-secret-pass!"}
    )

    key = response.json()["api_key"]
    assert storage.get_tenant_by_api_key(key).plan == "starter"


def test_self_hosted_install_is_unchanged(client):
    assert client.get("/api/leads").status_code == 200
    assert client.get("/api/license").json()["hosted"] is False


def _subscribed_workspace(client, monkeypatch, tmp_path, cancel_calls, paid_through):
    headers = _trial(client)
    tenant = storage.get_tenant_by_api_key(headers["Authorization"].removeprefix("Bearer "))
    storage.set_tenant_subscription(tenant.id, "pro", "sub7")
    subscription = SimpleNamespace(id="sub7", status="Active", paid_through_date=paid_through)
    gateway = SimpleNamespace(subscription=SimpleNamespace(
        find=lambda sub_id: subscription,
        cancel=lambda sub_id: cancel_calls.append(sub_id) or SimpleNamespace(is_success=True),
    ))
    monkeypatch.setattr(billing, "_gateway", lambda: gateway)
    return headers


def test_cancel_keeps_access_until_the_paid_period_ends(client, hosted, monkeypatch, tmp_path):
    from datetime import date, timedelta

    cancels = []
    headers = _subscribed_workspace(client, monkeypatch, tmp_path, cancels, date.today() + timedelta(days=10))

    response = client.post("/api/billing/subscription/cancel", headers=headers)

    assert response.json()["status"] == "cancelled"
    assert cancels == ["sub7"]
    status = client.get("/api/license", headers=headers).json()
    assert status["tier"] == "pro"
    assert status["expires_at"] == response.json()["access_until"]
    # Cancelling twice isn't possible -- the subscription is detached.
    assert client.post("/api/billing/subscription/cancel", headers=headers).status_code == 404


def test_workspace_drops_to_starter_once_the_paid_period_is_over(client, hosted, monkeypatch, tmp_path):
    from datetime import date, timedelta

    headers = _subscribed_workspace(client, monkeypatch, tmp_path, [], date.today() - timedelta(days=2))

    client.post("/api/billing/subscription/cancel", headers=headers)

    status = client.get("/api/license", headers=headers).json()
    assert status["tier"] == "starter"
    assert status["licensed"] is False


def test_cancel_needs_a_subscription(client, hosted):
    assert client.post("/api/billing/subscription/cancel", headers=_trial(client)).status_code == 404


def test_cancel_needs_a_workspace(client, hosted):
    assert client.post("/api/billing/subscription/cancel").status_code == 401
