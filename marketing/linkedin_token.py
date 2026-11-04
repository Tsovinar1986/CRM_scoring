"""Gets a LinkedIn access token for marketing/autopost.py.

Run it on your own computer:

    python marketing/linkedin_token.py

It asks for your LinkedIn app's Client ID and Client Secret, opens LinkedIn in
the browser for you to sign in, and prints the access token to save as the
LINKEDIN_ACCESS_TOKEN secret on GitHub. Tokens last 60 days; run it again then.

The app needs "Sign In with LinkedIn using OpenID Connect" and "Share on
LinkedIn" (Products tab), and http://localhost:8765/callback as an
Authorized redirect URL (Auth tab).
"""

import getpass
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

REDIRECT = "http://localhost:8765/callback"
SCOPES = "openid profile w_member_social"


def main() -> None:
    client_id = input("LinkedIn app Client ID: ").strip()
    client_secret = getpass.getpass("LinkedIn app Client Secret (hidden): ").strip()
    state = secrets.token_urlsafe(16)
    received: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            received.update(query)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>Done. You can close this tab and go back to the terminal.</h2>".encode())

        def log_message(self, *args):
            pass

    url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode(
        {"response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "scope": SCOPES, "state": state}
    )
    print("\nOpening LinkedIn in your browser. If it doesn't open, visit:\n" + url + "\n")
    webbrowser.open(url)
    with HTTPServer(("localhost", 8765), Callback) as server:
        while "code" not in received and "error" not in received:
            server.handle_request()

    if "error" in received:
        raise SystemExit(f"LinkedIn said: {received.get('error_description', received['error'])}")
    if received.get("state") != state:
        raise SystemExit("The sign-in reply didn't match this request; run the script again.")

    resp = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": received["code"],
            "redirect_uri": REDIRECT,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise SystemExit(f"LinkedIn didn't issue a token: {resp.status_code} {resp.text[:300]}")
    body = resp.json()
    days = int(body.get("expires_in", 0)) // 86400
    print("\nSave this as the LINKEDIN_ACCESS_TOKEN secret on GitHub (valid for about %d days):\n" % days)
    print(body["access_token"])


if __name__ == "__main__":
    main()
