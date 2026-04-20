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
from typing import Any, Literal

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


def _parse_http_error(e: HttpError) -> dict[str, Any]:
    """Convert a Google API HttpError to the standard error envelope."""
    try:
        content = json.loads(e.content.decode())
        errors = content.get("error", {}).get("errors", [{}])
        reason = errors[0].get("reason", "") if errors else ""
    except (json.JSONDecodeError, AttributeError, UnicodeDecodeError, ValueError):
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
    creds: Credentials,
    time_min: str,
    time_max: str,
    max_results: int = 50,
) -> dict[str, Any]:
    """List calendar events across all owned and writable calendars.

    Excludes read-only calendars (holidays, subscriptions, shared viewer-only).
    Normalizes all-day events (date) to YYYY-MM-DD and timed events (dateTime)
    to ISO 8601 with timezone. Results are sorted by start time.

    Note: max_results applies per calendar. With multiple owned calendars,
    total results may exceed this value. Hard cap per calendar: 100.

    Args:
        creds: Authorized Google credentials.
        time_min: ISO 8601 lower bound, e.g. "2026-04-12T00:00:00Z".
        time_max: ISO 8601 upper bound, e.g. "2026-04-26T23:59:59Z".
        max_results: Maximum events per calendar. Hard cap: 100.

    Returns:
        {"ok": True, "data": [...]} or {"ok": False, "error": "...", "code": N}
    """
    from googleapiclient.discovery import build
    from google.auth.exceptions import RefreshError

    max_results = min(max_results, 100)

    try:
        service = build("calendar", "v3", credentials=creds)

        # Paginate calendarList to handle accounts with many calendars.
        all_calendars: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            response = service.calendarList().list(pageToken=page_token).execute(num_retries=3)
            all_calendars.extend(response.get("items", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        owned_calendars = [
            cal for cal in all_calendars
            if cal.get("accessRole") in ("owner", "writer")
        ]

        results: list[dict[str, Any]] = []

        for cal in owned_calendars:
            # Paginate events within each calendar, stopping once we've hit
            # the per-calendar max_results cap. events.list(maxResults=...)
            # controls page size, NOT total results — without this guard a
            # busy calendar would return every matching event across all pages.
            events_for_calendar = 0
            events_page_token: str | None = None
            while events_for_calendar < max_results:
                remaining = max_results - events_for_calendar
                events_response = (
                    service.events()
                    .list(
                        calendarId=cal["id"],
                        timeMin=time_min,
                        timeMax=time_max,
                        maxResults=min(remaining, max_results),
                        singleEvents=True,
                        orderBy="startTime",
                        pageToken=events_page_token,
                    )
                    .execute(num_retries=3)
                )

                for event in events_response.get("items", []):
                    if events_for_calendar >= max_results:
                        break

                    start_raw = event.get("start", {})
                    end_raw = event.get("end", {})
                    all_day = "date" in start_raw and "dateTime" not in start_raw

                    attendees = [
                        {"name": a.get("displayName", ""), "email": a.get("email", "")}
                        for a in event.get("attendees", [])
                    ]

                    results.append(
                        {
                            "id": event["id"],
                            "summary": event.get("summary", ""),
                            "start": start_raw.get("date") if all_day else start_raw.get("dateTime", ""),
                            "end": end_raw.get("date") if all_day else end_raw.get("dateTime", ""),
                            "location": event.get("location"),
                            "description": event.get("description"),
                            "attendees": attendees,
                            "status": event.get("status", "confirmed"),
                            "all_day": all_day,
                        }
                    )
                    events_for_calendar += 1

                events_page_token = events_response.get("nextPageToken")
                if not events_page_token:
                    break

        results.sort(key=lambda e: e["start"] or "")
        return {"ok": True, "data": results}

    except HttpError as e:
        return _parse_http_error(e)
    except RefreshError as e:
        return {"ok": False, "error": f"token refresh failed: {e}", "code": 401}
    except Exception as e:
        return {"ok": False, "error": f"upstream failure: {type(e).__name__}", "code": 503}


# ── MCP server ─────────────────────────────────────────────────────────────

mcp = FastMCP("google-multi-account")


def _load_or_error(account: Account) -> Credentials | dict[str, Any]:
    """Return credentials or an error envelope if Keychain lookup fails."""
    try:
        return load_credentials(account)
    except RuntimeError as e:
        return {"ok": False, "error": str(e), "code": 401}


@mcp.tool()
def gmail_search_personal(query: str, max_results: int = 20) -> dict[str, Any]:
    """Search Gmail for giantrotta24@gmail.com.

    Use this tool when the user asks about email in their personal inbox — unread, from a specific sender, mentioning a topic, in a date range, etc.

    Args:
        query: Gmail search syntax. Common operators:
            - is:unread, is:read, is:starred, is:important
            - from:alice@example.com, to:me, cc:bob@example.com
            - subject:"project kickoff"
            - after:YYYY/MM/DD, before:YYYY/MM/DD (e.g. "after:2026/04/12")
            - has:attachment, filename:pdf
            - label:inbox, in:anywhere
            - Combine with space (AND) or OR: "is:unread after:2026/04/12"
        max_results: Max messages to return (default 20, cap 50).

    Returns:
        {"ok": True, "data": [{id, thread_id, from, subject, date, snippet, labels}, ...]}
        or {"ok": False, "error": "...", "code": N}
    """
    result = _load_or_error("personal")
    if isinstance(result, dict):
        return result
    return gmail_search(result, query, max_results)


@mcp.tool()
def gmail_search_work(query: str, max_results: int = 20) -> dict[str, Any]:
    """Search Gmail for gian@rvshare.com.

    Use this tool when the user asks about email in their work inbox — unread, from a specific sender, mentioning a topic, in a date range, etc.

    Args:
        query: Gmail search syntax. Common operators:
            - is:unread, is:read, is:starred, is:important
            - from:alice@example.com, to:me, cc:bob@example.com
            - subject:"project kickoff"
            - after:YYYY/MM/DD, before:YYYY/MM/DD (e.g. "after:2026/04/12")
            - has:attachment, filename:pdf
            - label:inbox, in:anywhere
            - Combine with space (AND) or OR: "is:unread after:2026/04/12"
        max_results: Max messages to return (default 20, cap 50).

    Returns:
        {"ok": True, "data": [{id, thread_id, from, subject, date, snippet, labels}, ...]}
        or {"ok": False, "error": "...", "code": N}
    """
    result = _load_or_error("work")
    if isinstance(result, dict):
        return result
    return gmail_search(result, query, max_results)


@mcp.tool()
def calendar_events_personal(time_min: str, time_max: str, max_results: int = 50) -> dict[str, Any]:
    """List calendar events for giantrotta24@gmail.com.

    Use this tool when the user asks about meetings or events on their personal calendar within a date range. Returns events from all owned/writable calendars — excludes read-only calendars like holidays and subscriptions.

    Args:
        time_min: ISO 8601 lower bound, e.g. "2026-04-12T00:00:00Z".
        time_max: ISO 8601 upper bound, e.g. "2026-04-26T23:59:59Z".
        max_results: Max events per calendar (default 50, cap 100). Total
            results may exceed this if the user has multiple calendars.

    Returns:
        {"ok": True, "data": [{id, summary, start, end, location, description, attendees, status, all_day}, ...]}
        or {"ok": False, "error": "...", "code": N}
    """
    result = _load_or_error("personal")
    if isinstance(result, dict):
        return result
    return calendar_events(result, time_min, time_max, max_results)


@mcp.tool()
def calendar_events_work(time_min: str, time_max: str, max_results: int = 50) -> dict[str, Any]:
    """List calendar events for gian@rvshare.com.

    Use this tool when the user asks about meetings or events on their work calendar within a date range. Returns events from all owned/writable calendars — excludes read-only calendars like holidays and subscriptions.

    Args:
        time_min: ISO 8601 lower bound, e.g. "2026-04-12T00:00:00Z".
        time_max: ISO 8601 upper bound, e.g. "2026-04-26T23:59:59Z".
        max_results: Max events per calendar (default 50, cap 100). Total
            results may exceed this if the user has multiple calendars.

    Returns:
        {"ok": True, "data": [{id, summary, start, end, location, description, attendees, status, all_day}, ...]}
        or {"ok": False, "error": "...", "code": N}
    """
    result = _load_or_error("work")
    if isinstance(result, dict):
        return result
    return calendar_events(result, time_min, time_max, max_results)


if __name__ == "__main__":
    mcp.run(transport="stdio")
