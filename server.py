"""Server entrypoint with backward-compatible exports."""
from __future__ import annotations

from api import calendar_events, gmail_search
from auth import load_credentials
from config import KEYCHAIN_SERVICES, SCOPES
from tools import mcp

__all__ = [
    "KEYCHAIN_SERVICES",
    "SCOPES",
    "load_credentials",
    "gmail_search",
    "calendar_events",
    "mcp",
]


if __name__ == "__main__":
    mcp.run(transport="stdio")
