"""Robinhood authentication module with TOTP support."""

import os
from typing import Any

import pyotp
import robin_stocks.robinhood as rh
from dotenv import load_dotenv


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


def get_totp_code(secret: str | None) -> str | None:
    """Generate TOTP code from secret if provided.

    Args:
        secret: Base32-encoded TOTP secret from Robinhood 2FA setup.

    Returns:
        6-digit TOTP code or None if no secret provided.
    """
    if not secret:
        return None
    try:
        totp = pyotp.TOTP(secret)
        return totp.now()
    except Exception as e:
        raise AuthenticationError(f"Failed to generate TOTP code: {e}") from e


def login(
    username: str | None = None,
    password: str | None = None,
    totp_secret: str | None = None,
) -> dict[str, Any]:
    """Login to Robinhood with optional TOTP 2FA.

    Credentials can be passed directly or read from environment variables:
    - ROBINHOOD_USERNAME
    - ROBINHOOD_PASSWORD
    - ROBINHOOD_TOTP_SECRET (optional)

    Args:
        username: Robinhood account email.
        password: Robinhood account password.
        totp_secret: Optional TOTP secret for 2FA.

    Returns:
        Login response dict from robin_stocks.

    Raises:
        AuthenticationError: If credentials missing or login fails.
    """
    load_dotenv()

    username = username or os.getenv("ROBINHOOD_USERNAME")
    password = password or os.getenv("ROBINHOOD_PASSWORD")
    totp_secret = totp_secret or os.getenv("ROBINHOOD_TOTP_SECRET")

    if not username or not password:
        raise AuthenticationError(
            "ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD environment variables required"
        )

    # Generate TOTP code if secret provided
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

        return result

    except Exception as e:
        if "mfa" in str(e).lower() or "2fa" in str(e).lower():
            raise AuthenticationError(
                "2FA required but ROBINHOOD_TOTP_SECRET not provided or invalid"
            ) from e
        raise AuthenticationError(f"Login failed: {e}") from e


def logout() -> None:
    """Logout from Robinhood and clear session."""
    try:
        rh.logout()
    except Exception:
        pass  # Ignore logout errors


def is_logged_in() -> bool:
    """Check if currently logged in to Robinhood.

    Returns:
        True if logged in, False otherwise.
    """
    try:
        # Try to fetch something that requires auth
        result = rh.profiles.load_account_profile()
        return result is not None
    except Exception:
        return False
