"""Robinhood authentication module.

Supports both TOTP-based 2FA (authenticator app) and the newer
verification_workflow device-approval flow (required since Dec 2024).
On first run the server prints a prompt to approve the login in the
Robinhood mobile app; after that the session is cached in
~/.tokens/robinhood.pickle so no interaction is needed on restart.
"""

import os
import sys
import time
from typing import Any

import pyotp
import robin_stocks.robinhood as rh
from robin_stocks.robinhood.helper import request_get, request_post
from dotenv import load_dotenv


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


def get_totp_code(secret: str | None) -> str | None:
    """Generate TOTP code from a base32 authenticator-app secret."""
    if not secret:
        return None
    try:
        return pyotp.TOTP(secret).now()
    except Exception as e:
        raise AuthenticationError(f"Failed to generate TOTP code: {e}") from e


def _validate_sheriff_workflow(device_token: str, workflow_id: str, mfa_code: str | None = None) -> None:
    """Handle Robinhood's verification_workflow device-approval challenge.

    Sends a push notification to the Robinhood app and polls until the user
    approves the login (up to 2 minutes). Falls back to TOTP if provided.
    """
    user_machine_url = "https://api.robinhood.com/pathfinder/user_machine/"
    payload = {
        "device_id": device_token,
        "flow": "suv",
        "input": {"workflow_id": workflow_id},
    }
    data = request_post(url=user_machine_url, payload=payload, json=True)

    if "id" not in data:
        raise AuthenticationError(f"Verification workflow failed: no inquiry ID in response: {data}")

    inquiries_url = f"https://api.robinhood.com/pathfinder/inquiries/{data['id']}/user_view/"
    res = request_get(inquiries_url)

    challenge_id = res.get("context", {}).get("sheriff_challenge", {}).get("id")
    if not challenge_id:
        raise AuthenticationError(f"Could not extract sheriff challenge ID from: {res}")

    # If TOTP is available, try it directly first
    if mfa_code:
        challenge_url = f"https://api.robinhood.com/challenge/{challenge_id}/respond/"
        challenge_response = request_post(url=challenge_url, payload={"response": mfa_code}, json=True)
        if challenge_response.get("status") == "validated":
            inquiries_payload = {"sequence": 0, "user_input": {"status": "continue"}}
            inquiries_response = request_post(url=inquiries_url, payload=inquiries_payload, json=True)
            if inquiries_response.get("type_context", {}).get("result") == "workflow_status_approved":
                return
            raise AuthenticationError("TOTP challenge validated but workflow not approved")

    # No TOTP — poll for mobile app approval
    prompts_url = f"https://api.robinhood.com/push/{challenge_id}/get_prompts_status/"
    print(
        "\n[robinhood-mcp] Verification required — open the Robinhood app and approve the login prompt.\n"
        "[robinhood-mcp] Waiting up to 2 minutes...",
        file=sys.stderr,
    )

    start = time.time()
    while time.time() - start < 120:
        time.sleep(5)
        status_res = request_get(url=prompts_url)
        if status_res.get("challenge_status") == "validated":
            inquiries_payload = {"sequence": 0, "user_input": {"status": "continue"}}
            inquiries_response = request_post(url=inquiries_url, payload=inquiries_payload, json=True)
            if inquiries_response.get("type_context", {}).get("result") == "workflow_status_approved":
                print("[robinhood-mcp] Login approved!", file=sys.stderr)
                return
            raise AuthenticationError("Challenge validated but workflow not approved")
        elapsed = int(time.time() - start)
        print(f"[robinhood-mcp] Waiting for approval... ({elapsed}s)", file=sys.stderr)

    raise AuthenticationError("Login confirmation timed out after 2 minutes. Please restart and approve in app.")


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
        raise AuthenticationError(
            "ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD environment variables required"
        )

    mfa_code = get_totp_code(totp_secret)

    try:
        result = rh.login(
            username=username,
            password=password,
            mfa_code=mfa_code,
            store_session=True,
        )

        if not result:
            raise AuthenticationError("Login returned empty result")

        # If the base login returned a verification_workflow, handle it here
        if isinstance(result, dict) and "verification_workflow" in result:
            workflow_id = result["verification_workflow"]["id"]
            import random
            device_token = "".join(
                [f"{(int(random.random() * 4294967296) >> ((3 & i) << 3)) & 255:02x}" for i in range(16)]
            )
            _validate_sheriff_workflow(device_token=device_token, workflow_id=workflow_id, mfa_code=mfa_code)
            # Re-login after approval to get actual access token
            result = rh.login(
                username=username,
                password=password,
                mfa_code=mfa_code,
                store_session=True,
            )
            if not result or "access_token" not in str(result):
                raise AuthenticationError("Re-login after approval did not return access token")

        return result

    except AuthenticationError:
        raise
    except Exception as e:
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
