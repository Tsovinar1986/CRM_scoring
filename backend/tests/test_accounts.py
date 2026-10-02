from unittest.mock import MagicMock

import pytest

from app import storage
from app.licensing import LicenseInfo
from app.routers import accounts


def _signup(client, email="buyer@acme.com", password="Correct-Horse9", name="Acme Corp"):
    return client.post("/api/accounts/signup", json={"name": name, "email": email, "password": password})


@pytest.fixture(autouse=True)
def _advanced_license(monkeypatch):
    """Signup requires an Advanced-tier license on this deployment (see
    accounts.py's module docstring) -- default every test here to having
    one, since the gating itself is covered by the dedicated tests below."""
    monkeypatch.setattr(
        accounts,
        "verify_license",
        lambda: LicenseInfo(customer_email="seller@example.com", plan="monthly", tier="advanced", expires_at=None),
    )


def test_signup_blocked_without_a_license(client, monkeypatch):
    monkeypatch.setattr(accounts, "verify_license", lambda: None)
    resp = _signup(client)
    assert resp.status_code == 402


def test_signup_blocked_with_a_pro_license(client, monkeypatch):
    monkeypatch.setattr(
        accounts,
        "verify_license",
        lambda: LicenseInfo(customer_email="seller@example.com", plan="monthly", tier="pro", expires_at=None),
    )
    resp = _signup(client)
    assert resp.status_code == 402


def test_signup_creates_a_usable_tenant(client):
    resp = _signup(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Acme Corp"
    assert body["api_key"]

    # The returned key actually works against a real endpoint.
    leads_resp = client.get("/api/leads", headers={"Authorization": f"Bearer {body['api_key']}"})
    assert leads_resp.status_code == 200


def test_signup_rejects_duplicate_email(client):
    _signup(client)
    resp = _signup(client, name="Someone Else")
    assert resp.status_code == 409


def test_signup_rejects_weak_password(client):
    resp = _signup(client, password="weak")
    assert resp.status_code == 400
    assert "8 characters" in resp.json()["detail"]


def test_signup_rejects_invalid_email(client):
    resp = client.post(
        "/api/accounts/signup", json={"name": "Acme", "email": "not-an-email", "password": "Correct-Horse9"}
    )
    assert resp.status_code == 422


def test_login_with_correct_credentials_succeeds(client):
    _signup(client)
    resp = client.post(
        "/api/accounts/login", json={"email": "buyer@acme.com", "password": "Correct-Horse9"}
    )
    assert resp.status_code == 200
    assert resp.json()["api_key"]


def test_login_with_wrong_password_fails(client):
    _signup(client)
    resp = client.post(
        "/api/accounts/login", json={"email": "buyer@acme.com", "password": "wrong-password9!"}
    )
    assert resp.status_code == 401


def test_login_with_unknown_email_fails(client):
    resp = client.post(
        "/api/accounts/login", json={"email": "nobody@nowhere.com", "password": "Correct-Horse9"}
    )
    assert resp.status_code == 401


def test_login_rotates_the_api_key(client):
    signup_resp = _signup(client)
    old_key = signup_resp.json()["api_key"]

    login_resp = client.post(
        "/api/accounts/login", json={"email": "buyer@acme.com", "password": "Correct-Horse9"}
    )
    new_key = login_resp.json()["api_key"]

    assert new_key != old_key
    assert client.get("/api/leads", headers={"Authorization": f"Bearer {old_key}"}).status_code == 401
    assert client.get("/api/leads", headers={"Authorization": f"Bearer {new_key}"}).status_code == 200


def test_forgot_password_gives_same_response_for_known_and_unknown_email(client):
    _signup(client)
    known = client.post("/api/accounts/forgot-password", json={"email": "buyer@acme.com"})
    unknown = client.post("/api/accounts/forgot-password", json={"email": "nobody@nowhere.com"})

    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json() == unknown.json()


def test_forgot_password_sends_email_when_account_exists(client, monkeypatch):
    _signup(client)
    send_mock = MagicMock(return_value=True)
    monkeypatch.setattr(accounts, "send_password_reset_email", send_mock)

    client.post("/api/accounts/forgot-password", json={"email": "buyer@acme.com"})

    assert send_mock.called
    to_email, reset_url, ttl_minutes = send_mock.call_args[0]
    assert to_email == "buyer@acme.com"
    assert "/reset-password?token=" in reset_url


def test_forgot_password_does_not_send_email_for_unknown_account(client, monkeypatch):
    send_mock = MagicMock(return_value=True)
    monkeypatch.setattr(accounts, "send_password_reset_email", send_mock)

    client.post("/api/accounts/forgot-password", json={"email": "nobody@nowhere.com"})

    assert not send_mock.called


def test_reset_password_with_valid_token_succeeds_and_new_password_works(client):
    _signup(client)
    tenant = storage.get_tenant_by_email("buyer@acme.com")
    token = storage.create_password_reset(tenant.id, ttl_seconds=3600)

    resp = client.post(
        "/api/accounts/reset-password", json={"token": token, "password": "New-Correct9"}
    )
    assert resp.status_code == 200

    login_resp = client.post(
        "/api/accounts/login", json={"email": "buyer@acme.com", "password": "New-Correct9"}
    )
    assert login_resp.status_code == 200

    old_login = client.post(
        "/api/accounts/login", json={"email": "buyer@acme.com", "password": "Correct-Horse9"}
    )
    assert old_login.status_code == 401


def test_reset_password_token_is_single_use(client):
    _signup(client)
    tenant = storage.get_tenant_by_email("buyer@acme.com")
    token = storage.create_password_reset(tenant.id, ttl_seconds=3600)

    first = client.post("/api/accounts/reset-password", json={"token": token, "password": "New-Correct9"})
    second = client.post("/api/accounts/reset-password", json={"token": token, "password": "Another-Correct9"})

    assert first.status_code == 200
    assert second.status_code == 400


def test_reset_password_rejects_invalid_token(client):
    resp = client.post(
        "/api/accounts/reset-password", json={"token": "not-a-real-token", "password": "New-Correct9"}
    )
    assert resp.status_code == 400


def test_reset_password_rejects_weak_new_password(client):
    _signup(client)
    tenant = storage.get_tenant_by_email("buyer@acme.com")
    token = storage.create_password_reset(tenant.id, ttl_seconds=3600)

    resp = client.post("/api/accounts/reset-password", json={"token": token, "password": "weak"})
    assert resp.status_code == 400


# --- Account settings ---


def _signed_in(client, **kwargs):
    resp = _signup(client, **kwargs)
    return {"Authorization": f"Bearer {resp.json()['api_key']}"}


def test_me_returns_the_signed_in_account(client):
    headers = _signed_in(client)
    me = client.get("/api/accounts/me", headers=headers).json()
    assert me["name"] == "Acme Corp"
    assert me["email"] == "buyer@acme.com"
    assert me["has_password"] is True
    assert me["has_subscription"] is False


def test_me_is_not_available_for_the_self_hosted_default_workspace(client):
    assert client.get("/api/accounts/me").status_code == 404


def test_rename_workspace(client):
    headers = _signed_in(client)
    assert client.patch("/api/accounts/me", headers=headers, json={"name": "  New Name "}).status_code == 200
    assert client.get("/api/accounts/me", headers=headers).json()["name"] == "New Name"


def test_change_password_needs_the_current_one_and_rotates_the_key(client):
    headers = _signed_in(client)
    wrong = client.post(
        "/api/accounts/me/password", headers=headers,
        json={"current_password": "nope", "new_password": "Brand-New-Pass7"},
    )
    assert wrong.status_code == 403

    resp = client.post(
        "/api/accounts/me/password", headers=headers,
        json={"current_password": "Correct-Horse9", "new_password": "Brand-New-Pass7"},
    )
    assert resp.status_code == 200
    assert client.get("/api/accounts/me", headers=headers).status_code == 401  # old key signed out
    login = client.post("/api/accounts/login", json={"email": "buyer@acme.com", "password": "Brand-New-Pass7"})
    assert login.status_code == 200


def test_change_password_enforces_strength(client):
    headers = _signed_in(client)
    resp = client.post(
        "/api/accounts/me/password", headers=headers,
        json={"current_password": "Correct-Horse9", "new_password": "weak"},
    )
    assert resp.status_code == 400


def test_delete_account_needs_the_password(client):
    headers = _signed_in(client)
    resp = client.request("DELETE", "/api/accounts/me", headers=headers, json={"password": "wrong"})
    assert resp.status_code == 403
    assert client.get("/api/accounts/me", headers=headers).status_code == 200


def test_delete_account_erases_the_workspace_and_its_leads(client):
    from .conftest import make_scored_lead

    headers = _signed_in(client)
    tenant = storage.get_tenant_by_api_key(headers["Authorization"].removeprefix("Bearer "))
    storage.upsert_leads(tenant.id, [make_scored_lead()])

    resp = client.request("DELETE", "/api/accounts/me", headers=headers, json={"password": "Correct-Horse9"})
    assert resp.status_code == 200
    assert storage.list_leads(tenant.id) == []
    assert storage.get_tenant_by_email("buyer@acme.com") is None
    assert client.post(
        "/api/accounts/login", json={"email": "buyer@acme.com", "password": "Correct-Horse9"}
    ).status_code == 401


def test_delete_account_cancels_the_subscription_first(client, monkeypatch):
    headers = _signed_in(client)
    tenant = storage.get_tenant_by_api_key(headers["Authorization"].removeprefix("Bearer "))
    storage.set_tenant_subscription(tenant.id, "pro", "sub9")
    cancelled = []
    monkeypatch.setattr(accounts, "cancel_at_braintree", lambda sub_id: cancelled.append(sub_id))

    resp = client.request("DELETE", "/api/accounts/me", headers=headers, json={"password": "Correct-Horse9"})
    assert resp.status_code == 200
    assert cancelled == ["sub9"]


def test_delete_account_keeps_everything_if_the_cancel_fails(client, monkeypatch):
    from fastapi import HTTPException

    headers = _signed_in(client)
    tenant = storage.get_tenant_by_api_key(headers["Authorization"].removeprefix("Bearer "))
    storage.set_tenant_subscription(tenant.id, "pro", "sub9")

    def fail(sub_id):
        raise HTTPException(status_code=502, detail="Couldn't connect to Braintree.")

    monkeypatch.setattr(accounts, "cancel_at_braintree", fail)
    resp = client.request("DELETE", "/api/accounts/me", headers=headers, json={"password": "Correct-Horse9"})
    assert resp.status_code == 502
    assert client.get("/api/accounts/me", headers=headers).json()["has_subscription"] is True
