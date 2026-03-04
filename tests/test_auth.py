"""Tests for authentication module."""

from unittest.mock import MagicMock, patch

import pytest

from robinhood_mcp.auth import (
    AuthenticationError,
    _clear_stale_pickle,
    get_totp_code,
    is_logged_in,
    login,
    logout,
)


class TestGetTotpCode:
    """Tests for get_totp_code function."""

    def test_returns_none_for_no_secret(self):
        """Should return None when no secret provided."""
        assert get_totp_code(None) is None
        assert get_totp_code("") is None

    def test_generates_code_for_valid_secret(self):
        """Should generate 6-digit code for valid secret."""
        # Valid base32 secret
        secret = "JBSWY3DPEHPK3PXP"
        code = get_totp_code(secret)

        assert code is not None
        assert len(code) == 6
        assert code.isdigit()

    def test_raises_for_invalid_secret(self):
        """Should raise AuthenticationError for invalid secret."""
        with pytest.raises(AuthenticationError):
            get_totp_code("not-valid-base32!!!")


class TestLogin:
    """Tests for login function."""

    @patch.dict("os.environ", {}, clear=True)
    def test_raises_without_credentials(self):
        """Should raise AuthenticationError when no credentials."""
        with pytest.raises(AuthenticationError) as exc_info:
            login()
        assert "ROBINHOOD_USERNAME" in str(exc_info.value)

    @patch.dict(
        "os.environ",
        {"ROBINHOOD_USERNAME": "test@example.com", "ROBINHOOD_PASSWORD": "secret"},
        clear=True,
    )
    @patch("robinhood_mcp.auth.rh.login")
    def test_calls_robin_stocks_login(self, mock_login: MagicMock):
        """Should call robin_stocks login with credentials."""
        mock_login.return_value = {"access_token": "test"}

        result = login()

        mock_login.assert_called_once_with(
            username="test@example.com",
            password="secret",
            mfa_code=None,
            store_session=True,
        )
        assert result == {"access_token": "test"}

    @patch.dict(
        "os.environ",
        {
            "ROBINHOOD_USERNAME": "test@example.com",
            "ROBINHOOD_PASSWORD": "secret",
            "ROBINHOOD_TOTP_SECRET": "JBSWY3DPEHPK3PXP",
        },
        clear=True,
    )
    @patch("robinhood_mcp.auth.rh.login")
    def test_includes_totp_code(self, mock_login: MagicMock):
        """Should generate and include TOTP code when secret provided."""
        mock_login.return_value = {"access_token": "test"}

        login()

        # Verify mfa_code was passed (should be 6 digits)
        call_args = mock_login.call_args
        assert call_args.kwargs["mfa_code"] is not None
        assert len(call_args.kwargs["mfa_code"]) == 6

    @patch.dict(
        "os.environ",
        {"ROBINHOOD_USERNAME": "test@example.com", "ROBINHOOD_PASSWORD": "secret"},
        clear=True,
    )
    @patch("robinhood_mcp.auth.rh.login")
    def test_raises_on_login_failure(self, mock_login: MagicMock):
        """Should raise AuthenticationError on login failure."""
        mock_login.return_value = None

        with pytest.raises(AuthenticationError) as exc_info:
            login()
        assert "empty result" in str(exc_info.value)

    @patch.dict(
        "os.environ",
        {"ROBINHOOD_USERNAME": "test@example.com", "ROBINHOOD_PASSWORD": "secret"},
        clear=True,
    )
    @patch("robinhood_mcp.auth._clear_stale_pickle")
    @patch("robinhood_mcp.auth.rh.login")
    def test_preserves_auth_error_when_cleanup_fails(
        self, mock_login: MagicMock, mock_clear_stale_pickle: MagicMock
    ):
        """Should keep original AuthenticationError if cache cleanup raises OSError."""
        mock_login.return_value = None
        mock_clear_stale_pickle.side_effect = OSError("permission denied")

        with pytest.raises(AuthenticationError) as exc_info:
            login()

        assert "Login returned empty result" in str(exc_info.value)

    @patch.dict(
        "os.environ",
        {"ROBINHOOD_USERNAME": "test@example.com", "ROBINHOOD_PASSWORD": "secret"},
        clear=True,
    )
    @patch("robinhood_mcp.auth._clear_stale_pickle")
    @patch("robinhood_mcp.auth.rh.login")
    def test_preserves_wrapped_login_error_when_cleanup_fails(
        self, mock_login: MagicMock, mock_clear_stale_pickle: MagicMock
    ):
        """Should still raise wrapped login AuthenticationError if cleanup fails."""
        mock_login.side_effect = RuntimeError("network down")
        mock_clear_stale_pickle.side_effect = OSError("permission denied")

        with pytest.raises(AuthenticationError) as exc_info:
            login()

        assert "Login failed: network down" in str(exc_info.value)


class TestClearStalePickle:
    """Tests for stale session cache cleanup."""

    @patch("robinhood_mcp.auth.os.path.isfile")
    @patch("robinhood_mcp.auth.os.remove")
    @patch("robinhood_mcp.auth.logger.exception")
    def test_logs_and_reraises_oserror(
        self,
        mock_logger_exception: MagicMock,
        mock_remove: MagicMock,
        mock_isfile: MagicMock,
    ):
        """Should log and re-raise OSError when cache removal fails."""
        mock_isfile.return_value = True
        mock_remove.side_effect = OSError("permission denied")

        with pytest.raises(OSError):
            _clear_stale_pickle()

        mock_logger_exception.assert_called_once()


class TestLogout:
    """Tests for logout function."""

    @patch("robinhood_mcp.auth.rh.logout")
    def test_calls_robin_stocks_logout(self, mock_logout: MagicMock):
        """Should call robin_stocks logout."""
        logout()
        mock_logout.assert_called_once()

    @patch("robinhood_mcp.auth.rh.logout")
    def test_ignores_logout_errors(self, mock_logout: MagicMock):
        """Should not raise on logout errors."""
        mock_logout.side_effect = Exception("Network error")

        # Should not raise
        logout()


class TestIsLoggedIn:
    """Tests for is_logged_in function."""

    @patch("robinhood_mcp.auth.rh.profiles.load_account_profile")
    def test_returns_true_when_logged_in(self, mock_profile: MagicMock):
        """Should return True when profile loads successfully."""
        mock_profile.return_value = {"account_number": "12345"}

        assert is_logged_in() is True

    @patch("robinhood_mcp.auth.rh.profiles.load_account_profile")
    def test_returns_false_when_not_logged_in(self, mock_profile: MagicMock):
        """Should return False when profile fails to load."""
        mock_profile.side_effect = Exception("Not authenticated")

        assert is_logged_in() is False

    @patch("robinhood_mcp.auth.rh.profiles.load_account_profile")
    def test_returns_false_for_none_result(self, mock_profile: MagicMock):
        """Should return False when profile returns None."""
        mock_profile.return_value = None

        assert is_logged_in() is False
