"""Tests for the FastMCP server's auth-state caching.

These cover the failure-fast behavior added to `_ensure_logged_in()` so that
a transient AuthenticationError (e.g. a Robinhood device-approval timeout)
doesn't cause every subsequent tool call to re-run the full login flow and
freeze the single-threaded MCP server.
"""

from unittest.mock import MagicMock, patch

import pytest

from robinhood_mcp import server
from robinhood_mcp.auth import AuthenticationError, EnvironmentVariablesError
from robinhood_mcp.tools import RobinhoodError


@pytest.fixture(autouse=True)
def reset_server_state():
    """Reset the module-level login-state globals before each test."""
    server._login_attempted = False
    server._login_error = None
    server._cached_login_status = None
    server._cached_login_status_ts = 0.0
    server._auth_failure_message = None
    server._auth_failure_ts = 0.0
    yield
    server._login_attempted = False
    server._login_error = None
    server._cached_login_status = None
    server._cached_login_status_ts = 0.0
    server._auth_failure_message = None
    server._auth_failure_ts = 0.0


def _call_tool(tool, *args, **kwargs):
    """Call either a plain FastMCP function or a FunctionTool wrapper."""
    return getattr(tool, "fn", tool)(*args, **kwargs)


class TestEnsureLoggedInCooldown:
    """Failure-fast cooldown for transient AuthenticationError."""

    @patch("robinhood_mcp.server.login")
    def test_authentication_error_is_cached_for_subsequent_calls(self, mock_login: MagicMock):
        """A second call inside the cooldown must NOT re-invoke login()."""
        mock_login.side_effect = AuthenticationError("device approval timed out")

        with pytest.raises(RobinhoodError):
            server._ensure_logged_in()
        with pytest.raises(RobinhoodError) as exc_info:
            server._ensure_logged_in()

        # login() must only have been called once — the second call should
        # have short-circuited on the cached failure.
        assert mock_login.call_count == 1
        assert "cached failure" in str(exc_info.value)
        assert "device approval timed out" in str(exc_info.value)

    @patch("robinhood_mcp.server.login")
    def test_cooldown_expiry_allows_one_fresh_attempt(self, mock_login: MagicMock):
        """After the cooldown window elapses, login() must be retried."""
        mock_login.side_effect = AuthenticationError("device approval timed out")

        with pytest.raises(RobinhoodError):
            server._ensure_logged_in()

        # Pretend the cooldown has fully elapsed.
        server._auth_failure_ts -= server._AUTH_FAILURE_COOLDOWN_SECONDS + 1

        with pytest.raises(RobinhoodError):
            server._ensure_logged_in()

        assert mock_login.call_count == 2

    @patch("robinhood_mcp.server.login")
    def test_successful_login_clears_cached_failure(self, mock_login: MagicMock):
        """A successful retry must clear the cached-failure state."""
        mock_login.side_effect = [
            AuthenticationError("device approval timed out"),
            {"access_token": "ok"},
        ]

        with pytest.raises(RobinhoodError):
            server._ensure_logged_in()

        # Expire the cooldown so the next call retries.
        server._auth_failure_ts -= server._AUTH_FAILURE_COOLDOWN_SECONDS + 1

        # Successful retry — should not raise.
        server._ensure_logged_in()

        assert server._auth_failure_message is None
        assert mock_login.call_count == 2

    @patch("robinhood_mcp.server.login")
    def test_environment_variables_error_remains_permanent(self, mock_login: MagicMock):
        """Missing-credentials errors are permanent until restart, not cooldown-cached."""
        mock_login.side_effect = EnvironmentVariablesError(
            "ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD environment variables required"
        )

        with pytest.raises(RobinhoodError):
            server._ensure_logged_in()
        with pytest.raises(RobinhoodError) as exc_info:
            server._ensure_logged_in()

        # Still only one login() call — handled by the existing _login_error path.
        assert mock_login.call_count == 1
        # The permanent-error message must not carry the transient-failure suffix.
        assert "cached failure" not in str(exc_info.value)


class TestAccountNumberForwarding:
    """Server wrappers forward optional account selection to tool functions."""

    @patch("robinhood_mcp.server.get_portfolio")
    @patch("robinhood_mcp.server._ensure_logged_in")
    def test_portfolio_forwards_account_number(
        self, mock_ensure: MagicMock, mock_get_portfolio: MagicMock
    ):
        mock_get_portfolio.return_value = {"equity": "2500.00"}

        result = _call_tool(server.robinhood_get_portfolio, account_number="IRA123")

        assert result == {"equity": "2500.00"}
        mock_ensure.assert_called_once_with()
        mock_get_portfolio.assert_called_once_with("IRA123")

    @patch("robinhood_mcp.server.get_order_history")
    @patch("robinhood_mcp.server._ensure_logged_in")
    def test_order_history_forwards_account_number(
        self, mock_ensure: MagicMock, mock_get_order_history: MagicMock
    ):
        mock_get_order_history.return_value = []

        result = _call_tool(
            server.robinhood_get_order_history,
            symbol="HIMS",
            state="all",
            limit=10,
            start_date="2026-01-01",
            account_number="IRA123",
        )

        assert result == []
        mock_ensure.assert_called_once_with()
        mock_get_order_history.assert_called_once_with("HIMS", "all", 10, "2026-01-01", "IRA123")
