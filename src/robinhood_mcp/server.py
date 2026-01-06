"""FastMCP server for Robinhood portfolio research."""

import sys
from typing import Literal

from dotenv import load_dotenv
from fastmcp import FastMCP

from .auth import AuthenticationError, is_logged_in, login
from .tools import (
    RobinhoodError,
    get_dividends,
    get_earnings,
    get_fundamentals,
    get_historicals,
    get_news,
    get_options_positions,
    get_portfolio,
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


def _ensure_logged_in() -> None:
    """Ensure we're logged in before API calls."""
    global _login_attempted, _login_error

    if not _login_attempted:
        _login_attempted = True
        try:
            login()
            print("Logged in to Robinhood", file=sys.stderr)
        except AuthenticationError as e:
            _login_error = str(e)
            print(f"Login failed: {e}", file=sys.stderr)

    if _login_error:
        raise RobinhoodError(f"Not logged in: {_login_error}")

    if not is_logged_in():
        raise RobinhoodError("Session expired. Please restart the server.")


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
