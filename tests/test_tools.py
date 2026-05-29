"""Tests for tools module."""

from unittest.mock import MagicMock, patch

import pytest

import robinhood_mcp.tools as tools_module
from robinhood_mcp.tools import (
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


@pytest.fixture(autouse=True)
def clear_positions_cache():
    """Reset the positions cache between tests."""
    tools_module._clear_positions_cache()
    yield
    tools_module._clear_positions_cache()


@pytest.fixture(autouse=True)
def clear_symbol_cache():
    """Reset the instrument-URL to symbol cache between tests."""
    tools_module._clear_symbol_cache()
    yield
    tools_module._clear_symbol_cache()


def _make_order(
    instrument: str = "https://instrument/hims/",
    side: str = "buy",
    state: str = "filled",
    created_at: str = "2026-01-01T00:00:00.000000Z",
    executions: list | None = None,
) -> dict:
    """Build a robin_stocks-shaped stock order dict for tests."""
    if executions is None:
        executions = [
            {
                "price": "20.00",
                "quantity": "10.00000000",
                "timestamp": created_at,
                "settlement_date": "2026-01-03",
            }
        ]
    return {
        "id": "order-id",
        "instrument": instrument,
        "side": side,
        "state": state,
        "quantity": "10.00000000",
        "cumulative_quantity": "10.00000000",
        "average_price": "20.00",
        "price": "20.00",
        "type": "limit",
        "created_at": created_at,
        "updated_at": created_at,
        "last_transaction_at": created_at,
        "executions": executions,
    }


class TestGetAccounts:
    """Tests for get_accounts function."""

    @patch("robinhood_mcp.tools.rh.profiles.load_account_profile")
    def test_returns_slimmed_account_profiles(self, mock_profile: MagicMock):
        """Should return account profiles with fields useful for selection."""
        mock_profile.return_value = [
            {
                "account_number": "IRA123",
                "type": "traditional_ira",
                "state": "active",
                "buying_power": "100.00",
                "cash": "50.00",
                "portfolio_cash": "25.00",
                "cash_available_for_withdrawal": "10.00",
                "deactivated": False,
                "locked": False,
                "url": "https://api.robinhood.com/accounts/IRA123/",
                "user": "https://api.robinhood.com/user/",
            },
            {
                "account_number": "TAXABLE456",
                "type": "margin",
                "state": "active",
                "buying_power": "200.00",
                "cash": "75.00",
                "portfolio_cash": "35.00",
                "cash_available_for_withdrawal": "20.00",
                "deactivated": False,
                "locked": False,
            },
        ]

        result = tools_module.get_accounts()

        assert result == [
            {
                "account_number": "IRA123",
                "type": "traditional_ira",
                "state": "active",
                "buying_power": "100.00",
                "cash": "50.00",
                "portfolio_cash": "25.00",
                "cash_available_for_withdrawal": "10.00",
                "deactivated": False,
                "locked": False,
            },
            {
                "account_number": "TAXABLE456",
                "type": "margin",
                "state": "active",
                "buying_power": "200.00",
                "cash": "75.00",
                "portfolio_cash": "35.00",
                "cash_available_for_withdrawal": "20.00",
                "deactivated": False,
                "locked": False,
            },
        ]
        mock_profile.assert_called_once_with(dataType="results")

    @patch("robinhood_mcp.tools.rh.profiles.load_account_profile")
    def test_raises_on_non_list_response(self, mock_profile: MagicMock):
        """Should raise RobinhoodError when account list has an unexpected shape."""
        mock_profile.return_value = {"unexpected": "shape"}

        with pytest.raises(RobinhoodError):
            tools_module.get_accounts()


class TestGetPortfolio:
    """Tests for get_portfolio function."""

    @patch("robinhood_mcp.tools.rh.profiles.load_portfolio_profile")
    def test_returns_portfolio_data(self, mock_profile: MagicMock):
        """Should return portfolio profile data."""
        expected = {
            "equity": "10000.00",
            "extended_hours_equity": "10050.00",
        }
        mock_profile.return_value = expected

        result = get_portfolio()

        assert result == expected
        mock_profile.assert_called_once()

    @patch("robinhood_mcp.tools.rh.profiles.load_portfolio_profile")
    def test_forwards_account_number(self, mock_profile: MagicMock):
        """Should request a specific account's portfolio when account_number is given."""
        mock_profile.return_value = {"equity": "2500.00"}

        result = get_portfolio(account_number=" IRA123 ")

        assert result == {"equity": "2500.00"}
        mock_profile.assert_called_once_with(account_number="IRA123")

    @patch("robinhood_mcp.tools.rh.profiles.load_portfolio_profile")
    def test_rejects_invalid_account_number(self, mock_profile: MagicMock):
        """Should reject unsafe account numbers before they reach robin_stocks."""
        with pytest.raises(RobinhoodError):
            get_portfolio(account_number="IRA123&account_numbers=OTHER")

        mock_profile.assert_not_called()

    @patch("robinhood_mcp.tools.rh.profiles.load_portfolio_profile")
    def test_raises_on_none_result(self, mock_profile: MagicMock):
        """Should raise RobinhoodError when API returns None."""
        mock_profile.return_value = None

        with pytest.raises(RobinhoodError) as exc_info:
            get_portfolio()
        assert "login" in str(exc_info.value).lower()


class TestGetPositions:
    """Tests for get_positions function."""

    @patch("robinhood_mcp.tools.rh.account.build_holdings")
    def test_returns_slimmed_holdings(self, mock_holdings: MagicMock):
        """Should return holdings dict with only essential fields."""
        mock_holdings.return_value = {
            "AAPL": {
                "quantity": "10",
                "average_buy_price": "150.00",
                "price": "175.00",
                "equity": "1750.00",
                "percent_change": "16.67",
                "equity_change": "250.00",
                "id": "abc123",
                "name": "Apple Inc.",
                "type": "stock",
                "instrument": "https://api.robinhood.com/instruments/abc/",
                "account": "https://api.robinhood.com/accounts/xyz/",
            },
            "TSLA": {
                "quantity": "5",
                "average_buy_price": "200.00",
                "price": "250.00",
                "equity": "1250.00",
                "percent_change": "25.00",
                "equity_change": "250.00",
                "id": "def456",
                "name": "Tesla, Inc.",
                "type": "stock",
                "instrument": "https://api.robinhood.com/instruments/def/",
                "account": "https://api.robinhood.com/accounts/xyz/",
            },
        }

        result = get_positions()

        # Should only contain slim fields, not id, name, type, instrument, account
        assert result == {
            "AAPL": {
                "quantity": "10",
                "average_buy_price": "150.00",
                "price": "175.00",
                "equity": "1750.00",
                "percent_change": "16.67",
                "equity_change": "250.00",
            },
            "TSLA": {
                "quantity": "5",
                "average_buy_price": "200.00",
                "price": "250.00",
                "equity": "1250.00",
                "percent_change": "25.00",
                "equity_change": "250.00",
            },
        }
        # Verify excluded fields are not present
        assert "id" not in result["AAPL"]
        assert "name" not in result["AAPL"]
        assert "type" not in result["AAPL"]
        assert "instrument" not in result["AAPL"]
        assert "account" not in result["AAPL"]

    @patch(
        "robinhood_mcp.tools.time.monotonic",
        side_effect=[100.0, 100.0, 100.0, 101.0],
    )
    @patch("robinhood_mcp.tools.rh.account.build_holdings")
    def test_caches_holdings_snapshot(self, mock_holdings: MagicMock, _mock_monotonic: MagicMock):
        """Should reuse a fresh holdings snapshot instead of rebuilding it."""
        mock_holdings.return_value = {
            "AAPL": {
                "quantity": "10",
                "average_buy_price": "150.00",
                "price": "175.00",
                "equity": "1750.00",
                "percent_change": "16.67",
                "equity_change": "250.00",
            },
        }

        first = get_positions()
        first["AAPL"]["quantity"] = "999"
        second = get_positions()

        assert second == {
            "AAPL": {
                "quantity": "10",
                "average_buy_price": "150.00",
                "price": "175.00",
                "equity": "1750.00",
                "percent_change": "16.67",
                "equity_change": "250.00",
            },
        }
        assert mock_holdings.call_count == 1

    @patch(
        "robinhood_mcp.tools.time.monotonic",
        side_effect=[100.0, 100.0, 100.0, 131.0, 131.0, 131.0],
    )
    @patch("robinhood_mcp.tools.rh.account.build_holdings")
    def test_refreshes_expired_cache(self, mock_holdings: MagicMock, _mock_monotonic: MagicMock):
        """Should rebuild holdings after the cache TTL expires."""
        mock_holdings.side_effect = [
            {
                "AAPL": {
                    "quantity": "10",
                    "average_buy_price": "150.00",
                    "price": "175.00",
                    "equity": "1750.00",
                    "percent_change": "16.67",
                    "equity_change": "250.00",
                },
            },
            {
                "AAPL": {
                    "quantity": "11",
                    "average_buy_price": "150.00",
                    "price": "175.00",
                    "equity": "1925.00",
                    "percent_change": "16.67",
                    "equity_change": "275.00",
                },
            },
        ]

        first = get_positions()
        second = get_positions()

        assert first == {
            "AAPL": {
                "quantity": "10",
                "average_buy_price": "150.00",
                "price": "175.00",
                "equity": "1750.00",
                "percent_change": "16.67",
                "equity_change": "250.00",
            },
        }
        assert second == {
            "AAPL": {
                "quantity": "11",
                "average_buy_price": "150.00",
                "price": "175.00",
                "equity": "1925.00",
                "percent_change": "16.67",
                "equity_change": "275.00",
            },
        }
        assert mock_holdings.call_count == 2

    @patch(
        "robinhood_mcp.tools.time.monotonic",
        side_effect=[100.0, 100.0, 100.0, 101.0],
    )
    @patch("robinhood_mcp.tools.rh.account.build_holdings")
    def test_caches_empty_holdings_snapshot(
        self, mock_holdings: MagicMock, _mock_monotonic: MagicMock
    ):
        """Should reuse an empty holdings snapshot instead of rebuilding it."""
        mock_holdings.return_value = {}

        assert get_positions() == {}
        assert get_positions() == {}
        assert mock_holdings.call_count == 1

    @patch("robinhood_mcp.tools.get_quote")
    @patch("robinhood_mcp.tools.rh.stocks.get_symbol_by_url")
    @patch("robinhood_mcp.tools.rh.account.get_open_stock_positions")
    @patch("robinhood_mcp.tools.rh.account.build_holdings")
    def test_account_number_uses_account_specific_positions(
        self,
        mock_build_holdings: MagicMock,
        mock_open_positions: MagicMock,
        mock_symbol: MagicMock,
        mock_get_quote: MagicMock,
    ):
        """Should build holdings from the selected account's open positions."""
        mock_open_positions.return_value = [
            {
                "instrument": "https://instrument/hims/",
                "quantity": "10.00000000",
                "average_buy_price": "20.00",
            }
        ]
        mock_symbol.return_value = "HIMS"
        mock_get_quote.return_value = {"last_trade_price": "21.50"}

        result = get_positions(account_number="IRA123")

        assert result == {
            "HIMS": {
                "price": "21.50",
                "quantity": "10.00000000",
                "average_buy_price": "20.00",
                "equity": "215.00",
                "percent_change": "7.50",
                "equity_change": "15.00",
            }
        }
        mock_open_positions.assert_called_once_with(account_number="IRA123")
        mock_build_holdings.assert_not_called()


class TestGetPosition:
    """Tests for get_position function."""

    @patch(
        "robinhood_mcp.tools.time.monotonic",
        side_effect=[100.0, 100.0, 100.0, 101.0],
    )
    @patch("robinhood_mcp.tools.get_quote")
    @patch("robinhood_mcp.tools.rh.account.get_open_stock_positions")
    @patch("robinhood_mcp.tools.rh.stocks.get_instruments_by_symbols")
    @patch("robinhood_mcp.tools.rh.account.build_holdings")
    def test_returns_cached_symbol_without_extra_api_calls(
        self,
        mock_holdings: MagicMock,
        mock_get_instruments: MagicMock,
        mock_open_positions: MagicMock,
        mock_get_quote: MagicMock,
        _mock_monotonic: MagicMock,
    ):
        """Should serve a cached symbol directly from the holdings snapshot."""
        mock_holdings.return_value = {
            "HIMS": {
                "quantity": "25",
                "average_buy_price": "18.50",
                "equity": "555.00",
            },
        }

        get_positions()
        result = get_position(" hims ")

        assert result == {
            "symbol": "HIMS",
            "held": False,
            "price": None,
            "quantity": "25",
            "average_buy_price": "18.50",
            "equity": "555.00",
            "percent_change": None,
            "equity_change": None,
        }
        mock_get_instruments.assert_not_called()
        mock_open_positions.assert_not_called()
        mock_get_quote.assert_not_called()

    @patch("robinhood_mcp.tools.rh.account.build_holdings")
    @patch("robinhood_mcp.tools.get_quote")
    @patch("robinhood_mcp.tools.rh.account.get_open_stock_positions")
    @patch("robinhood_mcp.tools.rh.stocks.get_instruments_by_symbols")
    def test_returns_single_position_without_building_all_holdings(
        self,
        mock_get_instruments: MagicMock,
        mock_open_positions: MagicMock,
        mock_get_quote: MagicMock,
        mock_build_holdings: MagicMock,
    ):
        """Should fetch one symbol directly when holdings cache is cold."""
        mock_get_instruments.return_value = [{"url": "https://instrument/hims/"}]
        mock_open_positions.return_value = [
            {
                "instrument": "https://instrument/hims/",
                "quantity": "10.00000000",
                "average_buy_price": "20.00",
            }
        ]
        mock_get_quote.return_value = {"last_trade_price": "21.50"}

        result = get_position("HIMS")

        assert result == {
            "symbol": "HIMS",
            "held": True,
            "price": "21.50",
            "quantity": "10.00000000",
            "average_buy_price": "20.00",
            "equity": "215.00",
            "percent_change": "7.50",
            "equity_change": "15.00",
        }
        mock_get_instruments.assert_called_once_with("HIMS")
        mock_open_positions.assert_called_once_with()
        mock_get_quote.assert_called_once_with("HIMS")
        mock_build_holdings.assert_not_called()

    @patch("robinhood_mcp.tools.rh.account.build_holdings")
    @patch("robinhood_mcp.tools.get_quote")
    @patch("robinhood_mcp.tools.rh.account.get_open_stock_positions")
    @patch("robinhood_mcp.tools.rh.stocks.get_instruments_by_symbols")
    def test_forwards_account_number_to_single_position_lookup(
        self,
        mock_get_instruments: MagicMock,
        mock_open_positions: MagicMock,
        mock_get_quote: MagicMock,
        mock_build_holdings: MagicMock,
    ):
        """Should search one symbol inside the selected account."""
        mock_get_instruments.return_value = [{"url": "https://instrument/hims/"}]
        mock_open_positions.return_value = [
            {
                "instrument": "https://instrument/hims/",
                "quantity": "10.00000000",
                "average_buy_price": "20.00",
            }
        ]
        mock_get_quote.return_value = {"last_trade_price": "21.50"}

        result = get_position("HIMS", account_number="IRA123")

        assert result["symbol"] == "HIMS"
        assert result["held"] is True
        mock_open_positions.assert_called_once_with(account_number="IRA123")
        mock_build_holdings.assert_not_called()

    @patch("robinhood_mcp.tools.get_quote")
    @patch("robinhood_mcp.tools.rh.account.get_open_stock_positions")
    @patch("robinhood_mcp.tools.rh.stocks.get_instruments_by_symbols")
    def test_returns_not_held_when_symbol_absent(
        self,
        mock_get_instruments: MagicMock,
        mock_open_positions: MagicMock,
        mock_get_quote: MagicMock,
    ):
        """Should report held=False when the symbol has no open position."""
        mock_get_instruments.return_value = [{"url": "https://instrument/hims/"}]
        mock_open_positions.return_value = [
            {"instrument": "https://instrument/other/", "quantity": "1"}
        ]

        result = get_position("HIMS")

        assert result == {"symbol": "HIMS", "held": False}
        mock_get_quote.assert_not_called()


class TestGetQuote:
    """Tests for get_quote function."""

    @patch("robinhood_mcp.tools.rh.stocks.get_quotes")
    def test_returns_quote(self, mock_quotes: MagicMock):
        """Should return quote for symbol."""
        expected = {"symbol": "AAPL", "last_trade_price": "175.00"}
        mock_quotes.return_value = [expected]

        result = get_quote("AAPL")

        assert result == expected
        mock_quotes.assert_called_once_with("AAPL")

    @patch("robinhood_mcp.tools.rh.stocks.get_quotes")
    def test_uppercases_symbol(self, mock_quotes: MagicMock):
        """Should uppercase and strip symbol."""
        mock_quotes.return_value = [{"symbol": "AAPL"}]

        get_quote("  aapl  ")

        mock_quotes.assert_called_once_with("AAPL")

    def test_raises_for_empty_symbol(self):
        """Should raise RobinhoodError for empty symbol."""
        with pytest.raises(RobinhoodError) as exc_info:
            get_quote("")
        assert "non-empty string" in str(exc_info.value)

    def test_raises_for_non_string_symbol(self):
        """Should raise RobinhoodError for non-string symbol."""
        with pytest.raises(RobinhoodError):
            get_quote(123)  # type: ignore

    @patch("robinhood_mcp.tools.rh.stocks.get_quotes")
    def test_raises_for_no_results(self, mock_quotes: MagicMock):
        """Should raise RobinhoodError when no quote found."""
        mock_quotes.return_value = []

        with pytest.raises(RobinhoodError) as exc_info:
            get_quote("INVALID")
        assert "No quote found" in str(exc_info.value)


class TestGetHistoricals:
    """Tests for get_historicals function."""

    @patch("robinhood_mcp.tools.rh.stocks.get_stock_historicals")
    def test_returns_historical_data(self, mock_hist: MagicMock):
        """Should return historical data."""
        expected = [
            {"open": "100.00", "close": "105.00", "volume": "1000000"},
            {"open": "105.00", "close": "110.00", "volume": "1200000"},
        ]
        mock_hist.return_value = expected

        result = get_historicals("AAPL", interval="day", span="month")

        assert result == expected
        mock_hist.assert_called_once_with("AAPL", interval="day", span="month")

    def test_raises_for_invalid_interval(self):
        """Should raise RobinhoodError for invalid interval."""
        with pytest.raises(RobinhoodError) as exc_info:
            get_historicals("AAPL", interval="invalid")  # type: ignore
        assert "Invalid interval" in str(exc_info.value)

    def test_raises_for_invalid_span(self):
        """Should raise RobinhoodError for invalid span."""
        with pytest.raises(RobinhoodError) as exc_info:
            get_historicals("AAPL", span="invalid")  # type: ignore
        assert "Invalid span" in str(exc_info.value)


class TestGetFundamentals:
    """Tests for get_fundamentals function."""

    @patch("robinhood_mcp.tools.rh.stocks.get_fundamentals")
    def test_returns_fundamentals(self, mock_fund: MagicMock):
        """Should return fundamental data."""
        expected = {"pe_ratio": "25.5", "market_cap": "2500000000000"}
        mock_fund.return_value = [expected]

        result = get_fundamentals("AAPL")

        assert result == expected


class TestGetNews:
    """Tests for get_news function."""

    @patch("robinhood_mcp.tools.rh.stocks.get_news")
    def test_returns_news_list(self, mock_news: MagicMock):
        """Should return list of news articles."""
        expected = [
            {"title": "Apple announces new product", "source": "Reuters"},
            {"title": "AAPL stock rises", "source": "Bloomberg"},
        ]
        mock_news.return_value = expected

        result = get_news("AAPL")

        assert result == expected


class TestGetEarnings:
    """Tests for get_earnings function."""

    @patch("robinhood_mcp.tools.rh.stocks.get_earnings")
    def test_returns_earnings_list(self, mock_earnings: MagicMock):
        """Should return list of earnings reports."""
        expected = [{"year": "2024", "quarter": "Q4", "eps": {"actual": "1.50"}}]
        mock_earnings.return_value = expected

        result = get_earnings("AAPL")

        assert result == expected


class TestGetRatings:
    """Tests for get_ratings function."""

    @patch("robinhood_mcp.tools.rh.stocks.get_ratings")
    def test_returns_ratings(self, mock_ratings: MagicMock):
        """Should return ratings summary."""
        expected = {"num_buy_ratings": 30, "num_hold_ratings": 10, "num_sell_ratings": 2}
        mock_ratings.return_value = expected

        result = get_ratings("AAPL")

        assert result == expected


class TestGetDividends:
    """Tests for get_dividends function."""

    @patch("robinhood_mcp.tools.rh.account.get_dividends")
    def test_returns_dividends_list(self, mock_divs: MagicMock):
        """Should return list of dividend payments."""
        expected = [
            {"amount": "0.23", "payable_date": "2024-02-15"},
            {"amount": "0.23", "payable_date": "2024-05-15"},
        ]
        mock_divs.return_value = expected

        result = get_dividends()

        assert result == expected

    @patch("robinhood_mcp.tools.rh.account.get_dividends")
    def test_filters_dividends_by_account_number(self, mock_divs: MagicMock):
        """Should return only dividends for the selected account."""
        mock_divs.return_value = [
            {
                "amount": "0.23",
                "payable_date": "2024-02-15",
                "account": "https://api.robinhood.com/accounts/IRA123/",
            },
            {
                "amount": "0.42",
                "payable_date": "2024-02-16",
                "account": "https://api.robinhood.com/accounts/TAXABLE456/",
            },
        ]

        result = get_dividends(account_number="IRA123")

        assert result == [
            {
                "amount": "0.23",
                "payable_date": "2024-02-15",
                "account": "https://api.robinhood.com/accounts/IRA123/",
            }
        ]
        mock_divs.assert_called_once_with()


class TestGetOptionsPositions:
    """Tests for get_options_positions function."""

    @patch("robinhood_mcp.tools.rh.options.get_open_option_positions")
    def test_returns_options_list(self, mock_options: MagicMock):
        """Should return list of options positions."""
        expected = [{"chain_symbol": "AAPL", "type": "call", "quantity": "1"}]
        mock_options.return_value = expected

        result = get_options_positions()

        assert result == expected

    @patch("robinhood_mcp.tools.rh.options.get_open_option_positions")
    def test_forwards_account_number(self, mock_options: MagicMock):
        """Should request option positions for the selected account."""
        mock_options.return_value = [{"chain_symbol": "AAPL", "type": "call", "quantity": "1"}]

        result = get_options_positions(account_number="IRA123")

        assert result == [{"chain_symbol": "AAPL", "type": "call", "quantity": "1"}]
        mock_options.assert_called_once_with(account_number="IRA123")


class TestGetWatchlist:
    """Tests for get_watchlist function."""

    @patch("robinhood_mcp.tools.rh.account.get_watchlist_by_name")
    def test_returns_watchlist(self, mock_watchlist: MagicMock):
        """Should return watchlist items."""
        expected = [{"symbol": "AAPL"}, {"symbol": "TSLA"}]
        mock_watchlist.return_value = expected

        result = get_watchlist("Default")

        assert result == expected
        mock_watchlist.assert_called_once_with(name="Default")


class TestSearchSymbols:
    """Tests for search_symbols function."""

    @patch("robinhood_mcp.tools.rh.stocks.get_instruments_by_symbols")
    def test_returns_search_results(self, mock_instruments: MagicMock):
        """Should return matching instruments."""
        expected = [{"symbol": "AAPL", "name": "Apple Inc."}]
        mock_instruments.return_value = expected

        result = search_symbols("AAPL")

        assert result == expected

    def test_raises_for_empty_query(self):
        """Should raise RobinhoodError for empty query."""
        with pytest.raises(RobinhoodError) as exc_info:
            search_symbols("")
        assert "non-empty string" in str(exc_info.value)


class TestGetOrderHistory:
    """Tests for get_order_history function."""

    @patch("robinhood_mcp.tools.rh.stocks.get_symbol_by_url")
    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_returns_curated_rows_with_resolved_symbols(
        self, mock_orders: MagicMock, mock_symbol: MagicMock
    ):
        """Should return curated rows with instrument URLs resolved to symbols."""
        mock_orders.return_value = [_make_order()]
        mock_symbol.return_value = "HIMS"

        result = get_order_history()

        assert result == [
            {
                "symbol": "HIMS",
                "side": "buy",
                "state": "filled",
                "quantity": "10.00000000",
                "filled_quantity": "10.00000000",
                "average_price": "20.00",
                "type": "limit",
                "created_at": "2026-01-01T00:00:00.000000Z",
                "last_transaction_at": "2026-01-01T00:00:00.000000Z",
                "executions": [
                    {
                        "price": "20.00",
                        "quantity": "10.00000000",
                        "timestamp": "2026-01-01T00:00:00.000000Z",
                    }
                ],
            }
        ]

    @patch("robinhood_mcp.tools.rh.stocks.get_symbol_by_url")
    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_resolves_each_distinct_instrument_once(
        self, mock_orders: MagicMock, mock_symbol: MagicMock
    ):
        """Should resolve each distinct instrument URL only once, not per order."""
        mock_orders.return_value = [
            _make_order(instrument="https://instrument/hims/", created_at="2026-03-03T00:00:00Z"),
            _make_order(instrument="https://instrument/hims/", created_at="2026-02-02T00:00:00Z"),
            _make_order(instrument="https://instrument/aapl/", created_at="2026-01-01T00:00:00Z"),
        ]
        mock_symbol.side_effect = lambda url: {
            "https://instrument/hims/": "HIMS",
            "https://instrument/aapl/": "AAPL",
        }[url]

        result = get_order_history()

        assert [row["symbol"] for row in result] == ["HIMS", "HIMS", "AAPL"]
        assert mock_symbol.call_count == 2

    @patch("robinhood_mcp.tools.rh.stocks.get_symbol_by_url")
    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_executed_filter_keeps_filled_and_partial_fills(
        self, mock_orders: MagicMock, mock_symbol: MagicMock
    ):
        """Default state='executed' should keep filled AND partially_filled orders."""
        mock_symbol.return_value = "HIMS"
        mock_orders.return_value = [
            _make_order(state="filled", created_at="2026-01-04T00:00:00Z"),
            _make_order(
                state="partially_filled",
                created_at="2026-01-03T00:00:00Z",
                executions=[
                    {"price": "20.00", "quantity": "5", "timestamp": "2026-01-03T00:00:00Z"}
                ],
            ),
            _make_order(state="cancelled", created_at="2026-01-02T00:00:00Z", executions=[]),
            _make_order(state="queued", created_at="2026-01-01T00:00:00Z", executions=[]),
        ]

        result = get_order_history()

        assert [row["state"] for row in result] == ["filled", "partially_filled"]

    @patch("robinhood_mcp.tools.rh.stocks.get_symbol_by_url")
    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_state_all_returns_every_order(self, mock_orders: MagicMock, mock_symbol: MagicMock):
        """state='all' should return cancelled and queued orders too."""
        mock_symbol.return_value = "HIMS"
        mock_orders.return_value = [
            _make_order(state="filled", created_at="2026-01-02T00:00:00Z"),
            _make_order(state="cancelled", created_at="2026-01-01T00:00:00Z", executions=[]),
        ]

        result = get_order_history(state="all")

        assert [row["state"] for row in result] == ["filled", "cancelled"]

    @patch("robinhood_mcp.tools.rh.stocks.get_symbol_by_url")
    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_malformed_executions_treated_as_no_fills(
        self, mock_orders: MagicMock, mock_symbol: MagicMock
    ):
        """An order whose executions field is not a list of dicts is treated as
        having no fills: curated to [] without crashing, and dropped by the
        default state='executed' filter."""
        mock_symbol.return_value = "HIMS"
        mock_orders.return_value = [
            _make_order(state="filled", executions=5),  # type: ignore[arg-type]
        ]

        # state="all" must curate the malformed value to [] rather than crash.
        all_rows = get_order_history(state="all")
        assert all_rows[0]["executions"] == []

        # state="executed" must drop it - a non-list value is not a real fill.
        assert get_order_history() == []

    @patch("robinhood_mcp.tools.rh.stocks.get_symbol_by_url")
    @patch("robinhood_mcp.tools.rh.stocks.get_instruments_by_symbols")
    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_symbol_filter_restricts_to_one_instrument(
        self,
        mock_orders: MagicMock,
        mock_instruments: MagicMock,
        mock_symbol: MagicMock,
    ):
        """A symbol filter keeps only that instrument and skips per-row resolution."""
        mock_instruments.return_value = [{"url": "https://instrument/hims/"}]
        mock_orders.return_value = [
            _make_order(instrument="https://instrument/hims/", created_at="2026-01-02T00:00:00Z"),
            _make_order(instrument="https://instrument/aapl/", created_at="2026-01-01T00:00:00Z"),
        ]

        result = get_order_history(symbol="hims")

        assert [row["symbol"] for row in result] == ["HIMS"]
        mock_instruments.assert_called_once_with("HIMS")
        mock_symbol.assert_not_called()

    @patch("robinhood_mcp.tools.rh.stocks.get_symbol_by_url")
    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_limit_returns_most_recent_first(self, mock_orders: MagicMock, mock_symbol: MagicMock):
        """Should sort newest-first by created_at and slice to limit."""
        mock_symbol.return_value = "HIMS"
        mock_orders.return_value = [
            _make_order(created_at="2026-01-01T00:00:00Z"),
            _make_order(created_at="2026-03-03T00:00:00Z"),
            _make_order(created_at="2026-02-02T00:00:00Z"),
        ]

        result = get_order_history(limit=2)

        assert [row["created_at"] for row in result] == [
            "2026-03-03T00:00:00Z",
            "2026-02-02T00:00:00Z",
        ]

    @patch("robinhood_mcp.tools.rh.stocks.get_symbol_by_url")
    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_start_date_forwarded_to_api(self, mock_orders: MagicMock, mock_symbol: MagicMock):
        """start_date should be forwarded to robin_stocks for server-side filtering."""
        mock_symbol.return_value = "HIMS"
        mock_orders.return_value = [_make_order()]

        get_order_history(start_date="2026-01-01")

        assert mock_orders.call_args.kwargs.get("start_date") == "2026-01-01"

    @patch("robinhood_mcp.tools.rh.stocks.get_symbol_by_url")
    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_account_number_forwarded_to_api(self, mock_orders: MagicMock, mock_symbol: MagicMock):
        """account_number should be forwarded to robin_stocks order history."""
        mock_symbol.return_value = "HIMS"
        mock_orders.return_value = [_make_order()]

        get_order_history(account_number="IRA123", start_date="2026-01-01")

        assert mock_orders.call_args.kwargs == {
            "start_date": "2026-01-01",
            "account_number": "IRA123",
        }

    @patch("robinhood_mcp.tools.rh.stocks.get_symbol_by_url")
    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_unresolvable_instrument_yields_none_symbol(
        self, mock_orders: MagicMock, mock_symbol: MagicMock
    ):
        """A failed symbol lookup should not fail the call - symbol falls back to None."""
        mock_orders.return_value = [_make_order()]
        mock_symbol.side_effect = Exception("instrument lookup failed")

        result = get_order_history()

        assert result[0]["symbol"] is None
        assert result[0]["state"] == "filled"

    @patch("robinhood_mcp.tools.rh.stocks.get_symbol_by_url")
    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_failed_resolution_attempted_once_per_call(
        self, mock_orders: MagicMock, mock_symbol: MagicMock
    ):
        """A failing instrument lookup is attempted once per call, not once per
        row - many orders for one unresolvable instrument must not storm the API."""
        mock_orders.return_value = [
            _make_order(instrument="https://instrument/x/", created_at="2026-01-03T00:00:00Z"),
            _make_order(instrument="https://instrument/x/", created_at="2026-01-02T00:00:00Z"),
            _make_order(instrument="https://instrument/x/", created_at="2026-01-01T00:00:00Z"),
        ]
        mock_symbol.side_effect = Exception("rate limited")

        result = get_order_history()

        assert [row["symbol"] for row in result] == [None, None, None]
        assert mock_symbol.call_count == 1

    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_returns_empty_list_when_no_orders(self, mock_orders: MagicMock):
        """Should return an empty list when the account has no orders."""
        mock_orders.return_value = []

        assert get_order_history() == []

    @patch("robinhood_mcp.tools.rh.orders.get_all_stock_orders")
    def test_raises_on_non_list_response(self, mock_orders: MagicMock):
        """Should raise RobinhoodError when the API returns an unexpected type."""
        mock_orders.return_value = {"unexpected": "shape"}

        with pytest.raises(RobinhoodError):
            get_order_history()

    def test_raises_for_invalid_state(self):
        """Should raise RobinhoodError for an unsupported state filter."""
        with pytest.raises(RobinhoodError):
            get_order_history(state="bogus")  # type: ignore[arg-type]

    def test_raises_for_invalid_limit(self):
        """Should raise RobinhoodError for a non-positive limit."""
        with pytest.raises(RobinhoodError):
            get_order_history(limit=0)
