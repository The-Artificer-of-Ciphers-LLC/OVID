"""Backend-selection tests for the env-driven rate limiter (INFRA-01).

The app-level ``limiter`` is a module global whose storage backend is chosen
once at import time from ``REDIS_URL``. Because that choice is import-time and
process-global, we probe it in **subprocess isolation** rather than reloading
the module in-process (which would pollute the shared limiter for every other
test). Each subprocess imports ``app.rate_limit`` under a controlled
environment and prints the active storage class name.

Also pins the two tunable named constants the rest of the phase consumes
(``AUTH_WRITE_LIMIT`` for Plan 02, ``FALLBACK_LIMIT`` for the outage cap).
"""

import subprocess
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent  # api/


def _probe_storage_class(env_overrides: dict[str, str]) -> str:
    """Import app.rate_limit in a fresh interpreter and return the storage class.

    A minimal, explicit environment is passed so the parent test process's
    variables (e.g. a stray REDIS_URL) never leak into the probe.
    """
    env = {
        "DATABASE_URL": "sqlite://",
        "OVID_SECRET_KEY": "test-secret-key-for-unit-tests-32b",
        "PATH": str(Path(sys.executable).parent),
    }
    env.update(env_overrides)
    code = (
        "import app.rate_limit as rl; "
        "print(type(rl.limiter._storage).__name__)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(API_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"probe exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return result.stdout.strip()


def test_redis_url_selects_redis_storage() -> None:
    """With REDIS_URL set, the app limiter's active storage is RedisStorage."""
    backend = _probe_storage_class({"REDIS_URL": "redis://localhost:6379/0"})
    assert backend == "RedisStorage", (
        f"Expected RedisStorage when REDIS_URL is set, got {backend!r}"
    )


def test_no_redis_url_selects_memory_storage() -> None:
    """With REDIS_URL unset, the limiter preserves today's memory:// default."""
    backend = _probe_storage_class({})  # REDIS_URL deliberately absent
    assert backend == "MemoryStorage", (
        f"Expected MemoryStorage when REDIS_URL is unset, got {backend!r}"
    )


def test_tunable_constants_defined() -> None:
    """AUTH_WRITE_LIMIT (Plan 02) and FALLBACK_LIMIT (outage cap) are named constants."""
    from app.rate_limit import AUTH_WRITE_LIMIT, FALLBACK_LIMIT

    assert AUTH_WRITE_LIMIT == "20/minute;300/hour", AUTH_WRITE_LIMIT
    assert FALLBACK_LIMIT == "60/minute", FALLBACK_LIMIT


def _probe_read_limits(env_overrides: dict[str, str]) -> tuple[str, str]:
    """Import app.rate_limit in a fresh interpreter and return (UNAUTH_LIMIT, AUTH_LIMIT).

    Subprocess-isolated for the same reason as ``_probe_storage_class`` above:
    the read-tier limits are read once at import time onto module globals, and
    reloading in-process would pollute the shared limiter for every other test.
    """
    env = {
        "DATABASE_URL": "sqlite://",
        "OVID_SECRET_KEY": "test-secret-key-for-unit-tests-32b",
        "PATH": str(Path(sys.executable).parent),
    }
    env.update(env_overrides)
    code = "import app.rate_limit as rl; print(rl.UNAUTH_LIMIT); print(rl.AUTH_LIMIT)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(API_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"probe exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    unauth, auth = result.stdout.strip().splitlines()
    return unauth, auth


def test_read_limit_env_defaults_preserved() -> None:
    """Without overrides, UNAUTH_LIMIT/AUTH_LIMIT keep today's hardcoded defaults (CR-01)."""
    unauth, auth = _probe_read_limits({})
    assert unauth == "100/minute", unauth
    assert auth == "500/minute", auth


def test_read_limit_env_overrides_are_honored() -> None:
    """OVID_UNAUTH_LIMIT / OVID_AUTH_LIMIT override the read-tier defaults (CR-01).

    The load-test harness raises these (see .github/workflows/loadtest.yml and
    loadtest/locustfile.py) so read traffic isn't throttled before p95 can be
    measured.
    """
    unauth, auth = _probe_read_limits(
        {"OVID_UNAUTH_LIMIT": "100000000/minute", "OVID_AUTH_LIMIT": "100000000/minute"}
    )
    assert unauth == "100000000/minute", unauth
    assert auth == "100000000/minute", auth
