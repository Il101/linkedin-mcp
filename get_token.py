"""LinkedIn OAuth helper — obtain a LINKEDIN_ACCESS_TOKEN for local/dev use.

Runs the OAuth 2.0 authorization-code flow:
  1. Opens the LinkedIn consent page in your browser.
  2. Catches the redirect on http://localhost:8000/callback.
  3. Exchanges the code for an access token and prints it.

Prerequisites
-------------
Set your OAuth app credentials in the environment first:

    export LINKEDIN_CLIENT_ID="your_client_id"
    export LINKEDIN_CLIENT_SECRET="your_client_secret"

In the LinkedIn Developer Portal, add this exact redirect URL to your app:

    http://localhost:8000/callback

Required scopes: openid, profile, w_member_social.

Note: LinkedIn access tokens expire after ~60 days; rerun this script to renew.
"""

import os
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

REDIRECT_URI = "http://localhost:8000/callback"
SCOPES = "openid profile w_member_social"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

_auth_code: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        global _auth_code
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if "code" in params:
            _auth_code = params["code"][0]
            self.wfile.write(b"<h1>Authorized.</h1>You can close this tab.")
        else:
            error = params.get("error_description", ["unknown error"])[0]
            self.wfile.write(f"<h1>Authorization failed</h1>{error}".encode())

    def log_message(self, *args):  # silence the default request logging
        pass


def main() -> None:
    client_id = os.getenv("LINKEDIN_CLIENT_ID")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit(
            "Error: set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET "
            "environment variables first (see this script's docstring)."
        )

    auth_request = AUTH_URL + "?" + urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
        }
    )

    print(f"Opening browser for LinkedIn authorization:\n{auth_request}\n")
    webbrowser.open(auth_request)

    server = HTTPServer(("localhost", 8000), _CallbackHandler)
    print("Waiting for the redirect on http://localhost:8000/callback ...")
    while _auth_code is None:
        server.handle_request()

    print("Exchanging authorization code for an access token ...")
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": _auth_code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    token = response.json()["access_token"]

    print("\nSuccess. Add this to your .env (LINKEDIN_ACCESS_TOKEN):\n")
    print(token)


if __name__ == "__main__":
    main()
