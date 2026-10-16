"""Client for the Paying service. Copy this one file into any project.

Needs only `requests`.

    from paying_client import Paying, verify_webhook

    paying = Paying("https://pay.example.am", "sk_test_...")
    session = paying.create_checkout(
        amount=1500_00, currency="AMD", description="CRM Scoring Pro",
        mode="subscription", interval="month",
        success_url="https://app.example.am/?checkout={CHECKOUT_SESSION_ID}",
        cancel_url="https://app.example.am/#plans",
        metadata={"tier": "pro"},
    )
    redirect(session["url"])

    # webhook endpoint
    event = verify_webhook(raw_body, request.headers["Paying-Signature"], "whsec_...")
    if event["type"] == "payment.succeeded": ...

Amounts are integers in minor units: 1500 AMD = 150000, $20.00 = 2000.
"""

import hashlib
import hmac
import json
import time

import requests


class PayingError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class Paying:
    def __init__(self, base_url: str, secret_key: str, timeout: float = 20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {secret_key}"

    def _req(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = self._session.request(method, f"{self.base_url}/v1{path}", timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise PayingError(0, f"Couldn't reach Paying: {exc!r}") from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail")
            except ValueError:
                detail = resp.text
            raise PayingError(resp.status_code, detail if isinstance(detail, str) else json.dumps(detail))
        return resp.json()

    # Checkout
    def create_checkout(
        self,
        *,
        amount: int,
        description: str,
        success_url: str,
        cancel_url: str,
        currency: str = "AMD",
        mode: str = "payment",
        interval: str | None = None,
        customer_email: str | None = None,
        metadata: dict[str, str] | None = None,
        methods: list[str] | None = None,
    ) -> dict:
        body = {
            "amount": amount,
            "currency": currency,
            "description": description,
            "mode": mode,
            "interval": interval,
            "customer_email": customer_email,
            "metadata": metadata or {},
            "methods": methods,
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        return self._req("POST", "/checkout/sessions", json={k: v for k, v in body.items() if v is not None})

    def get_checkout(self, session_id: str) -> dict:
        return self._req("GET", f"/checkout/sessions/{session_id}")

    # Payments
    def get_payment(self, payment_id: str) -> dict:
        return self._req("GET", f"/payments/{payment_id}")

    def list_payments(self, **filters) -> list[dict]:
        return self._req("GET", "/payments", params=filters)["data"]

    def refund(self, payment_id: str, amount: int | None = None) -> dict:
        return self._req("POST", f"/payments/{payment_id}/refund", json={"amount": amount} if amount else {})

    # Subscriptions
    def get_subscription(self, sub_id: str) -> dict:
        return self._req("GET", f"/subscriptions/{sub_id}")

    def cancel_subscription(self, sub_id: str, at_period_end: bool = True) -> dict:
        return self._req("POST", f"/subscriptions/{sub_id}/cancel", json={"at_period_end": at_period_end})

    def methods(self, currency: str | None = None) -> list[dict]:
        return self._req("GET", "/methods", params={"currency": currency} if currency else None)["data"]


class WebhookSignatureError(Exception):
    pass


def verify_webhook(body: bytes, signature_header: str, secret: str, tolerance: int = 300) -> dict:
    """Check a webhook's Paying-Signature and return the parsed event.

    Raises WebhookSignatureError if it's forged, tampered with or older than
    `tolerance` seconds (replay protection).
    """
    parts = dict(p.split("=", 1) for p in (signature_header or "").split(",") if "=" in p)
    try:
        t = int(parts["t"])
        given = parts["v1"]
    except (KeyError, ValueError):
        raise WebhookSignatureError("Malformed Paying-Signature header")
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, given):
        raise WebhookSignatureError("Signature mismatch")
    if abs(time.time() - t) > tolerance:
        raise WebhookSignatureError("Signature too old")
    return json.loads(body)
