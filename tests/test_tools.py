"""Tests for tools module."""

from unittest.mock import MagicMock, patch

import pytest

from robinhood_mcp.tools import (
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
    def test_raises_on_none_result(self, mock_profile: MagicMock):
        """Should raise RobinhoodError when API returns None."""
        mock_profile.return_value = None

        with pytest.raises(RobinhoodError) as exc_info:
            get_portfolio()
        assert "login" in str(exc_info.value).lower()


class TestGetPositions:
    """Tests for get_positions function."""

    @patch("robinhood_mcp.tools.rh.account.build_holdings")
    def test_returns_holdings(self, mock_holdings: MagicMock):
        """Should return holdings dict."""
        expected = {
            "AAPL": {"quantity": "10", "average_buy_price": "150.00"},
            "TSLA": {"quantity": "5", "average_buy_price": "200.00"},
        }
        mock_holdings.return_value = expected

        result = get_positions()

        assert result == expected


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


class TestGetOptionsPositions:
    """Tests for get_options_positions function."""

    @patch("robinhood_mcp.tools.rh.options.get_open_option_positions")
    def test_returns_options_list(self, mock_options: MagicMock):
        """Should return list of options positions."""
        expected = [{"chain_symbol": "AAPL", "type": "call", "quantity": "1"}]
        mock_options.return_value = expected

        result = get_options_positions()

        assert result == expected


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
