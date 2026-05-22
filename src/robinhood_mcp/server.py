"""FastMCP server for Robinhood portfolio research."""

import math
import sys
import threading
import time
from typing import Literal

from dotenv import load_dotenv
from fastmcp import FastMCP

from .auth import AuthenticationError, EnvironmentVariablesError, is_logged_in, login
from .tools import (
    RobinhoodError,
    get_dividends,
    get_earnings,
    get_fundamentals,
    get_historicals,
    get_news,
    get_options_positions,
    get_order_history,
    get_portfolio,
    get_position,
    get_positions,
    get_quote,
    get_ratings,
    get_watchlist,
    search_symbols,
)

# Load environment variables
load_dotenv()

# Initialize FastMCP server (older versions don't accept description kwarg).
try:
    mcp = FastMCP(
        "robinhood-mcp",
        description="Read-only research tools for Robinhood portfolio data",
    )
except TypeError:
    mcp = FastMCP("robinhood-mcp")

# Track login state
_login_attempted = False
_login_error: str | None = None
_login_lock = threading.Lock()
_cached_login_status: bool | None = None
_cached_login_status_ts = 0.0
_LOGIN_STATUS_TTL_SECONDS = 5.0

# Cache transient AuthenticationError failures so repeated tool calls don't
# each re-run the full robin_stocks login flow — that flow can synchronously
# block the (single-threaded) MCP server for tens of seconds while polling
# for mobile-app device approval. With the cache, only the first call pays
# the cost; subsequent calls within the cooldown window fail fast.
_auth_failure_message: str | None = None
_auth_failure_ts = 0.0
_AUTH_FAILURE_COOLDOWN_SECONDS = 300.0


def _is_session_valid_cached() -> bool:
    """Return cached login status when fresh, otherwise probe Robinhood once."""
    global _cached_login_status, _cached_login_status_ts

    now = time.monotonic()
    if (
        _cached_login_status is not None
        and (now - _cached_login_status_ts) < _LOGIN_STATUS_TTL_SECONDS
    ):
        return _cached_login_status

    status = is_logged_in()
    _cached_login_status = status
    _cached_login_status_ts = now
    return status


def _ensure_logged_in() -> None:
    """Ensure we're logged in before API calls, re-attempting if session expired."""
    global _login_attempted, _login_error
    global _cached_login_status, _cached_login_status_ts
    global _auth_failure_message, _auth_failure_ts

    with _login_lock:
        # Only explicit credential/config errors are treated as permanent.
        if _login_error:
            raise RobinhoodError(f"Not logged in: {_login_error}")

        # Recent transient auth failure? Fail fast instead of re-running the
        # full login flow and freezing the server again. Cooldown clears
        # automatically so the server can recover after the user fixes things
        # (or just restarts Claude Desktop).
        if _auth_failure_message is not None:
            elapsed = time.monotonic() - _auth_failure_ts
            if elapsed < _AUTH_FAILURE_COOLDOWN_SECONDS:
                # Ceil so the message never claims "0s" while still inside
                # the cooldown — int() floors and would lie about sub-second
                # tails.
                remaining = math.ceil(_AUTH_FAILURE_COOLDOWN_SECONDS - elapsed)
                raise RobinhoodError(
                    f"Not logged in: {_auth_failure_message} "
                    f"(cached failure; will retry in {remaining}s)"
                )
            # Cooldown elapsed — allow one fresh attempt.
            _auth_failure_message = None

        session_valid = _is_session_valid_cached() if _login_attempted else False
        if not _login_attempted or not session_valid:
            _login_attempted = True
            _login_error = None
            try:
                login()
                _cached_login_status = True
                _cached_login_status_ts = time.monotonic()
                _auth_failure_message = None
                print("[robinhood-mcp] Logged in to Robinhood", file=sys.stderr)
            except EnvironmentVariablesError as e:
                _cached_login_status = False
                _cached_login_status_ts = time.monotonic()
                _login_error = str(e)
                print(f"[robinhood-mcp] Login failed: {e}", file=sys.stderr)
                raise RobinhoodError(f"Not logged in: {_login_error}") from e
            except AuthenticationError as e:
                _cached_login_status = False
                _cached_login_status_ts = time.monotonic()
                message = str(e)
                _auth_failure_message = message
                _auth_failure_ts = time.monotonic()
                print(f"[robinhood-mcp] Login failed: {e}", file=sys.stderr)
                raise RobinhoodError(f"Not logged in: {message}") from e


@mcp.tool()
def robinhood_get_portfolio() -> dict:
    """Get current portfolio value and performance metrics.

    Returns portfolio profile with equity, extended hours equity,
    withdrawable amount, and other account details.
    """
    _ensure_logged_in()
    return get_portfolio()


@mcp.tool()
def robinhood_get_positions() -> dict:
    """Get all current stock positions with details.

    Returns a dict mapping stock symbols to position details including
    price, quantity, average buy price, equity, and percent change.
    """
    _ensure_logged_in()
    return get_positions()


@mcp.tool()
def robinhood_get_position(symbol: str) -> dict:
    """Get one current stock position with a faster single-symbol lookup.

    Args:
        symbol: Stock ticker symbol (e.g., "HIMS", "AAPL")

    Returns a dict with held=False if absent, otherwise the position details
    for that symbol including quantity, price, average buy price, and P&L.
    """
    _ensure_logged_in()
    return get_position(symbol)


@mcp.tool()
def robinhood_get_watchlist(name: str = "Default") -> list:
    """Get stocks in a watchlist.

    Args:
        name: Watchlist name (default: "Default")

    Returns list of watchlist items with instrument details.
    """
    _ensure_logged_in()
    return get_watchlist(name)


@mcp.tool()
def robinhood_get_quote(symbol: str) -> dict:
    """Get real-time quote for a stock symbol.

    Args:
        symbol: Stock ticker symbol (e.g., "AAPL", "TSLA")

    Returns quote data including last trade price, bid, ask,
    previous close, and trading status.
    """
    _ensure_logged_in()
    return get_quote(symbol)


@mcp.tool()
def robinhood_get_fundamentals(symbol: str) -> dict:
    """Get fundamental data for a stock.

    Args:
        symbol: Stock ticker symbol

    Returns fundamentals including P/E ratio, market cap,
    dividend yield, 52-week high/low, and more.
    """
    _ensure_logged_in()
    return get_fundamentals(symbol)


@mcp.tool()
def robinhood_get_historicals(
    symbol: str,
    interval: Literal["5minute", "10minute", "hour", "day", "week"] = "day",
    span: Literal["day", "week", "month", "3month", "year", "5year"] = "month",
) -> list:
    """Get historical price data for a stock.

    Args:
        symbol: Stock ticker symbol
        interval: Time interval (5minute, 10minute, hour, day, week)
        span: Time span (day, week, month, 3month, year, 5year)

    Returns list of OHLCV data points (open, high, low, close, volume).
    """
    _ensure_logged_in()
    return get_historicals(symbol, interval, span)


@mcp.tool()
def robinhood_get_news(symbol: str) -> list:
    """Get recent news articles for a stock.

    Args:
        symbol: Stock ticker symbol

    Returns list of news articles with title, URL, source,
    and publication date.
    """
    _ensure_logged_in()
    return get_news(symbol)


@mcp.tool()
def robinhood_get_earnings(symbol: str) -> list:
    """Get earnings data for a stock.

    Args:
        symbol: Stock ticker symbol

    Returns list of earnings reports with EPS, report date,
    analyst estimates, and actual vs expected.
    """
    _ensure_logged_in()
    return get_earnings(symbol)


@mcp.tool()
def robinhood_get_ratings(symbol: str) -> dict:
    """Get analyst ratings summary for a stock.

    Args:
        symbol: Stock ticker symbol

    Returns ratings summary with buy, hold, sell counts,
    and overall recommendation.
    """
    _ensure_logged_in()
    return get_ratings(symbol)


@mcp.tool()
def robinhood_get_dividends() -> list:
    """Get all dividend payments received.

    Returns list of dividend payments with amount, payable date,
    record date, and instrument details.
    """
    _ensure_logged_in()
    return get_dividends()


@mcp.tool()
def robinhood_get_options_positions() -> list:
    """Get all current options positions (read-only).

    Returns list of options positions with chain symbol, type,
    strike price, expiration, and quantity.
    """
    _ensure_logged_in()
    return get_options_positions()


@mcp.tool()
def robinhood_get_order_history(
    symbol: str | None = None,
    state: Literal["executed", "all"] = "executed",
    limit: int = 50,
    start_date: str | None = None,
) -> list:
    """Get historical stock order history (executed buys and sells).

    This is your trade history - the orders that built your current holdings.
    For what you hold *now* use robinhood_get_positions; for dividend income
    use robinhood_get_dividends. Read-only: never places or cancels orders.

    Args:
        symbol: Optional ticker filter (e.g., "AAPL"). Omit for all symbols.
        state: "executed" (default) returns only orders that filled, including
            partial fills; "all" also returns cancelled/queued/rejected orders.
        limit: Maximum number of orders to return, most recent first.
        start_date: Optional "YYYY-MM-DD" lower bound, applied server-side.

    Returns a list of order rows (newest first) with symbol, side, state,
    quantity, filled quantity, average price, type, timestamps, and per-fill
    executions.
    """
    _ensure_logged_in()
    return get_order_history(symbol, state, limit, start_date)


@mcp.tool()
def robinhood_search_symbols(query: str) -> list:
    """Search for stock symbols by company name or ticker.

    Args:
        query: Search query (company name or partial ticker)

    Returns list of matching instruments with symbol, name,
    and other details.
    """
    _ensure_logged_in()
    return search_symbols(query)


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
