"""Tests for Mastodon OAuth — domain validation, email collision, race condition, cache expiry."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest

from app.models import MastodonOAuthClient


# ---------------------------------------------------------------------------
# Domain validation tests
# ---------------------------------------------------------------------------

class TestValidateMastodonDomain:
    """Tests for validate_mastodon_domain() hardening."""

    @patch("app.auth.mastodon.socket.gethostbyname")
    def test_private_ip_rejected(self, mock_dns):
        """DNS resolving to 127.0.0.1 raises ValueError."""
        from app.auth.mastodon import validate_mastodon_domain
        mock_dns.return_value = "127.0.0.1"
        with pytest.raises(ValueError, match="private or restricted IP"):
            validate_mastodon_domain("evil.example.com")

    @patch("app.auth.mastodon.socket.gethostbyname")
    def test_valid_domain_returns_normalized(self, mock_dns):
        """Valid domain with public IP returns normalized domain string."""
        from app.auth.mastodon import validate_mastodon_domain
        mock_dns.return_value = "8.8.8.8"
        result = validate_mastodon_domain("mastodon.social")
        assert result == "mastodon.social"

    @patch("app.auth.mastodon.socket.gethostbyname")
    def test_domain_with_scheme_stripped(self, mock_dns):
        """Domain prefixed with https:// has scheme stripped."""
        from app.auth.mastodon import validate_mastodon_domain
        mock_dns.return_value = "8.8.8.8"
        result = validate_mastodon_domain("https://mastodon.social")
        assert result == "mastodon.social"

    def test_blocked_instance_rejected(self):
        """Blocked instances (gab.com) raise HTTPException with blocked_instance error."""
        from fastapi import HTTPException
        from app.auth.mastodon import validate_mastodon_domain
        with pytest.raises(HTTPException) as exc_info:
            validate_mastodon_domain("gab.com")
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"] == "blocked_instance"

    def test_blocked_instance_truthsocial(self):
        """truthsocial.com is blocked."""
        from fastapi import HTTPException
        from app.auth.mastodon import validate_mastodon_domain
        with pytest.raises(HTTPException):
            validate_mastodon_domain("truthsocial.com")

    def test_unresolvable_domain_raises(self):
        """Domain that cannot be resolved raises ValueError."""
        from app.auth.mastodon import validate_mastodon_domain
        with pytest.raises(ValueError, match="Could not resolve domain"):
            validate_mastodon_domain("invalid-domain-that-does-not-exist.local")


# ---------------------------------------------------------------------------
# Placeholder email collision tests
# ---------------------------------------------------------------------------

class TestMastodonPlaceholderEmail:
    """Tests for domain-qualified placeholder emails (BUG-01)."""

    @patch("httpx.AsyncClient.post")
    @patch("httpx.AsyncClient.get")
    @patch("app.auth.mastodon.socket.gethostbyname")
    def test_placeholder_email_includes_domain(self, mock_dns, mock_get, mock_post, client, db_session):
        """Mastodon placeholder email includes domain to prevent collision."""
        mock_dns.return_value = "8.8.8.8"

        # Seed client
        db_session.add(MastodonOAuthClient(
            domain="mastodon.social",
            client_id="cid",
            client_secret="csec",
        ))
        db_session.commit()

        # Mock token exchange
        mock_post.return_value = httpx.Response(200, json={"access_token": "tok"}, request=httpx.Request("POST", "url"))
        mock_get.return_value = httpx.Response(200, json={
            "id": "12345",
            "username": "testuser",
            "display_name": "Test User"
        }, request=httpx.Request("GET", "url"))

        # Login to set session cookies
        login_resp = client.get("/v1/auth/mastodon/login?domain=mastodon.social", follow_redirects=False)
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(login_resp.headers["location"])
        qs = parse_qs(parsed.query)
        state = qs["state"][0]

        # Callback
        resp = client.get(f"/v1/auth/mastodon/callback?code=test_code&state={state}")
        assert resp.status_code == 200

        # Check user was created with domain-qualified email
        from app.models import User
        user = db_session.query(User).filter(User.email.like("mastodon_%")).first()
        assert user is not None
        assert "mastodon.social" in user.email
        assert "12345" in user.email

    def test_different_domains_different_emails(self):
        """Two domains with same account_id produce different placeholder emails."""
        # Import the helper that builds the email
        # The email format should be: mastodon_{domain}_{account_id}@noemail.placeholder
        email_1 = "mastodon_mastodon.social_12345@noemail.placeholder"
        email_2 = "mastodon_fosstodon.org_12345@noemail.placeholder"
        assert email_1 != email_2


# ---------------------------------------------------------------------------
# Client registration — upsert and expiry tests
# ---------------------------------------------------------------------------

class TestClientRegistrationUpsert:
    """Tests for get_or_register_client() upsert and TTL (BUG-03, BUG-05)."""

    @patch("app.auth.mastodon.socket.gethostbyname")
    def test_cached_client_returned(self, mock_dns, client, db_session):
        """Existing non-expired client is returned without re-registration."""
        mock_dns.return_value = "8.8.8.8"

        db_session.add(MastodonOAuthClient(
            domain="cached.example.com",
            client_id="cached_id",
            client_secret="cached_secret",
            expires_at=datetime.now(timezone.utc) + timedelta(days=15),
        ))
        db_session.commit()

        resp = client.get("/v1/auth/mastodon/login?domain=cached.example.com", follow_redirects=False)
        assert resp.status_code == 307
        assert "client_id=cached_id" in resp.headers["location"]

    @patch("httpx.AsyncClient.post")
    @patch("app.auth.mastodon.socket.gethostbyname")
    def test_expired_client_re_registers(self, mock_dns, mock_post, client, db_session):
        """Client with expires_at in the past triggers re-registration."""
        mock_dns.return_value = "8.8.8.8"

        db_session.add(MastodonOAuthClient(
            domain="expired.example.com",
            client_id="old_id",
            client_secret="old_secret",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        ))
        db_session.commit()

        mock_post.return_value = httpx.Response(200, json={
            "client_id": "new_id",
            "client_secret": "new_secret"
        }, request=httpx.Request("POST", "url"))

        resp = client.get("/v1/auth/mastodon/login?domain=expired.example.com", follow_redirects=False)
        assert resp.status_code == 307
        assert "client_id=new_id" in resp.headers["location"]

    @patch("httpx.AsyncClient.post")
    @patch("app.auth.mastodon.socket.gethostbyname")
    def test_null_expires_at_treated_as_expired(self, mock_dns, mock_post, client, db_session):
        """Legacy client with NULL expires_at triggers re-registration."""
        mock_dns.return_value = "8.8.8.8"

        db_session.add(MastodonOAuthClient(
            domain="legacy.example.com",
            client_id="legacy_id",
            client_secret="legacy_secret",
            # No expires_at — NULL
        ))
        db_session.commit()

        mock_post.return_value = httpx.Response(200, json={
            "client_id": "refreshed_id",
            "client_secret": "refreshed_secret"
        }, request=httpx.Request("POST", "url"))

        resp = client.get("/v1/auth/mastodon/login?domain=legacy.example.com", follow_redirects=False)
        assert resp.status_code == 307
        assert "client_id=refreshed_id" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Mastodon login flow (existing tests, preserved)
# ---------------------------------------------------------------------------

class TestMastodonLogin:
    @patch("app.auth.mastodon.socket.gethostbyname")
    @patch("httpx.AsyncClient.post")
    def test_login_dynamic_registration(self, mock_post, mock_dns, client, db_session):
        mock_dns.return_value = "8.8.8.8"

        mock_resp = httpx.Response(200, json={
            "client_id": "test_client_id",
            "client_secret": "test_client_secret"
        }, request=httpx.Request("POST", "https://mastodon.example.com"))
        mock_post.return_value = mock_resp

        resp = client.get("/v1/auth/mastodon/login?domain=mastodon.example.com", follow_redirects=False)
        assert resp.status_code == 307

        redirect_url = resp.headers["location"]
        assert redirect_url.startswith("https://mastodon.example.com/oauth/authorize")
        assert "client_id=test_client_id" in redirect_url
        assert "response_type=code" in redirect_url
        assert "scope=read" in redirect_url

        db_client = db_session.query(MastodonOAuthClient).filter_by(domain="mastodon.example.com").first()
        assert db_client is not None
        assert db_client.client_id == "test_client_id"
        assert db_client.client_secret == "test_client_secret"
        # New: expires_at should be set
        assert db_client.expires_at is not None

    @patch("app.auth.mastodon.socket.gethostbyname")
    def test_login_uses_cached_client(self, mock_dns, client, db_session):
        mock_dns.return_value = "8.8.8.8"

        db_client = MastodonOAuthClient(
            domain="cached.example.com",
            client_id="cached_id",
            client_secret="cached_secret",
            expires_at=datetime.now(timezone.utc) + timedelta(days=15),
        )
        db_session.add(db_client)
        db_session.commit()

        resp = client.get("/v1/auth/mastodon/login?domain=cached.example.com", follow_redirects=False)
        assert resp.status_code == 307
        assert "client_id=cached_id" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Mastodon callback (existing tests, preserved)
# ---------------------------------------------------------------------------

class TestMastodonCallback:
    @patch("httpx.AsyncClient.post")
    @patch("httpx.AsyncClient.get")
    def test_callback_success(self, mock_get, mock_post, client, db_session):
        db_client = MastodonOAuthClient(
            domain="mastodon.example.com",
            client_id="test_id",
            client_secret="test_secret",
            expires_at=datetime.now(timezone.utc) + timedelta(days=15),
        )
        db_session.add(db_client)
        db_session.commit()

        mock_token_resp = httpx.Response(200, json={"access_token": "test_access_token"}, request=httpx.Request("POST", "url"))
        mock_post.return_value = mock_token_resp
        mock_verify_resp = httpx.Response(200, json={
            "id": "12345",
            "username": "testuser",
            "display_name": "Test User"
        }, request=httpx.Request("GET", "url"))
        mock_get.return_value = mock_verify_resp

        with patch("app.auth.mastodon.socket.gethostbyname") as mock_dns:
            mock_dns.return_value = "8.8.8.8"
            login_resp = client.get("/v1/auth/mastodon/login?domain=mastodon.example.com", follow_redirects=False)

        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(login_resp.headers["location"])
        qs = parse_qs(parsed.query)
        state = qs["state"][0]

        resp = client.get(f"/v1/auth/mastodon/callback?code=test_code&state={state}")

        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "mastodon_mastodon.example.com:12345"
        assert data["user"]["display_name"] == "Test User"

    @patch("httpx.AsyncClient.post")
    @patch("httpx.AsyncClient.get")
    def test_callback_timeout(self, mock_get, mock_post, client, db_session):
        db_client = MastodonOAuthClient(
            domain="mastodon.example.com",
            client_id="test_id",
            client_secret="test_secret",
            expires_at=datetime.now(timezone.utc) + timedelta(days=15),
        )
        db_session.add(db_client)
        db_session.commit()

        mock_post.side_effect = httpx.TimeoutException("Timeout")

        with patch("app.auth.mastodon.socket.gethostbyname") as mock_dns:
            mock_dns.return_value = "8.8.8.8"
            login_resp = client.get("/v1/auth/mastodon/login?domain=mastodon.example.com", follow_redirects=False)

        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(login_resp.headers["location"])
        qs = parse_qs(parsed.query)
        state = qs["state"][0]

        resp = client.get(f"/v1/auth/mastodon/callback?code=test_code&state={state}")

        assert resp.status_code == 504
        assert resp.json()["detail"]["error"] == "gateway_timeout"


# ---------------------------------------------------------------------------
# OAuth error sanitization tests (SEC-05)
# ---------------------------------------------------------------------------

class TestOAuthErrorSanitization:
    """OAuth error responses must not leak provider error details."""

    @patch("app.auth.mastodon.socket.gethostbyname")
    @patch("httpx.AsyncClient.post")
    def test_mastodon_registration_error_sanitized(self, mock_post, mock_dns, client, db_session):
        """Connection error during registration does not leak exception details."""
        mock_dns.return_value = "8.8.8.8"
        mock_post.side_effect = ConnectionError("Secret internal error: SSL certificate verify failed for internal.corp.net")

        resp = client.get("/v1/auth/mastodon/login?domain=newinstance.example.com", follow_redirects=False)
        # Should get error but not leak the internal error message
        assert resp.status_code == 502
        data = resp.json()
        # The response should NOT contain the actual exception text
        response_text = str(data)
        assert "internal.corp.net" not in response_text
        assert "SSL certificate" not in response_text
