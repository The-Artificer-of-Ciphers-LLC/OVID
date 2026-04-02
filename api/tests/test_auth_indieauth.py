"""Tests for IndieAuth OAuth flow and endpoint discovery."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.indieauth import DiscoveryError, discover_endpoints, generate_pkce_pair, validate_url
from app.models import User, UserOAuthLink


# ---------------------------------------------------------------------------
# Unit tests — PKCE helpers
# ---------------------------------------------------------------------------

class TestGeneratePkcePair:
    def test_returns_verifier_and_challenge(self):
        verifier, challenge = generate_pkce_pair()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)
        assert len(verifier) > 20
        assert len(challenge) > 20
        assert verifier != challenge

    def test_pairs_are_unique(self):
        v1, c1 = generate_pkce_pair()
        v2, c2 = generate_pkce_pair()
        assert v1 != v2
        assert c1 != c2


# ---------------------------------------------------------------------------
# Unit tests — URL validation
# ---------------------------------------------------------------------------

class TestValidateUrl:
    def test_https_url_accepted(self):
        result = validate_url("https://example.com")
        assert result.startswith("https://")

    def test_http_rejected(self):
        with pytest.raises(ValueError, match="https"):
            validate_url("http://example.com")

    def test_http_localhost_allowed_in_dev(self):
        result = validate_url("http://localhost:8080", allow_localhost=True)
        assert "localhost" in result

    def test_http_localhost_rejected_without_flag(self):
        with pytest.raises(ValueError, match="https"):
            validate_url("http://localhost:8080", allow_localhost=False)

    def test_bare_domain_gets_https(self):
        result = validate_url("example.com")
        assert result.startswith("https://")

    def test_ftp_rejected(self):
        with pytest.raises(ValueError, match="https"):
            validate_url("ftp://example.com")

    def test_trailing_slash_normalised(self):
        result = validate_url("https://example.com")
        assert result == "https://example.com/"


# ---------------------------------------------------------------------------
# Unit tests — endpoint discovery
# ---------------------------------------------------------------------------

_DISCOVERY_HTML = """
<!DOCTYPE html>
<html>
<head>
    <link rel="authorization_endpoint" href="https://auth.example.com/auth">
    <link rel="token_endpoint" href="https://auth.example.com/token">
</head>
<body>Hello</body>
</html>
"""

_DISCOVERY_HTML_NO_ENDPOINTS = """
<!DOCTYPE html>
<html><head><title>My Blog</title></head><body>Hello</body></html>
"""

_DISCOVERY_HTML_PARTIAL = """
<!DOCTYPE html>
<html>
<head>
    <link rel="authorization_endpoint" href="https://auth.example.com/auth">
</head>
<body>Hello</body>
</html>
"""


class TestDiscoverEndpoints:
    @pytest.mark.anyio
    async def test_discovers_from_html_link_rels(self):
        """Parses authorization_endpoint and token_endpoint from HTML."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = _DISCOVERY_HTML
        mock_resp.headers = {}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.auth.indieauth.httpx.AsyncClient", return_value=mock_client):
            endpoints = await discover_endpoints("https://example.com/")

        assert endpoints["authorization_endpoint"] == "https://auth.example.com/auth"
        assert endpoints["token_endpoint"] == "https://auth.example.com/token"

    @pytest.mark.anyio
    async def test_no_endpoints_raises(self):
        """Page without link rels → DiscoveryError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = _DISCOVERY_HTML_NO_ENDPOINTS
        mock_resp.headers = {}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.auth.indieauth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(DiscoveryError, match="authorization_endpoint"):
                await discover_endpoints("https://example.com/")

    @pytest.mark.anyio
    async def test_missing_token_endpoint_raises(self):
        """Page with only authorization_endpoint → DiscoveryError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = _DISCOVERY_HTML_PARTIAL
        mock_resp.headers = {}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.auth.indieauth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(DiscoveryError, match="token_endpoint"):
                await discover_endpoints("https://example.com/")

    @pytest.mark.anyio
    async def test_timeout_raises(self):
        """httpx timeout → DiscoveryError."""
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("app.auth.indieauth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(DiscoveryError, match="timed out"):
                await discover_endpoints("https://example.com/")

    @pytest.mark.anyio
    async def test_http_error_raises(self):
        """HTTP error during fetch → DiscoveryError."""
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("404 Not Found"))

        with patch("app.auth.indieauth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(DiscoveryError, match="Failed to fetch"):
                await discover_endpoints("https://example.com/")

    @pytest.mark.anyio
    async def test_link_header_discovery(self):
        """Discovers endpoints from HTTP Link headers."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html></html>"
        mock_resp.headers = {
            "link": '<https://auth.example.com/auth>; rel="authorization_endpoint", '
                    '<https://auth.example.com/token>; rel="token_endpoint"'
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.auth.indieauth.httpx.AsyncClient", return_value=mock_client):
            endpoints = await discover_endpoints("https://example.com/")

        assert endpoints["authorization_endpoint"] == "https://auth.example.com/auth"
        assert endpoints["token_endpoint"] == "https://auth.example.com/token"


# ---------------------------------------------------------------------------
# IndieAuth login route
# ---------------------------------------------------------------------------

def _mock_discovery(endpoints=None, error=None):
    """Patch discover_endpoints to return mock endpoints or raise."""
    if error:
        return patch("app.auth.routes.discover_endpoints", AsyncMock(side_effect=error))
    if endpoints is None:
        endpoints = {
            "authorization_endpoint": "https://auth.example.com/auth",
            "token_endpoint": "https://auth.example.com/token",
        }
    return patch("app.auth.routes.discover_endpoints", AsyncMock(return_value=endpoints))


class TestIndieAuthLogin:
    def test_login_redirects_to_authorization_endpoint(self, client: TestClient):
        """Login discovers endpoints and redirects with PKCE params."""
        with _mock_discovery():
            resp = client.get(
                "/v1/auth/indieauth/login?url=https://user.example.com",
                follow_redirects=False,
            )

        assert resp.status_code == 307
        location = resp.headers["location"]
        assert "auth.example.com/auth" in location
        assert "code_challenge=" in location
        assert "code_challenge_method=S256" in location
        assert "state=" in location

    def test_login_missing_url_returns_400(self, client: TestClient):
        """No url param → 400."""
        resp = client.get("/v1/auth/indieauth/login")
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "missing_url"

    def test_login_http_url_returns_400(self, client: TestClient):
        """http:// URL (non-localhost) → 400."""
        resp = client.get("/v1/auth/indieauth/login?url=http://evil.com")
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "invalid_url"

    def test_login_discovery_fails_returns_400(self, client: TestClient):
        """Discovery error → 400."""
        with _mock_discovery(error=DiscoveryError("No endpoints")):
            resp = client.get("/v1/auth/indieauth/login?url=https://user.example.com")
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "discovery_failed"


# ---------------------------------------------------------------------------
# IndieAuth callback route
# ---------------------------------------------------------------------------

def _indieauth_callback_patches(token_response=None, token_status=200, token_error=None):
    """Return ExitStack patching httpx for the IndieAuth token exchange."""
    stack = ExitStack()

    if token_error:
        mock_post = AsyncMock(side_effect=token_error)
    else:
        if token_response is None:
            token_response = {"me": "https://user.example.com/"}
        mock_resp = MagicMock()
        mock_resp.status_code = token_status
        mock_resp.json.return_value = token_response
        mock_resp.text = str(token_response)
        mock_post = AsyncMock(return_value=mock_resp)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = mock_post

    stack.enter_context(patch("app.auth.routes.httpx.AsyncClient", return_value=mock_client))
    return stack


class TestIndieAuthCallback:
    def _setup_session(self, client: TestClient):
        """Do a login flow first to populate session state, then return the state."""
        with _mock_discovery():
            resp = client.get(
                "/v1/auth/indieauth/login?url=https://user.example.com",
                follow_redirects=False,
            )
        # Extract state from redirect URL
        location = resp.headers["location"]
        import re
        state_match = re.search(r"state=([^&]+)", location)
        return state_match.group(1) if state_match else ""

    def test_callback_exchanges_code_and_upserts_user(self, client: TestClient, db_session: Session):
        """Full callback flow: exchange code, get me URL, upsert user."""
        state = self._setup_session(client)

        with _indieauth_callback_patches():
            resp = client.get(f"/v1/auth/indieauth/callback?code=auth_code&state={state}")

        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data

        link = db_session.query(UserOAuthLink).filter(
            UserOAuthLink.provider == "indieauth",
            UserOAuthLink.provider_id == "https://user.example.com/",
        ).first()
        assert link is not None

    def test_callback_no_code_returns_401(self, client: TestClient):
        """Missing code param → 401."""
        resp = client.get("/v1/auth/indieauth/callback?state=abc")
        assert resp.status_code == 401

    def test_callback_state_mismatch_returns_401(self, client: TestClient):
        """Wrong state → 401."""
        self._setup_session(client)
        with _indieauth_callback_patches():
            resp = client.get("/v1/auth/indieauth/callback?code=abc&state=wrong")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "auth_failed"

    def test_callback_token_timeout_returns_502(self, client: TestClient):
        """httpx timeout during token exchange → 502."""
        state = self._setup_session(client)
        with _indieauth_callback_patches(token_error=httpx.TimeoutException("timeout")):
            resp = client.get(f"/v1/auth/indieauth/callback?code=abc&state={state}")
        assert resp.status_code == 502

    def test_callback_token_error_returns_502(self, client: TestClient):
        """Generic exception during token exchange → 502."""
        state = self._setup_session(client)
        with _indieauth_callback_patches(token_error=Exception("connection refused")):
            resp = client.get(f"/v1/auth/indieauth/callback?code=abc&state={state}")
        assert resp.status_code == 502

    def test_callback_token_non_200_returns_401(self, client: TestClient):
        """Token endpoint returns error → 401."""
        state = self._setup_session(client)
        with _indieauth_callback_patches(token_status=400, token_response={"error": "invalid_code"}):
            resp = client.get(f"/v1/auth/indieauth/callback?code=abc&state={state}")
        assert resp.status_code == 401

    def test_callback_no_me_field_returns_401(self, client: TestClient):
        """Token response missing 'me' → 401."""
        state = self._setup_session(client)
        with _indieauth_callback_patches(token_response={"access_token": "at"}):
            resp = client.get(f"/v1/auth/indieauth/callback?code=abc&state={state}")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "provider_error"
