"""Authentication helpers for loading Google credentials."""
from __future__ import annotations

import json

import keyring
from google.oauth2.credentials import Credentials

from config import Account, CREDENTIALS_PATH, KEYCHAIN_SERVICES, SCOPES


def load_credentials(account: Account) -> Credentials:
    """Load OAuth credentials from macOS Keychain for the given account."""
    if account not in KEYCHAIN_SERVICES:
        raise ValueError(
            f"Invalid account {account!r}. Expected one of: {sorted(KEYCHAIN_SERVICES)}"
        )

    service_name = KEYCHAIN_SERVICES[account]
    refresh_token = keyring.get_password(service_name, "refresh_token")

    if not refresh_token:
        raise RuntimeError(
            f"No credentials found for account '{account}'. "
            f"Run: uv --directory {CREDENTIALS_PATH.parent} run auth_setup.py {account}"
        )

    client_config = json.loads(CREDENTIALS_PATH.read_text())["installed"]

    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=client_config["token_uri"],
        client_id=client_config["client_id"],
        client_secret=client_config["client_secret"],
        scopes=SCOPES,
    )

