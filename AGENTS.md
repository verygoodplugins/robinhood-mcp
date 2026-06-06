# AGENTS.md

This file provides guidance to coding agents (Claude Code, Cursor, Codex, etc.) when working with this repository. It is the single source of truth; `CLAUDE.md` imports it via `@AGENTS.md`.

## Project Overview

**robinhood-mcp** is a **read-only** MCP (Model Context Protocol) server that wraps the [`robin_stocks`](https://github.com/jmfernandes/robin_stocks) Python library to expose Robinhood portfolio data as research tools for AI assistants. It is strictly a research/educational tool — **no trading functionality is exposed**.

**Core purpose:**
- Translate MCP tool calls into `robin_stocks` Robinhood API requests over stdio
- Provide read-only portfolio, quote, fundamentals, news, and order-history research
- Support multi-account Robinhood logins (taxable, IRA, etc.) via optional account selection

### Read-only is a hard invariant

The server **never** exposes order placement, cancellation, or any account-modifying call. There are no `order_buy_*`, `order_sell_*`, or `cancel_*` tools, and none should ever be added. Every tool delegates to read-only `robin_stocks` endpoints (`rh.profiles.*`, `rh.stocks.*`, `rh.account.*` getters, `rh.orders.get_all_stock_orders`, `rh.options.get_open_option_positions`). When adding a tool, preserve this invariant; the order-history tool explicitly documents "Read-only — this never places or cancels orders" (`tools.py:639`).

## Build & Development

```bash
# Install with dev dependencies (editable)
pip install -e ".[dev]"

# Lint and format-check (ruff; line-length 100, target py311)
ruff check .
ruff format --check .

# Run tests
pytest -v

# Run tests with coverage
pytest --cov=src --cov-report=html

# Smoke test (import + server instantiation + entry point)
./scripts/smoke.sh

# Run the MCP server (stdio mode)
robinhood-mcp
```

`robinhood-mcp` is the console-script entry point, wired to `robinhood_mcp.server:main` (`pyproject.toml:36-37`). Python **>= 3.11** is required (`pyproject.toml:11`). Runtime dependencies: `fastmcp`, `robin_stocks`, `python-dotenv`, `pyotp` (`pyproject.toml:21-26`).

## Commit & PR Standards

This repo uses **Conventional Commits** so [release-please](https://github.com/googleapis/release-please) can generate releases and PyPI publishes reliably.

- PR titles **must** be Conventional Commit format. The repo squash-merges, so the PR title becomes the merge commit and feeds release-please. This is enforced in CI by `.github/workflows/pr-title.yml` (there is no local Husky/Commitlint hook).
- Allowed prefixes (`pr-title.yml:23`): `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `build`, `ci`, `revert`.
- Use `!` (e.g. `feat!:`) for breaking changes → major bump. `feat:` → minor, `fix:` → patch, `chore`/`docs` → no bump.
- Subjects are imperative mood (e.g. `feat(auth): add TOTP support`, `fix: harden push approval auth flow`).

Accepted examples:
```text
feat(accounts): support Robinhood account selection
fix(auth): cache login failures and bound device-approval poll
docs: clarify TOTP setup
chore(deps): bump robin_stocks
```

### CI gates

Every PR to `main` runs (`.github/workflows/`):

- **CI** (`ci.yml`): `Python Lint` (`ruff check .` + `ruff format --check .`), `Python Tests` (`pytest --cov` + `./scripts/smoke.sh`). The `Go Lint`/`Go Build` jobs auto-skip because there are no `.go` files.
- **Security** (`security.yml`): `CodeQL Analysis` (Python) is blocking; `Dependency Audit` (`pip-audit`) and `Bandit Security Scan` are informational (`continue-on-error: true`).
- **PR Title** (`pr-title.yml`): Conventional Commit title check.

Run `ruff check .`, `ruff format --check .`, and `pytest` locally before pushing.

## Publishing

Releases are **release-please driven** — do **not** hand-edit `CHANGELOG.md` or version numbers, and do **not** cut release tags manually.

1. Pushes to `main` with conventional commits open/update a Release PR (`release.yml`, `googleapis/release-please-action@v4`).
2. Merging the Release PR bumps the version in `pyproject.toml`, `__init__.py` (`# x-release-please-version`), and `server.json`, updates `CHANGELOG.md`, and creates a GitHub Release + tag.
3. The release triggers the `pypi-publish` job, which builds the package and publishes to PyPI via **Trusted Publishing (OIDC)** — no PyPI token (`release.yml:51-76`, `id-token: write`).

## Architecture

```
┌──────────────────────────────────────────┐
│  MCP Client (Claude Code / Cursor / etc.) │
│  - Calls MCP tools over stdio             │
└─────────────┬────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────┐
│  robinhood-mcp Server (this Python app)   │
│  - FastMCP; @mcp.tool() registrations     │
│  - Lazy login + session/auth caching      │
│  - Translates tool calls → robin_stocks   │
└─────────────┬────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────┐
│  robin_stocks → Robinhood REST API        │
│  - Read-only endpoints only               │
│  - Session cached in ~/.tokens/*.pickle   │
└──────────────────────────────────────────┘
```

### Code Organization

```
src/robinhood_mcp/
├── __init__.py   # Package version (release-please managed)
├── auth.py       # Login, TOTP, device-approval workflow, monkey-patch, env reads
├── tools.py      # Read-only tool implementations + caching + validation
└── server.py     # FastMCP server; @mcp.tool() registration + login gating
```

- **`server.py`** — Initializes `FastMCP("robinhood-mcp")`, registers all tools with `@mcp.tool()`, and gates every tool behind `_ensure_logged_in()`. Each MCP tool is a thin wrapper delegating to the matching `tools.py` function. `main()` calls `mcp.run()`.
- **`tools.py`** — Pure read-only wrappers over `robin_stocks`, all routed through `_safe_call()` for uniform error handling (raises `RobinhoodError`). Adds input validation (`_normalize_symbol`, `_normalize_account_number`), a 30-second positions cache (`_POSITIONS_CACHE_TTL_SECONDS`, `tools.py:19`), an unbounded instrument-URL→symbol cache, and response slimming to reduce LLM context bloat.
- **`auth.py`** — Reads credentials from env, generates TOTP codes (`pyotp`), and handles the Robinhood `verification_workflow` device-approval flow. It **monkey-patches** `robin_stocks`' broken `_validate_sherrif_id` at import time (`auth.py:198-216`) with a polling-based version that never calls `input()` (the upstream version blocks forever on headless servers). It also captures `robin_stocks` stdout and redirects it to stderr so it cannot corrupt the stdio JSON-RPC transport (`auth.py:254-268`).

## MCP Tools

The server registers **15 read-only tools**, all prefixed `robinhood_`. Cross-checked three ways: 15 `@mcp.tool()` decorators in `server.py` (lines 134, 145, 159, 173, 188, 201, 215, 229, 248, 262, 276, 290, 304, 318, 348), 15 implementations in `tools.py`, and 15 entries in `server.json:22-83`. None place or cancel orders.

1. **robinhood_get_accounts** — List available accounts (account number, type, state, cash) for `account_number` selection across multi-account logins. (`server.py:134`)
2. **robinhood_get_portfolio** — Portfolio value and performance metrics. Optional `account_number`. (`server.py:145`)
3. **robinhood_get_positions** — All current stock positions (slimmed to price, quantity, average buy price, equity, percent/equity change). Optional `account_number`. (`server.py:159`)
4. **robinhood_get_position** — One position by `symbol` via a faster single-symbol lookup; returns `held=False` if absent. Optional `account_number`. (`server.py:173`)
5. **robinhood_get_watchlist** — Stocks in a watchlist (`name`, default `"Default"`). (`server.py:188`)
6. **robinhood_get_quote** — Real-time quote for a `symbol`. (`server.py:201`)
7. **robinhood_get_fundamentals** — Fundamentals (P/E, market cap, dividend yield, 52-week range) for a `symbol`. (`server.py:215`)
8. **robinhood_get_historicals** — OHLCV history for a `symbol`. `interval` ∈ {`5minute`,`10minute`,`hour`,`day`,`week`} (default `day`); `span` ∈ {`day`,`week`,`month`,`3month`,`year`,`5year`} (default `month`). (`server.py:229`)
9. **robinhood_get_news** — Recent news articles for a `symbol`. (`server.py:248`)
10. **robinhood_get_earnings** — Earnings reports/estimates for a `symbol`. (`server.py:262`)
11. **robinhood_get_ratings** — Analyst ratings summary for a `symbol`. (`server.py:276`)
12. **robinhood_get_dividends** — Dividend payment history. Optional `account_number` (omit for all). (`server.py:290`)
13. **robinhood_get_options_positions** — Current options positions (read-only). Optional `account_number`. (`server.py:304`)
14. **robinhood_get_order_history** — Executed stock order history (the trade history that built current holdings). Args: `symbol` (optional filter), `state` ∈ {`executed` (default),`all`}, `limit` (default `50`), `start_date` (`YYYY-MM-DD`), `account_number`. Read-only — never places or cancels orders. (`server.py:318`)
15. **robinhood_search_symbols** — Search instruments by company name or partial ticker (`query`). (`server.py:348`)

## Environment Variables

All credentials are read in `auth.py` (loaded from the environment or a local `.env` via `python-dotenv`). `.env.example` covers only the first three — `ROBINHOOD_APPROVAL_TIMEOUT` is read from code but not listed there.

| Variable | Required | Default | Purpose / where read |
|---|---|---|---|
| `ROBINHOOD_USERNAME` | Yes | — | Robinhood account email. Read at `auth.py:291`; missing username/password raises `EnvironmentVariablesError` at `auth.py:295`. |
| `ROBINHOOD_PASSWORD` | Yes | — | Robinhood account password. Read at `auth.py:292`. |
| `ROBINHOOD_TOTP_SECRET` | Recommended | — (unset) | Base32 TOTP secret for non-interactive 2FA. Read at `auth.py:293`. Strongly recommended for Claude Desktop / headless use — without it, fresh logins fall back to mobile-app push approval, which synchronously blocks the single-threaded server. |
| `ROBINHOOD_APPROVAL_TIMEOUT` | No | `60` seconds | Seconds to wait for mobile-app push approval. Read at `auth.py:45`; default constant `_DEFAULT_APPROVAL_TIMEOUT_SECONDS = 60.0` (`auth.py:39`). Clamped to a `5.0`s floor (`_MIN_APPROVAL_TIMEOUT_SECONDS`, `auth.py:40`/`:57`); non-numeric values warn and fall back to the default (`auth.py:50-56`). |

## Authentication & Session

- **Lazy login.** Authentication happens on the first tool call, not at server startup, via `_ensure_logged_in()` (`server.py:79`).
- **Session cache.** On first successful login the session token is cached in `~/.tokens/robinhood.pickle` (`auth.py:236`); subsequent restarts reuse it without 2FA interaction. A failed login clears this stale pickle (`_clear_stale_pickle`).
- **Login-status cache.** `is_logged_in()` results are memoized for `_LOGIN_STATUS_TTL_SECONDS = 5.0` (`server.py:50`) to avoid probing Robinhood on every call.
- **Auth-failure cooldown.** `_ensure_logged_in()` caches transient `AuthenticationError` failures for **300 seconds** (`_AUTH_FAILURE_COOLDOWN_SECONDS = 300.0`, `server.py:59`) so subsequent tool calls fail fast instead of re-running the full login flow (which can block the single-threaded server for tens of seconds while polling for device approval). After the cooldown one fresh attempt is allowed; restarting the client clears it immediately. `EnvironmentVariablesError` (missing creds) is treated as **permanent** — restart after fixing config (`server.py:86-131`).

## Testing

Tests live in `tests/` (`test_auth.py`, `test_server.py`, `test_tools.py`) and run against **mocked** `robin_stocks` responses — no real credentials or network needed (`[tool.pytest.ini_options]` sets `testpaths = ["tests"]`, `asyncio_mode = "auto"` in `pyproject.toml:46-48`).

```bash
pytest -v                          # full suite (mocked)
pytest --cov=src --cov-report=html # with coverage
./scripts/smoke.sh                 # import + server instantiation check
```

## Adding a New Tool

1. Implement the read-only function in `tools.py` with type hints, input validation, and `_safe_call()` for the `robin_stocks` call.
2. Register a thin wrapper in `server.py` with the `@mcp.tool()` decorator and a docstring (the docstring is the tool description shown to agents); call `_ensure_logged_in()` first and delegate to the `tools.py` function.
3. Add tests in `tests/test_tools.py` (and `tests/test_server.py` if registration behavior matters).
4. Add the tool to the `tools` array in `server.json`.
5. Update the README tool table.
6. **Never** add a write/trade endpoint — keep the read-only invariant intact.

## Safety Reminders

- **Never** expose trading functions (`order_buy_*`, `order_sell_*`, `cancel_*`, or any account-modifying call).
- **Never** log credentials. `robin_stocks` stdout is captured and redirected to stderr to keep secrets and chatter off the JSON-RPC transport.
- **Always** validate user input (symbols via `_normalize_symbol`, account numbers via `_normalize_account_number`).
- Keep session tokens secure — they are stored in `~/.tokens/`.
