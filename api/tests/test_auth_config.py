"""Import-time boot-guard tests for OVID_ENV (AUTH-10, D-09).

OVID_ENV is a REQUIRED env var with no default. ``api/app/auth/config.py``
raises at IMPORT time if it is unset or invalid, and derives
``ALLOW_LOCALHOST_BYPASS`` solely from it (False under production, True
otherwise). The IndieAuth localhost bypass consumes this single constant, so it
is provably unreachable when ``OVID_ENV=production``.

Because the assertion fires at module import and module-level constants persist
across ``importlib.reload()`` within one process, each case runs in a FRESH
subprocess with a controlled ``env`` dict — a subprocess (not reload) is the
only way to observe the true import-time behavior for every value in isolation.
"""

import os
import subprocess
import sys
from pathlib import Path

# api root (parent of tests/) so `import app.auth.config` resolves in the child;
# with `python -c`, sys.path[0] is the cwd, so `app` is importable from here.
_API_ROOT = Path(__file__).resolve().parent.parent


def _run_import(ovid_env: str | None, *, print_bypass: bool = False) -> subprocess.CompletedProcess:
    """Import ``app.auth.config`` in a fresh subprocess with a controlled env.

    Always supplies the other import-time requirements (DATABASE_URL,
    OVID_SECRET_KEY) so OVID_ENV is the only variable under test. ``ovid_env``
    of ``None`` omits OVID_ENV entirely (the unset case). When ``print_bypass``
    is set, the child prints ``BYPASS=<value>`` for ALLOW_LOCALHOST_BYPASS.
    """
    env = {
        "DATABASE_URL": "sqlite://",
        "OVID_SECRET_KEY": "test-secret-key-for-unit-tests-32b",
    }
    # Preserve PATH so the interpreter can locate shared libs; keep env minimal
    # otherwise so no ambient OVID_ENV leaks in from the parent shell.
    if "PATH" in os.environ:
        env["PATH"] = os.environ["PATH"]
    if ovid_env is not None:
        env["OVID_ENV"] = ovid_env
    code = "import app.auth.config as c"
    if print_bypass:
        code += "\nprint('BYPASS=' + str(c.ALLOW_LOCALHOST_BYPASS))"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_API_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


def test_unset_ovid_env_refuses_boot():
    """OVID_ENV unset -> import raises (fail-fast), non-zero exit (D-09)."""
    result = _run_import(None)
    assert result.returncode != 0, result.stdout
    assert "OVID_ENV" in result.stderr


def test_invalid_ovid_env_refuses_boot():
    """OVID_ENV set to an unrecognized value -> RuntimeError, non-zero exit."""
    result = _run_import("banana")
    assert result.returncode != 0, result.stdout
    assert "OVID_ENV" in result.stderr


def test_development_boot_enables_localhost_bypass():
    """OVID_ENV=development -> boots, ALLOW_LOCALHOST_BYPASS is True."""
    result = _run_import("development", print_bypass=True)
    assert result.returncode == 0, result.stderr
    assert "BYPASS=True" in result.stdout


def test_production_boot_disables_localhost_bypass():
    """OVID_ENV=production -> boots, ALLOW_LOCALHOST_BYPASS is False (AUTH-10)."""
    result = _run_import("production", print_bypass=True)
    assert result.returncode == 0, result.stderr
    assert "BYPASS=False" in result.stdout
