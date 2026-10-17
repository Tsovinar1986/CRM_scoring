"""End-to-end check of subscriptions through Paying's test bank.

Acts like a buyer: starts a free trial workspace, subscribes to a plan,
pays on Paying's test bank, comes back to the app, and checks the
workspace was upgraded; then cancels and checks access runs to the end of
the paid period. Also checks a declined card leaves the workspace on
Starter. No real money moves: it only works while Paying is in test mode.

    cd backend && ../.venv/bin/python scripts/check_billing.py
    cd backend && ../.venv/bin/python scripts/check_billing.py https://ai-lead-generation-scoring.onrender.com

The app's BILLING_PROVIDER must be paying (or empty with Paying's keys set).
Exits non-zero if any step fails.
"""

import re
import sys
from urllib.parse import parse_qs, urljoin, urlparse

import requests

APP_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8081").rstrip("/")
TIMEOUT = 90  # a sleeping Render service can take a while to wake up


class CheckFailed(Exception):
    pass


def step(text: str) -> None:
    print(f"  ✓ {text}")


def expect(condition: bool, text: str) -> None:
    if not condition:
        raise CheckFailed(text)


def api(method: str, path: str, key: str | None = None, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    resp = requests.request(method, f"{APP_URL}/api{path}", headers=headers, timeout=TIMEOUT, **kwargs)
    if resp.status_code >= 400:
        raise CheckFailed(f"{method} /api{path} -> {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def pay_on_test_bank(checkout_url: str, outcome: str) -> str:
    """Goes through Paying's checkout with the test card; returns the URL the
    buyer ends up on."""
    browser = requests.Session()
    page = browser.get(checkout_url, timeout=TIMEOUT)
    expect(page.ok, f"checkout page didn't open ({page.status_code})")
    expect("fake" in page.text, "checkout page has no test card -- is Paying in test mode?")
    # Pick the test card; Paying then redirects to its test bank.
    bank = browser.post(checkout_url, data={"method": "fake", "email": "billing-check@example.com"}, timeout=TIMEOUT, allow_redirects=False)
    expect(bank.status_code == 303 and "/fake-bank/" in bank.headers.get("location", ""), "checkout didn't send the buyer to the test bank")
    bank_url = urljoin(checkout_url, bank.headers["location"])
    # Press Pay or Decline, then follow the bank's redirects back.
    result = browser.post(f"{bank_url}/{outcome}", timeout=TIMEOUT, allow_redirects=False)
    url = urljoin(bank_url, result.headers.get("location", ""))
    for _ in range(5):
        if not url.startswith(urljoin(checkout_url, "/")):
            break  # left Paying: back at the app
        resp = browser.get(url, timeout=TIMEOUT, allow_redirects=False)
        if resp.status_code not in (301, 302, 303, 307):
            break
        url = urljoin(url, resp.headers["location"])
    return url


def check_paid_subscription() -> None:
    print("Paid subscription")
    key = api("POST", "/accounts/trial")["api_key"]
    expect(api("GET", "/license", key)["tier"] == "starter", "a new trial isn't on Starter")
    step("trial workspace starts on Starter")

    started = api("POST", "/billing/checkout", key, json={"tier": "pro", "interval": "monthly"})
    step(f"checkout opened: {started['url']}")

    landed = pay_on_test_bank(started["url"], "paid")
    session_id = (parse_qs(urlparse(landed).query).get("checkout") or [None])[0]
    expect(session_id == started["session_id"], f"buyer wasn't sent back to the app with the session (ended on {landed})")
    step(f"paid on the test bank and came back to {landed.split('?')[0]}")

    result = api("GET", f"/billing/session/{session_id}")
    expect(result.get("status") == "ok" and result.get("workspace_upgraded"), f"payment not confirmed: {result}")
    status = api("GET", "/license", key)
    expect(status["tier"] == "pro" and status["licensed"], f"workspace not upgraded: {status}")
    step("payment confirmed, workspace is on Pro")

    cancelled = api("POST", "/billing/subscription/cancel", key)
    status = api("GET", "/license", key)
    expect(cancelled["status"] == "cancelled" and status["tier"] == "pro" and status.get("expires_at"), f"cancel didn't keep access to period end: {status}")
    step("cancelled; Pro stays until the paid period ends")


def check_declined_card() -> None:
    print("Declined card")
    key = api("POST", "/accounts/trial")["api_key"]
    started = api("POST", "/billing/checkout", key, json={"tier": "pro", "interval": "monthly"})
    landed = pay_on_test_bank(started["url"], "declined")
    expect("error=declined" in landed, f"a declined card didn't return to checkout with an error (ended on {landed})")
    expect(api("GET", "/license", key)["tier"] == "starter", "a declined card upgraded the workspace")
    step("declined card shows an error and leaves the workspace on Starter")


def main() -> int:
    print(f"Checking billing at {APP_URL}")
    config = api("GET", "/billing/config")
    expect(config["checkout_available"], "checkout isn't configured (set BILLING_PROVIDER=paying and the PAYING_* keys)")
    expect(config["environment"] == "test", "the app uses a live key -- this check only runs against Paying's test mode")
    step("checkout is configured (test mode)")
    try:
        check_paid_subscription()
        check_declined_card()
    except CheckFailed as exc:
        print(f"  ✗ {exc}")
        print("FAILED")
        return 1
    print("All billing checks passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckFailed as exc:
        print(f"  ✗ {exc}\nFAILED")
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"  ✗ couldn't reach {re.sub(r'/api.*', '', str(exc))[:200]}\nFAILED")
        sys.exit(1)
