"""Tests for authentication module."""

from unittest.mock import MagicMock, patch

import pytest

from robinhood_mcp.auth import (
    AuthenticationError,
    _clear_stale_pickle,
    _patched_validate_sherrif_id,
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
    @patch("robinhood_mcp.auth._clear_stale_pickle")
    @patch("robinhood_mcp.auth.is_logged_in")
    @patch("robinhood_mcp.auth.rh.login")
    def test_treats_empty_result_as_success_when_session_is_valid(
        self,
        mock_login: MagicMock,
        mock_is_logged_in: MagicMock,
        mock_clear_stale_pickle: MagicMock,
    ):
        """Should recover when robin_stocks returns no payload but session is valid."""
        mock_login.return_value = None
        mock_is_logged_in.return_value = True

        result = login()

        assert result["recovered_empty_result"] is True
        assert result["session_valid"] is True
        assert "active Robinhood session" in result["detail"]
        mock_clear_stale_pickle.assert_not_called()

    @patch.dict(
        "os.environ",
        {"ROBINHOOD_USERNAME": "test@example.com", "ROBINHOOD_PASSWORD": "secret"},
        clear=True,
    )
    @patch("robinhood_mcp.auth._clear_stale_pickle")
    @patch("robinhood_mcp.auth.is_logged_in")
    @patch("robinhood_mcp.auth.rh.login")
    def test_raises_on_empty_result_without_valid_session(
        self,
        mock_login: MagicMock,
        mock_is_logged_in: MagicMock,
        mock_clear_stale_pickle: MagicMock,
    ):
        """Should still raise when robin_stocks returns no payload and no session exists."""
        mock_login.return_value = None
        mock_is_logged_in.return_value = False

        with pytest.raises(AuthenticationError) as exc_info:
            login()

        assert "empty result" in str(exc_info.value)
        mock_clear_stale_pickle.assert_called_once()

    @patch.dict(
        "os.environ",
        {"ROBINHOOD_USERNAME": "test@example.com", "ROBINHOOD_PASSWORD": "secret"},
        clear=True,
    )
    @patch("robinhood_mcp.auth.rh.login")
    def test_redirects_robin_stocks_stdout_to_stderr(
        self, mock_login: MagicMock, capsys: pytest.CaptureFixture[str]
    ):
        """Should keep third-party login chatter off stdout for MCP safety."""

        def fake_login(**_: str) -> dict[str, str]:
            print("Starting login process...")
            print("Verification required, handling challenge...")
            return {"access_token": "test"}

        mock_login.side_effect = fake_login

        result = login()
        captured = capsys.readouterr()

        assert result == {"access_token": "test"}
        assert captured.out == ""
        assert "[robinhood-mcp][robin_stocks] Starting login process..." in captured.err
        assert (
            "[robinhood-mcp][robin_stocks] Verification required, handling challenge..."
            in captured.err
        )

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


class TestPatchedValidationWorkflow:
    """Tests for the patched Robinhood verification workflow."""

    @patch("robinhood_mcp.auth.time.sleep", return_value=None)
    @patch("robinhood_mcp.auth.time.time", side_effect=range(0, 500, 5))
    @patch("robinhood_mcp.auth.request_get")
    @patch("robinhood_mcp.auth.request_post")
    def test_retries_when_prompt_status_response_is_empty(
        self,
        mock_request_post: MagicMock,
        mock_request_get: MagicMock,
        _mock_time: MagicMock,
        _mock_sleep: MagicMock,
    ):
        """Should keep polling when prompt status endpoint briefly returns None."""
        mock_request_post.side_effect = [
            {"id": "inq-123"},
            {"context": {"result": "workflow_status_approved"}},
        ]
        mock_request_get.side_effect = [
            {"context": {"sheriff_challenge": {"id": "challenge-123"}}},
            None,
            {"challenge_status": "validated"},
        ]

        _patched_validate_sherrif_id("device-token", "workflow-id")

        assert mock_request_get.call_count == 3

    @patch("robinhood_mcp.auth.time.sleep", return_value=None)
    @patch("robinhood_mcp.auth.time.time", side_effect=range(0, 500, 5))
    @patch("robinhood_mcp.auth.request_get")
    @patch("robinhood_mcp.auth.request_post")
    def test_retries_when_workflow_result_is_empty_after_approval(
        self,
        mock_request_post: MagicMock,
        mock_request_get: MagicMock,
        _mock_time: MagicMock,
        _mock_sleep: MagicMock,
    ):
        """Should keep polling when approval is recorded before workflow result is ready."""
        mock_request_post.side_effect = [
            {"id": "inq-123"},
            None,
            {"context": {"result": "workflow_status_approved"}},
        ]
        mock_request_get.side_effect = [
            {"context": {"sheriff_challenge": {"id": "challenge-123"}}},
            {"challenge_status": "validated"},
            {"challenge_status": "validated"},
        ]

        _patched_validate_sherrif_id("device-token", "workflow-id")

        assert mock_request_post.call_count == 3

    @patch("robinhood_mcp.auth.time.sleep", return_value=None)
    @patch("robinhood_mcp.auth.time.time", side_effect=range(0, 500, 5))
    @patch("robinhood_mcp.auth.request_get")
    @patch("robinhood_mcp.auth.request_post")
    def test_retries_when_workflow_context_is_null_after_approval(
        self,
        mock_request_post: MagicMock,
        mock_request_get: MagicMock,
        _mock_time: MagicMock,
        _mock_sleep: MagicMock,
    ):
        """Should tolerate Robinhood returning {'context': None} before finalization."""
        mock_request_post.side_effect = [
            {"id": "inq-123"},
            {"context": None, "type_context": None},
            {"context": {"result": "workflow_status_approved"}},
        ]
        mock_request_get.side_effect = [
            {"context": {"sheriff_challenge": {"id": "challenge-123"}}},
            {"challenge_status": "validated"},
            {"challenge_status": "validated"},
        ]

        _patched_validate_sherrif_id("device-token", "workflow-id")

        assert mock_request_post.call_count == 3


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
