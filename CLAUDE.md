# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

**robinhood-mcp** is a read-only MCP server that wraps the `robin_stocks` Python library to provide research tools for Robinhood portfolio data. This is strictly a research/educational tool - no trading functionality is exposed.

## Architecture

```
src/robinhood_mcp/
├── __init__.py      # Package version
├── auth.py          # Authentication with TOTP support
├── tools.py         # 12 read-only tool implementations
└── server.py        # FastMCP server with tool registration
```

### Key Design Decisions

1. **Read-Only Only**: We explicitly do NOT expose any trading functions:
   - No `order_buy_*`, `order_sell_*`
   - No `cancel_*_order`
   - No account modification functions

2. **FastMCP**: Uses FastMCP for simpler decorator-based tool registration

3. **Lazy Authentication**: Login happens on first tool call, not server startup

4. **Error Handling**: All robin_stocks calls are wrapped with `_safe_call()` for consistent error handling

## Common Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Run linting
ruff check .
ruff format --check .

# Run tests
pytest -v

# Run with coverage
pytest --cov=src --cov-report=html

# Run the server
robinhood-mcp
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ROBINHOOD_USERNAME` | Yes | Robinhood account email |
| `ROBINHOOD_PASSWORD` | Yes | Robinhood account password |
| `ROBINHOOD_TOTP_SECRET` | No | Base32 TOTP secret for 2FA |

## Testing

Tests use mocked robin_stocks responses. To run with real credentials (careful!):

```bash
# Set env vars first
pytest tests/ -v
```

## Adding New Tools

1. Add the implementation to `tools.py` with proper type hints
2. Register in `server.py` with `@mcp.tool()` decorator
3. Add tests in `tests/test_tools.py`
4. Update `server.json` tool list
5. Update README.md tool table

## Publishing

This project uses GitHub Actions for CI/CD:

1. Push to main triggers CI (lint + test)
2. Create a version tag (e.g., `v0.1.0`) to trigger release
3. Release workflow publishes to PyPI via Trusted Publishing

## Safety Reminders

- **Never** expose trading functions
- **Never** log credentials
- **Always** validate user input (symbols, etc.)
- Keep session tokens secure (stored in `~/.tokens/`)
