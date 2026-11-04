"""Turns a Threads token from the Meta app dashboard into a 60-day one.

Run it on your own computer:

    python marketing/threads_token.py

In your Meta app, open Use cases -> Access the Threads API -> Settings, add
your Threads account as a Threads Tester (and accept the invite in Threads:
Settings -> Account -> Website permissions), then generate a token with
threads_basic and threads_content_publish. Paste it here with the app's
Threads App Secret; the printed token goes in the THREADS_ACCESS_TOKEN secret
on GitHub. Run this again before the 60 days are up, with a fresh token.
"""

import getpass

import requests


def main() -> None:
    secret = getpass.getpass("Threads App Secret (hidden): ").strip()
    short = getpass.getpass("Token from the app dashboard (hidden): ").strip()
    resp = requests.get(
        "https://graph.threads.net/access_token",
        params={"grant_type": "th_exchange_token", "client_secret": secret, "access_token": short},
        timeout=30,
    )
    if resp.status_code != 200:
        raise SystemExit(f"Threads didn't extend the token: {resp.text[:300]}")
    body = resp.json()
    me = requests.get("https://graph.threads.net/v1.0/me", params={"fields": "username", "access_token": body["access_token"]}, timeout=30)
    who = me.json().get("username", "?") if me.ok else "?"
    print(f"\nToken for @{who}, valid for about {int(body.get('expires_in', 0)) // 86400} days.")
    print("Save it as the THREADS_ACCESS_TOKEN secret on GitHub:\n")
    print(body["access_token"])


if __name__ == "__main__":
    main()
