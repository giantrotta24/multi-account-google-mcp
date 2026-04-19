"""
Integration smoke tests for google-mcp.
Calls real Google APIs — requires auth_setup.py to have been run for both accounts.

Usage:
    uv --directory ~/Code/google-mcp run smoke_test.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import keyring

from server import calendar_events, gmail_search, load_credentials


def _check(label: str, result: dict) -> bool:
    """Print pass/fail for a tool result and return True if ok."""
    if not result.get("ok"):
        print(f"  FAIL {label}: {result}")
        return False
    print(f"  PASS {label} ({len(result['data'])} results)")
    return True


def test_auth() -> None:
    """Verify credentials load without error for both accounts."""
    for account in ("personal", "work"):
        creds = load_credentials(account)
        assert creds is not None, f"load_credentials('{account}') returned None"
        print(f"  PASS load_credentials({account!r})")


def test_gmail() -> None:
    """Verify gmail_search returns correct envelope and field schema for both accounts."""
    for account in ("personal", "work"):
        creds = load_credentials(account)
        result = gmail_search(creds, query="is:inbox", max_results=5)
        assert _check(f"gmail_search({account!r})", result), f"gmail_search failed for {account}"
        for msg in result["data"]:
            for field in ("id", "thread_id", "from", "subject", "date", "snippet", "labels"):
                assert field in msg, f"Missing field '{field}' in gmail result for {account}"
    print("  PASS gmail field schema")


def test_calendar() -> None:
    """Verify calendar_events returns correct envelope, schema, and all-day normalization."""
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=7)).isoformat()
    time_max = (now + timedelta(days=7)).isoformat()

    for account in ("personal", "work"):
        creds = load_credentials(account)
        result = calendar_events(
            creds, time_min=time_min, time_max=time_max, max_results=10
        )
        assert _check(f"calendar_events({account!r})", result), f"calendar_events failed for {account}"
        for event in result["data"]:
            for field in ("id", "summary", "start", "end", "status", "all_day"):
                assert field in event, f"Missing field '{field}' in calendar result for {account}"
            if event["all_day"]:
                assert len(event["start"]) == 10, (
                    f"All-day start must be YYYY-MM-DD, got: {event['start']!r}"
                )
            else:
                assert "T" in event["start"], (
                    f"Timed event start must be ISO 8601 with T, got: {event['start']!r}"
                )
    print("  PASS calendar field schema and all-day normalization")


def test_auth_failure() -> None:
    """Verify a missing Keychain credential surfaces a helpful RuntimeError."""
    original = keyring.get_password("google-mcp-personal", "refresh_token")
    keyring.delete_password("google-mcp-personal", "refresh_token")
    try:
        load_credentials("personal")
        assert False, "Expected RuntimeError for missing credential"
    except RuntimeError as e:
        assert "auth_setup.py" in str(e), (
            f"Error message must mention auth_setup.py, got: {e}"
        )
        print("  PASS auth_failure raises RuntimeError with remediation hint")
    finally:
        if original:
            keyring.set_password("google-mcp-personal", "refresh_token", original)


if __name__ == "__main__":
    tests = [test_auth, test_gmail, test_calendar, test_auth_failure]
    passed = 0
    failed = 0

    for test in tests:
        print(f"\n▶ {test.__name__}")
        try:
            test()
            passed += 1
        except Exception as exc:
            print(f"  FAIL: {exc}")
            failed += 1

    print(f"\n{'─' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
