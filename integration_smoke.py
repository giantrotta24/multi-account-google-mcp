"""
Integration smoke tests for google-mcp.

Calls real Google APIs and mutates local keychain credentials during one test.

Usage:
    RUN_LIVE_TESTS=1 uv --directory ~/Code/google-mcp run integration_smoke.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import keyring

from server import calendar_events, gmail_search, load_credentials


def _check(label: str, result: dict) -> bool:
    """Print pass/fail for a tool result and return True if ok."""
    if not result.get("ok"):
        error = result.get("error", "<no error field>")
        code = result.get("code", "<no code>")
        print(f"  FAIL {label}: code={code} error={error!r}")
        return False
    print(f"  PASS {label} ({len(result['data'])} results)")
    return True


def _require_live_flag() -> None:
    if os.getenv("RUN_LIVE_TESTS") != "1":
        raise SystemExit(
            "Refusing to run live integration tests.\n"
            "Set RUN_LIVE_TESTS=1 to confirm you intend to hit real APIs."
        )


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
    """Verify missing keychain credential surfaces a helpful RuntimeError."""
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
        if original is not None:
            keyring.set_password("google-mcp-personal", "refresh_token", original)


if __name__ == "__main__":
    _require_live_flag()

    tests = [test_auth, test_gmail, test_calendar]
    if os.getenv("RUN_DESTRUCTIVE_TESTS") == "1":
        tests.append(test_auth_failure)
    else:
        print("Skipping destructive keychain test. Set RUN_DESTRUCTIVE_TESTS=1 to include it.")

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

