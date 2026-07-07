"""Auth configuration — loads secrets and OAuth settings from environment."""

import os


def _require_env(name: str) -> str:
    """Return an env var or raise with a clear message at import time."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is not set. "
            f"Set it in .env or export it before starting the API."
        )
    return value


# Required — used for JWT signing
SECRET_KEY: str = _require_env("OVID_SECRET_KEY")

# Required — declares the deployment environment (no default; the app refuses to
# boot until an operator declares it). Mirrors the SECRET_KEY fail-fast above so
# "someone forgot to flip the dev bypass off in prod" is impossible (D-09).
OVID_ENV: str = _require_env("OVID_ENV")
if OVID_ENV not in ("development", "production"):
    raise RuntimeError(
        f"OVID_ENV must be 'development' or 'production', got {OVID_ENV!r}."
    )

# Single source of truth for the IndieAuth localhost bypass (AUTH-10). Derived
# solely from OVID_ENV and False under production, so routes.py never recomputes
# or hardcodes it — the bypass is unreachable in production by construction.
ALLOW_LOCALHOST_BYPASS: bool = OVID_ENV != "production"

# Explicit import-time production-safety assertion (ROADMAP criterion 6 /
# AUTH-10). Structurally unreachable given the derivation above, but it documents
# and enforces the invariant: production can never enable the localhost bypass.
if OVID_ENV == "production" and ALLOW_LOCALHOST_BYPASS:
    raise RuntimeError(
        "Invariant violation: ALLOW_LOCALHOST_BYPASS must be False when "
        "OVID_ENV=production."
    )

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
