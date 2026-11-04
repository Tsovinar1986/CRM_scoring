"""Turns a short-lived Facebook token into a Page token for marketing/autopost.py.

Run it on your own computer:

    python marketing/facebook_token.py

It asks for your Meta app's App ID and App Secret and a user token from the
Graph API Explorer (with pages_manage_posts, pages_read_engagement,
pages_show_list, and for Instagram also instagram_basic and
instagram_content_publish), then prints each of your Pages with its ID, a
Page token that doesn't expire, and the Instagram account linked to it. Save
them as the FACEBOOK_PAGE_ID, FACEBOOK_PAGE_TOKEN and INSTAGRAM_ACCOUNT_ID
secrets on GitHub.
"""

import getpass
import os

import requests

GRAPH = f"https://graph.facebook.com/{os.getenv('FACEBOOK_GRAPH_VERSION', 'v23.0')}"


def main() -> None:
    app_id = input("Meta App ID: ").strip()
    app_secret = getpass.getpass("Meta App Secret (hidden): ").strip()
    short = getpass.getpass("User token from the Graph API Explorer (hidden): ").strip()

    # A long-lived user token gives Page tokens that don't expire.
    resp = requests.get(
        f"{GRAPH}/oauth/access_token",
        params={"grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret, "fb_exchange_token": short},
        timeout=30,
    )
    if resp.status_code != 200:
        raise SystemExit(f"Facebook didn't extend the token: {resp.text[:300]}")
    long_user = resp.json()["access_token"]

    pages = requests.get(f"{GRAPH}/me/accounts", params={"access_token": long_user, "fields": "id,name,access_token,instagram_business_account"}, timeout=30)
    if pages.status_code != 200:
        raise SystemExit(f"Couldn't list your Pages: {pages.text[:300]}")
    found = pages.json().get("data", [])
    if not found:
        raise SystemExit("No Pages found. Make sure you manage a Facebook Page and ticked it when the Explorer asked.")
    for page in found:
        print(f"\nPage: {page['name']}\n  FACEBOOK_PAGE_ID    = {page['id']}\n  FACEBOOK_PAGE_TOKEN = {page['access_token']}")
        instagram = (page.get("instagram_business_account") or {}).get("id")
        print(f"  INSTAGRAM_ACCOUNT_ID = {instagram}" if instagram else "  (no Instagram Professional account linked to this Page)")


if __name__ == "__main__":
    main()
