"""
google-mcp: Multi-account Google MCP server for Claude Code.

Exposes four tools via stdio MCP protocol:
  gmail_search_personal, gmail_search_work
  calendar_events_personal, calendar_events_work

Sections:
  1. Auth     — load_credentials(account) -> Credentials
  2. API      — gmail_search(), calendar_events()
  3. MCP      — tool handlers + server entrypoint
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import keyring
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError
from mcp.server.fastmcp import FastMCP

# ── Constants ──────────────────────────────────────────────────────────────

_HERE = Path(__file__).parent
CREDENTIALS_PATH = _HERE / "credentials.json"

KEYCHAIN_SERVICES: dict[str, str] = {
    "personal": "google-mcp-personal",
    "work": "google-mcp-work",
}

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# ── Auth ───────────────────────────────────────────────────────────────────


def load_credentials(account: str) -> Credentials:
    """Load OAuth credentials from macOS Keychain for the given account.

    Args:
        account: "personal" or "work"

    Returns:
        A Credentials object ready for use with Google API clients.

    Raises:
        RuntimeError: If no refresh token exists in Keychain for the account.
    """
    service_name = KEYCHAIN_SERVICES[account]
    refresh_token = keyring.get_password(service_name, "refresh_token")

    if not refresh_token:
        raise RuntimeError(
            f"No credentials found for account '{account}'. "
            f"Run: uv --directory ~/Code/google-mcp run auth_setup.py {account}"
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


# ── API functions ──────────────────────────────────────────────────────────
# Stubs — replaced in Tasks 5 and 6. Present here so smoke_test.py can import
# server.py without AttributeError before implementation exists.


def gmail_search(
    creds: Credentials, query: str, max_results: int = 20
) -> dict[str, Any]:
    """Stub — implemented in Task 5."""
    raise NotImplementedError("gmail_search not yet implemented — see Task 5")


def calendar_events(
    creds: Credentials, time_min: str, time_max: str, max_results: int = 50
) -> dict[str, Any]:
    """Stub — implemented in Task 6."""
    raise NotImplementedError("calendar_events not yet implemented — see Task 6")


# ── MCP server ─────────────────────────────────────────────────────────────
# (implemented in Task 7)


if __name__ == "__main__":
    pass  # replaced in Task 7
