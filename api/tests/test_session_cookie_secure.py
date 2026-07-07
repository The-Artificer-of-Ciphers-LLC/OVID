"""Tests for the SESSION_COOKIE_SECURE env-gated Secure flag on the session
cookie (``api/main.py``, ``starlette.middleware.sessions.SessionMiddleware``).

The session cookie carries OAuth CSRF state and, per the Phase 7 option-b
provider-link flow, ``link_to_user_id`` — so it must be marked ``Secure``
(HTTPS-only) whenever the deployment is served over HTTPS.

``https_only`` is baked into the middleware stack at ``main.py`` IMPORT time
(``app.add_middleware(...)`` runs once, at module load), so — exactly like
``OVID_ENV``'s import-time boot guard in ``test_auth_config.py`` — the only
way to observe the real behavior for a *given* env value is a fresh
subprocess with a controlled environment. Reusing the module-cached ``main``
singleton (as the shared ``client`` fixture does) would not re-run the
middleware construction and would also mutate global state shared by every
other test in the suite.
"""

import os
import subprocess
import sys
from pathlib import Path

# api root (parent of tests/) so `import main` resolves in the child.
_API_ROOT = Path(__file__).resolve().parent.parent

# Child script: imports the real `main.app` (so the exact production
# middleware construction runs), adds a throwaway test-only route that writes
# to `request.session`, hits it via TestClient, and prints the raw Set-Cookie
# header so the parent process can assert on it.
_CHILD_SCRIPT = """
import sys
from fastapi import Request
from fastapi.testclient import TestClient

from main import app


@app.get("/__test_session_write")
def _write_session(request: Request):
    request.session["x"] = "y"
    return {"ok": True}


with TestClient(app) as client:
    resp = client.get("/__test_session_write")
    assert resp.status_code == 200, resp.text
    cookie_header = resp.headers.get("set-cookie", "")
    sys.stdout.write("SET-COOKIE=" + cookie_header + "\\n")
"""


def _run_session_write(session_cookie_secure: str | None) -> str:
    """Run the child script in a fresh subprocess, return the raw Set-Cookie header.

    ``session_cookie_secure`` of ``None`` omits SESSION_COOKIE_SECURE entirely
    (the unset/default case).
    """
    env = {
        "DATABASE_URL": "sqlite://",
        "OVID_SECRET_KEY": "test-secret-key-for-unit-tests-32b",
        "OVID_ENV": "development",
    }
    if "PATH" in os.environ:
        env["PATH"] = os.environ["PATH"]
    if session_cookie_secure is not None:
        env["SESSION_COOKIE_SECURE"] = session_cookie_secure

    result = subprocess.run(
        [sys.executable, "-c", _CHILD_SCRIPT],
        cwd=str(_API_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    for line in result.stdout.splitlines():
        if line.startswith("SET-COOKIE="):
            return line[len("SET-COOKIE=") :]
    raise AssertionError(f"child produced no SET-COOKIE line: {result.stdout!r}")


class TestSessionCookieSecureFlag:
    """End-to-end: real SessionMiddleware construction, real Set-Cookie header."""

    def test_unset_defaults_to_no_secure_flag(self):
        """SESSION_COOKIE_SECURE unset -> default False -> no Secure attribute.

        Load-bearing default: local http://localhost dev and the existing
        TestClient-based test suite must keep working unaffected.
        """
        cookie = _run_session_write(None)
        assert "secure" not in cookie.lower()

    def test_explicit_false_has_no_secure_flag(self):
        cookie = _run_session_write("false")
        assert "secure" not in cookie.lower()

    def test_empty_string_has_no_secure_flag(self):
        cookie = _run_session_write("")
        assert "secure" not in cookie.lower()

    def test_true_sets_secure_flag(self):
        """SESSION_COOKIE_SECURE=true -> Secure attribute present on the cookie."""
        cookie = _run_session_write("true")
        assert "secure" in cookie.lower()

    def test_one_sets_secure_flag(self):
        cookie = _run_session_write("1")
        assert "secure" in cookie.lower()

    def test_yes_sets_secure_flag(self):
        cookie = _run_session_write("yes")
        assert "secure" in cookie.lower()

    def test_mixed_case_and_whitespace_sets_secure_flag(self):
        """Parsing is case-insensitive and tolerates surrounding whitespace."""
        cookie = _run_session_write("  TRUE  ")
        assert "secure" in cookie.lower()

    def test_unrecognized_value_has_no_secure_flag(self):
        """Any value outside the truthy set is treated as false (fail-closed-safe default)."""
        cookie = _run_session_write("banana")
        assert "secure" not in cookie.lower()

    def test_same_site_lax_present(self):
        """same_site is explicitly pinned to lax (load-bearing for the provider-link
        flow's top-level cross-subdomain navigation) regardless of the Secure flag."""
        cookie = _run_session_write("true")
        assert "samesite=lax" in cookie.lower()


class TestSessionMiddlewareMechanism:
    """Proves the underlying Starlette mechanism in isolation (no app-level env
    parsing involved) — i.e. that `https_only=True` on SessionMiddleware itself
    is what produces the Secure attribute, independent of how main.py derives it."""

    def test_https_only_true_emits_secure_cookie(self):
        from starlette.applications import Starlette
        from starlette.middleware.sessions import SessionMiddleware
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient as StarletteTestClient

        async def write_session(request):
            request.session["x"] = "y"
            return JSONResponse({"ok": True})

        app = Starlette(routes=[Route("/write", write_session)])
        app.add_middleware(
            SessionMiddleware,
            secret_key="test-secret",
            https_only=True,
            same_site="lax",
        )

        with StarletteTestClient(app) as client:
            resp = client.get("/write")
        cookie = resp.headers.get("set-cookie", "")
        assert "secure" in cookie.lower()

    def test_https_only_false_omits_secure_cookie(self):
        from starlette.applications import Starlette
        from starlette.middleware.sessions import SessionMiddleware
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient as StarletteTestClient

        async def write_session(request):
            request.session["x"] = "y"
            return JSONResponse({"ok": True})

        app = Starlette(routes=[Route("/write", write_session)])
        app.add_middleware(
            SessionMiddleware,
            secret_key="test-secret",
            https_only=False,
            same_site="lax",
        )

        with StarletteTestClient(app) as client:
            resp = client.get("/write")
        cookie = resp.headers.get("set-cookie", "")
        assert "secure" not in cookie.lower()
