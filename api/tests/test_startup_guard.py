"""Fail-fast startup-guard tests for the rate limiter (D-06).

Multi-worker gunicorn on a ``memory://`` store gives each worker an independent
counter — silent Nx rate-limit inflation. The guard turns that misconfiguration
into a loud, import-time ``RuntimeError`` instead of a quietly weakened control.

Import-time behavior cannot be safely re-triggered on the module global within
one interpreter, so every case runs in **subprocess isolation** with a
controlled environment, asserting exit code and stderr. The guard reads an
explicit env var (``OVID_WORKERS``, fallback ``WEB_CONCURRENCY``) — never
gunicorn argv (D-06 rejects fragile scraping).
"""

import subprocess
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent  # api/


def _import_rate_limit(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    """Import app.rate_limit in a fresh interpreter under a controlled env."""
    env = {
        "DATABASE_URL": "sqlite://",
        "OVID_SECRET_KEY": "test-secret-key-for-unit-tests-32b",
        "OVID_ENV": "development",
        "PATH": str(Path(sys.executable).parent),
    }
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "import app.rate_limit"],
        cwd=str(API_DIR),
        env=env,
        capture_output=True,
        text=True,
    )


def test_multiworker_without_redis_refuses_to_boot() -> None:
    """OVID_WORKERS>1 + no REDIS_URL → non-zero exit with a RuntimeError."""
    result = _import_rate_limit({"OVID_WORKERS": "2"})
    assert result.returncode != 0, (
        f"Expected a non-zero exit for multi-worker memory://, got 0.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "RuntimeError" in result.stderr, result.stderr
    # Message must name the worker count and point at the fix.
    assert "2" in result.stderr, result.stderr
    assert "REDIS_URL" in result.stderr, result.stderr


def test_multiworker_with_redis_boots_clean() -> None:
    """OVID_WORKERS>1 WITH REDIS_URL set imports cleanly (shared store)."""
    result = _import_rate_limit(
        {"OVID_WORKERS": "4", "REDIS_URL": "redis://localhost:6379/0"}
    )
    assert result.returncode == 0, (
        f"Expected clean import with REDIS_URL set, got {result.returncode}.\n"
        f"stderr: {result.stderr}"
    )


def test_single_worker_boots_clean_without_redis() -> None:
    """OVID_WORKERS unset (single-worker self-host) imports cleanly on memory://."""
    result = _import_rate_limit({})  # OVID_WORKERS + REDIS_URL both absent
    assert result.returncode == 0, (
        f"Expected clean single-worker import, got {result.returncode}.\n"
        f"stderr: {result.stderr}"
    )


def test_web_concurrency_fallback_env_is_honored() -> None:
    """WEB_CONCURRENCY>1 (gunicorn's own var) + no REDIS_URL also refuses to boot."""
    result = _import_rate_limit({"WEB_CONCURRENCY": "3"})
    assert result.returncode != 0, (
        f"Expected non-zero exit for WEB_CONCURRENCY multi-worker, got 0.\n"
        f"stderr: {result.stderr}"
    )
    assert "RuntimeError" in result.stderr, result.stderr


def test_non_numeric_workers_raises_actionable_runtime_error() -> None:
    """OVID_WORKERS='four' raises an actionable RuntimeError, not an opaque
    ValueError (WR-04)."""
    result = _import_rate_limit({"OVID_WORKERS": "four"})
    assert result.returncode != 0, (
        f"Expected a non-zero exit for non-numeric OVID_WORKERS, got 0.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # The process's final, uncaught exception must be the actionable
    # RuntimeError — not a bare ValueError terminating the interpreter.
    last_line = result.stderr.rstrip().splitlines()[-1]
    assert last_line.startswith("RuntimeError"), result.stderr
    assert "four" in result.stderr, result.stderr
    assert "OVID_WORKERS" in result.stderr, result.stderr


def test_empty_workers_env_treated_as_unset() -> None:
    """OVID_WORKERS='' (empty string) is treated as unset, defaulting to a
    single worker rather than failing to parse (WR-04)."""
    result = _import_rate_limit({"OVID_WORKERS": ""})
    assert result.returncode == 0, (
        f"Expected a clean import with empty OVID_WORKERS (treated as unset), "
        f"got {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
