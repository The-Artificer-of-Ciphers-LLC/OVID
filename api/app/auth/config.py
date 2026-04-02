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
