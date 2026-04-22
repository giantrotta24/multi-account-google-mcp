"""MCP tool handlers and server wiring."""
from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from api import calendar_events, gmail_search
from auth import load_credentials
from config import Account, WORK_CALENDAR_FILTER_ENV

mcp = FastMCP("google-multi-account")


def _load_or_error(account: Account):
    """Return credentials or an error envelope if Keychain lookup fails."""
    try:
        return load_credentials(account)
    except RuntimeError as e:
        return {"ok": False, "error": str(e), "code": 401}


def _work_calendar_filters() -> list[str] | None:
    """Return optional work calendar filter from env."""
    raw = os.getenv(WORK_CALENDAR_FILTER_ENV, "").strip()
    return [raw] if raw else None


@mcp.tool()
def gmail_search_personal(query: str, max_results: int = 20) -> dict[str, Any]:
    """Search Gmail for the configured personal account."""
    result = _load_or_error("personal")
    if isinstance(result, dict):
        return result
    return gmail_search(result, query, max_results)


@mcp.tool()
def gmail_search_work(query: str, max_results: int = 20) -> dict[str, Any]:
    """Search Gmail for the configured work account."""
    result = _load_or_error("work")
    if isinstance(result, dict):
        return result
    return gmail_search(result, query, max_results)


@mcp.tool()
def calendar_events_personal(time_min: str, time_max: str, max_results: int = 50) -> dict[str, Any]:
    """List events for the configured personal account calendars."""
    result = _load_or_error("personal")
    if isinstance(result, dict):
        return result
    return calendar_events(result, time_min, time_max, max_results)


@mcp.tool()
def calendar_events_work(time_min: str, time_max: str, max_results: int = 50) -> dict[str, Any]:
    """List events for the configured work account calendars."""
    result = _load_or_error("work")
    if isinstance(result, dict):
        return result
    return calendar_events(
        result,
        time_min,
        time_max,
        max_results,
        calendar_names=_work_calendar_filters(),
    )

