"""Robinhood authentication module.

Supports both TOTP-based 2FA (authenticator app) and the newer
verification_workflow device-approval flow (required since Dec 2024).
On first run the server prints a prompt to approve the login in the
Robinhood mobile app; after that the session is cached in
~/.tokens/robinhood.pickle so no interaction is needed on restart.

Key insight: robin_stocks' rh.login() handles verification_workflow
INTERNALLY via _validate_sherrif_id — it never returns the workflow
dict to the caller. The PyPI version of that function is broken
(calls input() which blocks forever on a headless server). We
monkey-patch it at import time with a polling-based version that
sends a push notification and waits for mobile app approval.
"""

import inspect
import io
import logging
import os
import sys
import time
from contextlib import redirect_stdout
from typing import Any

import pyotp
import robin_stocks.robinhood as rh
import robin_stocks.robinhood.authentication as rh_auth
from dotenv import load_dotenv
from robin_stocks.robinhood.helper import request_get, request_post

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class EnvironmentVariablesError(AuthenticationError):
    """Raised when required authentication environment variables are missing."""

    pass


# ---------------------------------------------------------------------------
# Monkey-patch robin_stocks' broken _validate_sherrif_id with a working
# polling-based version that doesn't call input().
# ---------------------------------------------------------------------------


def _dict_or_empty(value: Any) -> dict[str, Any]:
    """Normalize optional Robinhood payload fragments to dictionaries."""
    return value if isinstance(value, dict) else {}


def _request_workflow_result(inquiries_url: str) -> str | None:
    """Ask Robinhood whether an approved challenge has finalized the workflow."""
    inq_resp = request_post(
        url=inquiries_url,
        payload={"sequence": 0, "user_input": {"status": "continue"}},
        json=True,
    )
    if not isinstance(inq_resp, dict):
        return None
    context = _dict_or_empty(inq_resp.get("context"))
    type_context = _dict_or_empty(inq_resp.get("type_context"))
    return context.get("result") or type_context.get("result", "")


def _patched_validate_sherrif_id(
    device_token: str, workflow_id: str, mfa_code: str | None = None
) -> None:
    """Replacement for robin_stocks' _validate_sherrif_id.

    Uses the /push/{id}/get_prompts_status/ polling endpoint instead of
    the broken /challenge/{id}/respond/ POST, and never calls input().
    """
    user_machine_url = "https://api.robinhood.com/pathfinder/user_machine/"
    payload = {
        "device_id": device_token,
        "flow": "suv",
        "input": {"workflow_id": workflow_id},
    }
    data = request_post(url=user_machine_url, payload=payload, json=True)

    if not isinstance(data, dict) or "id" not in data:
        raise AuthenticationError("Verification workflow failed — missing inquiry ID")

    inquiries_url = f"https://api.robinhood.com/pathfinder/inquiries/{data['id']}/user_view/"
    res = request_get(inquiries_url)
    if not isinstance(res, dict):
        raise AuthenticationError("Verification workflow failed — missing inquiry details")

    # API changed key from type_context.context → context
    ctx = _dict_or_empty(res.get("context"))
    if not ctx:
        ctx = _dict_or_empty(_dict_or_empty(res.get("type_context")).get("context"))
    challenge_id = _dict_or_empty(ctx.get("sheriff_challenge")).get("id")
    if not challenge_id:
        inquiry_id = data.get("id")
        details = f" for inquiry {inquiry_id}" if inquiry_id else ""
        raise AuthenticationError(
            f"Verification workflow failed — missing sheriff challenge ID{details}"
        )

    # If TOTP mfa_code is available, try direct challenge response first
    if mfa_code:
        challenge_url = f"https://api.robinhood.com/challenge/{challenge_id}/respond/"
        resp = request_post(url=challenge_url, payload={"response": mfa_code}, json=True)
        if not isinstance(resp, dict):
            raise AuthenticationError("TOTP challenge response was empty")
        if resp.get("status") == "validated":
            result = _request_workflow_result(inquiries_url)
            if result == "workflow_status_approved":
                return
            if not result:
                raise AuthenticationError("TOTP validated but workflow result was empty")
            raise AuthenticationError(f"TOTP validated but workflow not approved: {result}")

    # Poll for mobile app approval
    prompts_url = f"https://api.robinhood.com/push/{challenge_id}/get_prompts_status/"
    print(
        "\n[robinhood-mcp] Verification required — open the Robinhood app and approve the login.\n"
        "[robinhood-mcp] Waiting up to 2 minutes...",
        file=sys.stderr,
    )

    start = time.time()
    while time.time() - start < 120:
        time.sleep(5)
        status_res = request_get(url=prompts_url)
        elapsed = int(time.time() - start)
        if not isinstance(status_res, dict):
            print(
                f"[robinhood-mcp] Approval status unavailable, retrying... ({elapsed}s)",
                file=sys.stderr,
            )
            continue
        if status_res.get("challenge_status") == "validated":
            result = _request_workflow_result(inquiries_url)
            if result == "workflow_status_approved":
                print("[robinhood-mcp] Login approved!", file=sys.stderr)
                return
            if not result:
                print(
                    "[robinhood-mcp] Approval recorded, waiting for workflow "
                    f"finalization... ({elapsed}s)",
                    file=sys.stderr,
                )
                continue
            raise AuthenticationError(f"Challenge validated but workflow not approved: {result}")
        print(f"[robinhood-mcp] Waiting for approval... ({elapsed}s)", file=sys.stderr)

    raise AuthenticationError("Login timed out after 2 minutes. Restart server and approve in app.")


# Apply the monkey-patch before any login calls
_target = getattr(rh_auth, "_validate_sherrif_id", None)
if callable(_target):
    _params = tuple(inspect.signature(_target).parameters)
    if _params[:2] == ("device_token", "workflow_id"):
        rh_auth._validate_sherrif_id = _patched_validate_sherrif_id
    else:
        print(
            "[robinhood-mcp] WARNING: unexpected _validate_sherrif_id "
            f"signature {_params}. Upstream robin_stocks API may have changed.",
            file=sys.stderr,
        )
else:
    print(
        "[robinhood-mcp] WARNING: rh_auth._validate_sherrif_id not found "
        "or not callable. The upstream robin_stocks API may have changed "
        "— consider pinning or upgrading the dependency.",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_totp_code(secret: str | None) -> str | None:
    """Generate TOTP code from a base32 authenticator-app secret."""
    if not secret:
        return None
    try:
        return pyotp.TOTP(secret).now()
    except Exception as e:
        raise AuthenticationError(f"Failed to generate TOTP code: {e}") from e


def _clear_stale_pickle() -> None:
    """Remove cached session pickle so a fresh login is forced."""
    pickle_path = os.path.join(os.path.expanduser("~"), ".tokens", "robinhood.pickle")
    if os.path.isfile(pickle_path):
        try:
            os.remove(pickle_path)
            print(f"[robinhood-mcp] Cleared stale session cache: {pickle_path}", file=sys.stderr)
        except OSError as e:
            logger.exception("Failed to clear stale session cache at %s: %s", pickle_path, e)
            raise


def _emit_captured_login_stdout(output: str) -> None:
    """Forward robin_stocks stdout chatter to stderr for MCP-safe logging."""
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line:
            print(f"[robinhood-mcp][robin_stocks] {line}", file=sys.stderr)


def _login_with_captured_stdout(
    *, username: str, password: str, mfa_code: str | None
) -> dict[str, Any] | None:
    """Run robin_stocks login without letting stdout corrupt MCP JSON-RPC transport."""
    stdout_buffer = io.StringIO()
    try:
        with redirect_stdout(stdout_buffer):
            return rh.login(
                username=username,
                password=password,
                mfa_code=mfa_code,
                store_session=True,
            )
    finally:
        _emit_captured_login_stdout(stdout_buffer.getvalue())


def login(
    username: str | None = None,
    password: str | None = None,
    totp_secret: str | None = None,
) -> dict[str, Any]:
    """Login to Robinhood.

    Credentials are read from environment variables if not passed directly:
    - ROBINHOOD_USERNAME
    - ROBINHOOD_PASSWORD
    - ROBINHOOD_TOTP_SECRET  (optional — only needed for authenticator-app 2FA)

    On first login the session token is cached in ~/.tokens/robinhood.pickle.
    Subsequent logins load from cache without any 2FA interaction.

    Raises:
        AuthenticationError: If credentials are missing or login fails.
    """
    load_dotenv()

    username = username or os.getenv("ROBINHOOD_USERNAME")
    password = password or os.getenv("ROBINHOOD_PASSWORD")
    totp_secret = totp_secret or os.getenv("ROBINHOOD_TOTP_SECRET")

    if not username or not password:
        raise EnvironmentVariablesError(
            "ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD environment variables required"
        )

    mfa_code = get_totp_code(totp_secret)

    try:
        result = _login_with_captured_stdout(
            username=username,
            password=password,
            mfa_code=mfa_code,
        )

        if not result:
            if is_logged_in():
                return {
                    "detail": (
                        "logged in with active Robinhood session after empty login result"
                    ),
                    "recovered_empty_result": True,
                    "session_valid": True,
                }
            raise AuthenticationError("Login returned empty result")

        return result

    except AuthenticationError as e:
        if not isinstance(e, EnvironmentVariablesError):
            try:
                _clear_stale_pickle()
            except OSError:
                logger.warning(
                    "Ignoring stale session cache cleanup failure while propagating auth error",
                    exc_info=True,
                )
        raise
    except Exception as e:
        # If login failed, clear pickle so next attempt starts clean
        try:
            _clear_stale_pickle()
        except OSError:
            logger.warning(
                "Ignoring stale session cache cleanup failure while handling login exception",
                exc_info=True,
            )
        raise AuthenticationError(f"Login failed: {e}") from e


def logout() -> None:
    """Logout from Robinhood and clear session."""
    try:
        rh.logout()
    except Exception:
        pass


def is_logged_in() -> bool:
    """Check if the current session is still valid."""
    try:
        result = rh.profiles.load_account_profile()
        return result is not None
    except Exception:
        return False
