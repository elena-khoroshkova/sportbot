"""
Run this script ONCE on your own computer to get a Google OAuth2 refresh token.

Steps:
  1.  Make sure you have Python + google-auth-oauthlib installed:
         pip install google-auth-oauthlib
  2.  Export OAuth client credentials (or put them in .env locally):
         GOOGLE_CLIENT_ID=...
         GOOGLE_CLIENT_SECRET=...
  3.  Run this script:
         python get_refresh_token.py
  4.  A URL will be printed — open it in your browser, log in, and grant access.
  5.  Paste the authorisation code back into the terminal.
  6.  Copy the printed refresh_token into your Railway environment variables
      (and into .env for local testing).

You only need to do this once.  The refresh token does not expire unless you
revoke the app in your Google account settings.
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit(
        "Missing GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in environment. "
        "Set them and re-run."
    )

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

client_config = {
    "installed": {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
        "token_uri":     "https://oauth2.googleapis.com/token",
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
    }
}

flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

# Console flow: prints a URL, you paste back the code — no local server needed
creds = flow.run_console()

print("\n" + "=" * 60)
print("SUCCESS! Copy this refresh token into your Railway env vars")
print("and into the .env file as GOOGLE_REFRESH_TOKEN=")
print("=" * 60)
print(creds.refresh_token)
print("=" * 60 + "\n")
