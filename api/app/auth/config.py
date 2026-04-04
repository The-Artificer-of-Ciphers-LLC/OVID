"""Auth configuration — loads secrets and OAuth settings from environment.

Validates critical secrets at import time so misconfiguration is caught
at startup rather than causing runtime failures.
"""

import base64
import logging
import os

logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    """Return an env var or raise with a clear message at import time."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is not set. "
            f"Set it in .env or export it before starting the API."
        )
    return value


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_secret_key(key: str) -> str:
    """Validate JWT signing key strength.  Fails fast if too short.

    Args:
        key: The OVID_SECRET_KEY value.

    Returns:
        The key, unchanged.

    Raises:
        RuntimeError: If key is shorter than 32 bytes.
    """
    key_bytes = len(key.encode("utf-8"))
    if key_bytes < 32:
        raise RuntimeError(
            f"OVID_SECRET_KEY is too short ({key_bytes} bytes). "
            "Must be at least 32 bytes for HS256 signing security. "
            'Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return key


def _validate_apple_key_if_set() -> None:
    """Validate Apple Sign-In private key if configured.  Skip if unset.

    Accepts the key as raw PEM text or as base64-encoded PEM.

    Raises:
        RuntimeError: If APPLE_PRIVATE_KEY is set but cannot be loaded
            as an EC private key.
    """
    raw = os.environ.get("APPLE_PRIVATE_KEY", "")
    if not raw:
        return  # Not configured — Apple Sign-In provider just won't appear

    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    # If it doesn't look like PEM, try base64-decoding first
    if "BEGIN" not in raw:
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except Exception:
            raise RuntimeError(
                "APPLE_PRIVATE_KEY is set but is not valid base64 or PEM. "
                "Provide the ES256 private key as PEM text or base64-encoded PEM."
            )

    try:
        load_pem_private_key(raw.encode("utf-8"), password=None)
    except Exception as exc:
        raise RuntimeError(
            f"APPLE_PRIVATE_KEY is set but cannot be loaded as an EC private key: {exc}"
        )

    logger.info("apple_private_key_validated")


# ---------------------------------------------------------------------------
# Module-level configuration — validated at import time
# ---------------------------------------------------------------------------

# Required — used for JWT signing
SECRET_KEY: str = _validate_secret_key(_require_env("OVID_SECRET_KEY"))

# Validate Apple key at startup (no-op if unset)
_validate_apple_key_if_set()

# JWT lifetime in days (default 30)
JWT_EXPIRY_DAYS: int = int(os.environ.get("OVID_JWT_EXPIRY_DAYS", "30"))

# Optional OAuth provider settings — loaded but not required until
# the OAuth callback endpoints are implemented (T02/T03).
GITHUB_CLIENT_ID: str | None = os.environ.get("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET: str | None = os.environ.get("GITHUB_CLIENT_SECRET")
APPLE_CLIENT_ID: str | None = os.environ.get("APPLE_CLIENT_ID")
APPLE_TEAM_ID: str | None = os.environ.get("APPLE_TEAM_ID")
APPLE_KEY_ID: str | None = os.environ.get("APPLE_KEY_ID")
OVID_API_URL: str | None = os.environ.get("OVID_API_URL")
