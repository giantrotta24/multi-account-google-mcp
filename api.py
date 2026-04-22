"""Google API wrappers used by MCP tools."""
from __future__ import annotations

import json
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError


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
        return {
            "ok": False,
            "error": "auth failed — run auth_setup.py personal or work",
            "code": 401,
        }
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
    """Search Gmail and return message summaries."""
    from google.auth.exceptions import RefreshError
    from googleapiclient.discovery import build

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
                h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])
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
    calendar_names: list[str] | None = None,
) -> dict[str, Any]:
    """List calendar events across all owned and writable calendars."""
    from google.auth.exceptions import RefreshError
    from googleapiclient.discovery import build

    max_results = min(max_results, 100)

    try:
        service = build("calendar", "v3", credentials=creds)

        all_calendars: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            response = service.calendarList().list(pageToken=page_token).execute(num_retries=3)
            all_calendars.extend(response.get("items", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        owned_calendars = [
            cal for cal in all_calendars if cal.get("accessRole") in ("owner", "writer")
        ]

        if calendar_names is not None:
            owned_calendars = [
                cal
                for cal in owned_calendars
                if cal.get("summary", "") in calendar_names or cal.get("id", "") in calendar_names
            ]

        results: list[dict[str, Any]] = []

        for cal in owned_calendars:
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
                            "start": start_raw.get("date")
                            if all_day
                            else start_raw.get("dateTime", ""),
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

