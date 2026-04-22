# google-mcp

Multi-account Google MCP server exposing Gmail and Calendar read tools over stdio.

## Security notes

- `credentials.json` is local-only and must never be committed.
- Copy `credentials.template.json` to `credentials.json` and fill it with your local OAuth client values.
- Refresh tokens are stored in your OS keychain (`keyring`), not in source control.

## Setup

1. Install dependencies:
   - `uv sync`
2. Create local OAuth client config:
   - `cp credentials.template.json credentials.json`
3. Set expected account emails (optional but recommended for auth safety checks):
   - `export GOOGLE_MCP_PERSONAL_EMAIL="you@example.com"`
   - `export GOOGLE_MCP_WORK_EMAIL="you@company.com"`
4. Optionally set a specific work calendar filter:
   - `export GOOGLE_MCP_WORK_CALENDAR="calendar-id-or-summary"`
5. Authorize each account:
   - `uv run auth_setup.py personal`
   - `uv run auth_setup.py work`

## Run server

- `uv run server.py`

## Integration tests

These hit real Google APIs.

- Basic live tests:
  - `RUN_LIVE_TESTS=1 uv run integration_smoke.py`
- Include destructive keychain mutation test:
  - `RUN_LIVE_TESTS=1 RUN_DESTRUCTIVE_TESTS=1 uv run integration_smoke.py`

## Publish safety checks

- Run local security guardrail:
  - `python scripts/security_check.py`
- Optional pre-commit integration:
  - `uv tool install pre-commit`
  - `pre-commit install`
  - `pre-commit run --all-files`
- CI runs the same script on every push/PR via `.github/workflows/security-check.yml`.

