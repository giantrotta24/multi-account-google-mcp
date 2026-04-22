"""
One-time OAuth2 authorization flow. Run once per account.

Usage:
    uv --directory ~/Code/google-mcp run auth_setup.py personal
    uv --directory ~/Code/google-mcp run auth_setup.py work
"""
from __future__ import annotations

import argparse

import keyring
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import CREDENTIALS_PATH, KEYCHAIN_SERVICES, SCOPES, get_expected_email


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize a Google account for google-mcp.")
    parser.add_argument(
        "account", choices=sorted(KEYCHAIN_SERVICES), help="Account to authorize"
    )
    args = parser.parse_args()

    account: str = args.account
    service_name = KEYCHAIN_SERVICES[account]
    expected_email = get_expected_email(account)

    if not CREDENTIALS_PATH.exists():
        raise SystemExit(
            f"credentials.json not found at {CREDENTIALS_PATH}. "
            "Download it from Google Cloud Console (OAuth 2.0 Desktop app) and place it there."
        )

    existing_token = keyring.get_password(service_name, "refresh_token")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_PATH),
        scopes=SCOPES,
    )

    # access_type=offline ensures a refresh token on first consent.
    # prompt=consent is forced ONLY on first-time bootstrap. On rerun we skip
    # it so Google doesn't rotate the refresh token each time (per-user/per-
    # client refresh-token limits exist — older tokens silently age out).
    if existing_token:
        creds = flow.run_local_server(port=0, access_type="offline")
    else:
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    # Verify the authorized account matches the expected email.
    gmail_service = build("gmail", "v1", credentials=creds)
    profile = gmail_service.users().getProfile(userId="me").execute()
    authorized_email: str = profile["emailAddress"]

    if expected_email and authorized_email != expected_email:
        raise SystemExit(
            f"ERROR: Authorized as '{authorized_email}' but expected '{expected_email}'.\n"
            "Re-run and sign in with the correct Google account."
        )
    if not expected_email:
        print(
            f"! No expected email configured for '{account}'. "
            "Set GOOGLE_MCP_PERSONAL_EMAIL / GOOGLE_MCP_WORK_EMAIL to enforce account checks."
        )

    if not creds.refresh_token:
        if existing_token:
            # Expected on rerun without prompt=consent: Google omits the refresh
            # token because the client already has one. Keep the Keychain value.
            print(f"✓ Reauthorized as: {authorized_email}")
            print(f"✓ Existing refresh token in Keychain ('{service_name}') retained")
            return
        raise SystemExit(
            "ERROR: No refresh token returned on first-time authorization. "
            "Revoke access at https://myaccount.google.com/permissions and re-run."
        )

    keyring.set_password(service_name, "refresh_token", creds.refresh_token)

    print(f"✓ Authorized as: {authorized_email}")
    print(f"✓ Refresh token stored in macOS Keychain under '{service_name}'")


if __name__ == "__main__":
    main()
