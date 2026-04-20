"""
google-mcp: Multi-account Google MCP server for Claude Code.

Exposes four tools via stdio MCP protocol:
  gmail_search_personal, gmail_search_work
  calendar_events_personal, calendar_events_work

Sections:
  1. Auth     — load_credentials(account) -> Credentials
  2. API      — gmail_search(), calendar_events() (stubbed until Tasks 5-6)
  3. MCP      — tool handlers + server entrypoint (stubbed until Task 7)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import keyring
from google.oauth2.credentials import Credentials

# Reserved for Tasks 5-7. Imported now so the dependency surface is stable
# before the API + MCP handlers land.
from googleapiclient.errors import HttpError  # noqa: F401
from mcp.server.fastmcp import FastMCP  # noqa: F401

# ── Constants ──────────────────────────────────────────────────────────────

_HERE = Path(__file__).parent
CREDENTIALS_PATH = _HERE / "credentials.json"

KEYCHAIN_SERVICES: dict[str, str] = {
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

Account = Literal["personal", "work"]

# ── Auth ───────────────────────────────────────────────────────────────────


def load_credentials(account: Account) -> Credentials:
    """Load OAuth credentials from macOS Keychain for the given account.

    Args:
        account: "personal" or "work"

    Returns:
        A Credentials object ready for use with Google API clients.

    Raises:
        ValueError: If ``account`` is not a known key.
        RuntimeError: If no refresh token exists in Keychain for the account.
    """
    if account not in KEYCHAIN_SERVICES:
        raise ValueError(
            f"Invalid account {account!r}. Expected one of: {sorted(KEYCHAIN_SERVICES)}"
        )

    service_name = KEYCHAIN_SERVICES[account]
    refresh_token = keyring.get_password(service_name, "refresh_token")

    if not refresh_token:
        raise RuntimeError(
            f"No credentials found for account '{account}'. "
            f"Run: uv --directory {_HERE} run auth_setup.py {account}"
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
# gmail_search implemented in Task 5; calendar_events stubbed for Task 6.


def _parse_http_error(e: HttpError) -> dict[str, Any]:
    """Convert a Google API HttpError to the standard error envelope."""
    try:
        content = json.loads(e.content.decode())
        errors = content.get("error", {}).get("errors", [{}])
        reason = errors[0].get("reason", "") if errors else ""
    except (json.JSONDecodeError, IndexError):
        reason = ""

    code = int(e.resp.status)

    if code == 401:
        return {"ok": False, "error": "auth failed — run auth_setup.py personal or work", "code": 401}
    if reason in ("rateLimitExceeded", "userRateLimitExceeded"):
        return {"ok": False, "error": "rate limit exceeded", "code": 429}
    if code == 403:
        return {"ok": False, "error": "permission denied", "code": 403}
    return {"ok": False, "error": str(e), "code": code}


def gmail_search(
    creds: Credentials,
    query: str,
    max_results: int = 20,
) -> dict[str, Any]:
    """Search Gmail and return message summaries.

    Uses a list-then-get pattern: messages.list returns IDs only;
    messages.get (format=metadata) fetches headers and snippet per message.
    At max_results=20 this is 21 API calls — acceptable for a weekly workflow.

    Args:
        creds: Authorized Google credentials.
        query: Gmail search query string (e.g. "is:unread after:2026/04/12").
        max_results: Maximum messages to return. Hard cap: 50.

    Returns:
        {"ok": True, "data": [...]} or {"ok": False, "error": "...", "code": N}
    """
    from googleapiclient.discovery import build
    from google.auth.exceptions import RefreshError

    max_results = min(max_results, 50)

    try:
        service = build("gmail", "v1", credentials=creds)

        list_response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute(num_retries=3)
        )

        messages = list_response.get("messages", [])
        results: list[dict[str, Any]] = []

        for msg in messages:
            detail = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute(num_retries=3)
            )

            headers = {
                h["name"]: h["value"]
                for h in detail.get("payload", {}).get("headers", [])
            }

            results.append(
                {
                    "id": detail["id"],
                    "thread_id": detail["threadId"],
                    "from": headers.get("From", ""),
                    "subject": headers.get("Subject", ""),
                    "date": headers.get("Date", ""),
                    "snippet": detail.get("snippet", ""),
                    "labels": detail.get("labelIds", []),
                }
            )

        return {"ok": True, "data": results}

    except HttpError as e:
        return _parse_http_error(e)
    except RefreshError as e:
        return {"ok": False, "error": f"token refresh failed: {e}", "code": 401}
    except Exception as e:
        return {"ok": False, "error": f"upstream failure: {type(e).__name__}", "code": 503}


def calendar_events(
    creds: Credentials, time_min: str, time_max: str, max_results: int = 50
) -> dict[str, Any]:
    """Stub — implemented in Task 6."""
    raise NotImplementedError("calendar_events not yet implemented — see Task 6")


# ── MCP server ─────────────────────────────────────────────────────────────
# (implemented in Task 7)


if __name__ == "__main__":
    pass  # replaced in Task 7
