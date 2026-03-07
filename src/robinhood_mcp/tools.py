"""Read-only Robinhood tools wrapping robin_stocks library."""

import threading
import time
from collections.abc import Callable
from copy import deepcopy
from typing import Any, Literal

import robin_stocks.robinhood as rh


class RobinhoodError(Exception):
    """Error from Robinhood API call."""

    pass


_POSITIONS_CACHE_TTL_SECONDS = 30.0
_positions_cache_lock = threading.Lock()
_positions_cache: dict[str, dict[str, Any]] | None = None
_positions_cache_ts = 0.0


def _safe_call(func: Callable[..., Any], *args, **kwargs) -> Any:
    """Safely call a robin_stocks function with error handling.

    Args:
        func: The robin_stocks function to call.
        *args: Positional arguments.
        **kwargs: Keyword arguments.

    Returns:
        The function result.

    Raises:
        RobinhoodError: If the call fails.
    """
    try:
        result = func(*args, **kwargs)
        if result is None:
            raise RobinhoodError("API returned None - you may need to login first")
        return result
    except RobinhoodError:
        raise
    except Exception as e:
        raise RobinhoodError(f"API call failed: {e}") from e


def _normalize_symbol(symbol: str) -> str:
    """Normalize and validate ticker symbols."""
    if not symbol or not isinstance(symbol, str):
        raise RobinhoodError("Symbol must be a non-empty string")
    symbol = symbol.upper().strip()
    if not symbol:
        raise RobinhoodError("Symbol must be a non-empty string")
    return symbol


def _clear_positions_cache() -> None:
    """Reset the cached holdings snapshot."""
    global _positions_cache, _positions_cache_ts

    with _positions_cache_lock:
        _positions_cache = None
        _positions_cache_ts = 0.0


def _get_positions_cached(now: float) -> dict[str, dict[str, Any]] | None:
    """Return cached holdings when still fresh."""
    global _positions_cache, _positions_cache_ts

    with _positions_cache_lock:
        if _positions_cache is None:
            return None
        if (now - _positions_cache_ts) >= _POSITIONS_CACHE_TTL_SECONDS:
            _positions_cache = None
            _positions_cache_ts = 0.0
            return None
        return deepcopy(_positions_cache)


def _set_positions_cache(positions: dict[str, dict[str, Any]], now: float) -> None:
    """Store a fresh holdings snapshot for subsequent reads."""
    global _positions_cache, _positions_cache_ts

    with _positions_cache_lock:
        _positions_cache = deepcopy(positions)
        _positions_cache_ts = now


def get_portfolio() -> dict[str, Any]:
    """Get current portfolio value and performance metrics.

    Returns:
        Portfolio profile with equity, extended hours equity, market value, etc.
    """
    return _safe_call(rh.profiles.load_portfolio_profile)


def get_positions() -> dict[str, dict[str, Any]]:
    """Get all current stock positions with details.

    Returns:
        Dict mapping symbol to position details including:
        - price, quantity, average_buy_price
        - equity, percent_change, equity_change
    """
    global _positions_cache, _positions_cache_ts

    now = time.monotonic()
    cached = _get_positions_cached(now)
    if cached is not None:
        return cached

    with _positions_cache_lock:
        now = time.monotonic()
        if _positions_cache is not None and (
            now - _positions_cache_ts
        ) < _POSITIONS_CACHE_TTL_SECONDS:
            return deepcopy(_positions_cache)

        result = _safe_call(rh.account.build_holdings)
        if isinstance(result, dict):
            _positions_cache = deepcopy(result)
            _positions_cache_ts = time.monotonic()
        return result


def get_position(symbol: str) -> dict[str, Any]:
    """Get a single position by symbol without rebuilding all holdings.

    Returns:
        Dict with held=False if absent, otherwise position details including
        price, quantity, average_buy_price, equity, percent_change, and equity_change.
    """
    symbol = _normalize_symbol(symbol)
    cached_positions = _get_positions_cached(time.monotonic())
    if cached_positions is not None:
        cached_position = cached_positions.get(symbol)
        if isinstance(cached_position, dict):
            return {"symbol": symbol, "held": True, **cached_position}
        return {"symbol": symbol, "held": False}

    instruments = _safe_call(rh.stocks.get_instruments_by_symbols, symbol)
    if not isinstance(instruments, list) or not instruments or not isinstance(instruments[0], dict):
        return {"symbol": symbol, "held": False}

    instrument_url = instruments[0].get("url")
    if not instrument_url:
        raise RobinhoodError(f"No instrument found for symbol: {symbol}")

    positions = _safe_call(rh.account.get_open_stock_positions)
    if not isinstance(positions, list):
        raise RobinhoodError("Unexpected positions response type")

    match = next(
        (
            item
            for item in positions
            if isinstance(item, dict) and item.get("instrument") == instrument_url
        ),
        None,
    )
    if not match:
        return {"symbol": symbol, "held": False}

    quote = get_quote(symbol)
    price = quote.get("last_trade_price") or quote.get("mark_price")
    quantity = match.get("quantity")
    average_buy_price = match.get("average_buy_price")
    if price in (None, "") or quantity in (None, "") or average_buy_price in (None, ""):
        raise RobinhoodError(f"Incomplete position data for symbol: {symbol}")

    try:
        quantity_f = float(quantity)
        price_f = float(price)
        average_buy_price_f = float(average_buy_price)
    except (TypeError, ValueError) as e:
        raise RobinhoodError(f"Invalid numeric position data for symbol: {symbol}") from e

    equity = quantity_f * price_f
    equity_change = equity - (quantity_f * average_buy_price_f)
    percent_change = (
        0.0
        if average_buy_price_f == 0.0
        else ((price_f - average_buy_price_f) * 100 / average_buy_price_f)
    )
    return {
        "symbol": symbol,
        "held": True,
        "price": f"{price_f:.2f}",
        "quantity": quantity,
        "average_buy_price": average_buy_price,
        "equity": f"{equity:.2f}",
        "percent_change": f"{percent_change:.2f}",
        "equity_change": f"{equity_change:.2f}",
        "instrument": instrument_url,
    }


def get_watchlist(name: str = "Default") -> list[dict[str, Any]]:
    """Get stocks in a watchlist.

    Args:
        name: Watchlist name (default: "Default").

    Returns:
        List of watchlist items with instrument details.
    """
    result = _safe_call(rh.account.get_watchlist_by_name, name=name)
    return result if isinstance(result, list) else []


def get_quote(symbol: str) -> dict[str, Any]:
    """Get real-time quote for a stock symbol.

    Args:
        symbol: Stock ticker symbol (e.g., "AAPL").

    Returns:
        Quote data including last_trade_price, bid, ask, etc.
    """
    symbol = _normalize_symbol(symbol)
    result = _safe_call(rh.stocks.get_quotes, symbol)

    if isinstance(result, list) and len(result) > 0:
        return result[0]
    raise RobinhoodError(f"No quote found for symbol: {symbol}")


def get_fundamentals(symbol: str) -> dict[str, Any]:
    """Get fundamental data for a stock.

    Args:
        symbol: Stock ticker symbol.

    Returns:
        Fundamentals including pe_ratio, market_cap, dividend_yield, etc.
    """
    symbol = _normalize_symbol(symbol)
    result = _safe_call(rh.stocks.get_fundamentals, symbol)

    if isinstance(result, list) and len(result) > 0:
        return result[0]
    raise RobinhoodError(f"No fundamentals found for symbol: {symbol}")


def get_historicals(
    symbol: str,
    interval: Literal["5minute", "10minute", "hour", "day", "week"] = "day",
    span: Literal["day", "week", "month", "3month", "year", "5year"] = "month",
) -> list[dict[str, Any]]:
    """Get historical price data for a stock.

    Args:
        symbol: Stock ticker symbol.
        interval: Time interval (5minute, 10minute, hour, day, week).
        span: Time span (day, week, month, 3month, year, 5year).

    Returns:
        List of historical data points with open, close, high, low, volume.
    """
    symbol = _normalize_symbol(symbol)

    valid_intervals = {"5minute", "10minute", "hour", "day", "week"}
    valid_spans = {"day", "week", "month", "3month", "year", "5year"}

    if interval not in valid_intervals:
        raise RobinhoodError(f"Invalid interval. Must be one of: {valid_intervals}")
    if span not in valid_spans:
        raise RobinhoodError(f"Invalid span. Must be one of: {valid_spans}")

    result = _safe_call(rh.stocks.get_stock_historicals, symbol, interval=interval, span=span)
    return result if isinstance(result, list) else []


def get_news(symbol: str) -> list[dict[str, Any]]:
    """Get recent news articles for a stock.

    Args:
        symbol: Stock ticker symbol.

    Returns:
        List of news articles with title, url, source, published_at, etc.
    """
    symbol = _normalize_symbol(symbol)
    result = _safe_call(rh.stocks.get_news, symbol)
    return result if isinstance(result, list) else []


def get_earnings(symbol: str) -> list[dict[str, Any]]:
    """Get earnings data for a stock.

    Args:
        symbol: Stock ticker symbol.

    Returns:
        List of earnings reports with eps, report date, estimates, etc.
    """
    symbol = _normalize_symbol(symbol)
    result = _safe_call(rh.stocks.get_earnings, symbol)
    return result if isinstance(result, list) else []


def get_ratings(symbol: str) -> dict[str, Any]:
    """Get analyst ratings summary for a stock.

    Args:
        symbol: Stock ticker symbol.

    Returns:
        Ratings summary with buy, hold, sell counts and summary.
    """
    symbol = _normalize_symbol(symbol)
    result = _safe_call(rh.stocks.get_ratings, symbol)

    if isinstance(result, dict):
        return result
    raise RobinhoodError(f"No ratings found for symbol: {symbol}")


def get_dividends() -> list[dict[str, Any]]:
    """Get all dividend payments received.

    Returns:
        List of dividend payments with amount, payable_date, record_date, etc.
    """
    result = _safe_call(rh.account.get_dividends)
    return result if isinstance(result, list) else []


def get_options_positions() -> list[dict[str, Any]]:
    """Get all current options positions.

    Returns:
        List of options positions with chain_symbol, type, quantity, etc.
    """
    result = _safe_call(rh.options.get_open_option_positions)
    return result if isinstance(result, list) else []


def search_symbols(query: str) -> list[dict[str, Any]]:
    """Search for stock symbols by company name or ticker.

    Args:
        query: Search query (company name or partial ticker).

    Returns:
        List of matching instruments with symbol, name, etc.
    """
    if not query or not isinstance(query, str):
        raise RobinhoodError("Query must be a non-empty string")

    query = query.strip()

    # Try to get instruments by the query
    try:
        result = rh.stocks.get_instruments_by_symbols(query.upper())
        if result and isinstance(result, list):
            return result
    except Exception:
        pass

    # If exact match fails, try search
    try:
        result = rh.stocks.find_instrument_data(query)
        return result if isinstance(result, list) else []
    except Exception as e:
        raise RobinhoodError(f"Search failed: {e}") from e
