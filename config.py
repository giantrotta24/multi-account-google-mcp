"""Shared configuration for the google-mcp server."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

_HERE = Path(__file__).parent
CREDENTIALS_PATH = _HERE / "credentials.json"

Account = Literal["personal", "work"]

KEYCHAIN_SERVICES: dict[Account, str] = {
    "personal": "google-mcp-personal",
    "work": "google-mcp-work",
}

# Narrowest scopes covering the four tools: Gmail metadata/snippet search,
# calendar listing (to filter by accessRole), and event reads.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
]

ACCOUNT_EMAIL_ENVS: dict[Account, str] = {
    "personal": "GOOGLE_MCP_PERSONAL_EMAIL",
    "work": "GOOGLE_MCP_WORK_EMAIL",
}

WORK_CALENDAR_FILTER_ENV = "GOOGLE_MCP_WORK_CALENDAR"


def get_expected_email(account: Account) -> str | None:
    """Return expected email for account from environment, if configured."""
    env_name = ACCOUNT_EMAIL_ENVS[account]
    value = os.getenv(env_name, "").strip()
    return value or None

