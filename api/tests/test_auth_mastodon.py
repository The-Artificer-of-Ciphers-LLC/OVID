import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
import httpx

from app.models import MastodonOAuthClient
from app.auth.mastodon import validate_mastodon_domain

def test_validate_mastodon_domain():
    # Valid domains
    assert validate_mastodon_domain("mastodon.social") == "mastodon.social"
    assert validate_mastodon_domain("https://mastodon.social") == "mastodon.social"
    
    # Invalid domains
    with pytest.raises(ValueError, match="Domain resolves to private or restricted IP"):
        validate_mastodon_domain("localhost")
    with pytest.raises(ValueError, match="Domain resolves to private or restricted IP"):
        validate_mastodon_domain("127.0.0.1")
    with pytest.raises(ValueError, match="Domain resolves to private or restricted IP"):
        validate_mastodon_domain("10.0.0.1")
    with pytest.raises(ValueError, match="Could not resolve domain"):
        validate_mastodon_domain("invalid-domain-that-does-not-exist.local")


class TestMastodonLogin:
    @patch("app.auth.mastodon.socket.gethostbyname")
    @patch("httpx.AsyncClient.post")
    def test_login_dynamic_registration(self, mock_post, mock_dns, client, db_session):
        # Setup mocks
        mock_dns.return_value = "8.8.8.8"  # Fake valid public IP
        
        # Mock registration response
        mock_resp = httpx.Response(200, json={
            "client_id": "test_client_id",
            "client_secret": "test_client_secret"
        }, request=httpx.Request("POST", "https://mastodon.example.com"))
        mock_post.return_value = mock_resp
        
        # Request login
        resp = client.get("/v1/auth/mastodon/login?domain=mastodon.example.com", follow_redirects=False)
        assert resp.status_code == 307
        
        # Check redirect URL
        redirect_url = resp.headers["location"]
        assert redirect_url.startswith("https://mastodon.example.com/oauth/authorize")
        assert "client_id=test_client_id" in redirect_url
        assert "response_type=code" in redirect_url
        assert "scope=read" in redirect_url
        
        # Check DB was updated
        db_client = db_session.query(MastodonOAuthClient).filter_by(domain="mastodon.example.com").first()
        assert db_client is not None
        assert db_client.client_id == "test_client_id"
        assert db_client.client_secret == "test_client_secret"

    @patch("app.auth.mastodon.socket.gethostbyname")
    def test_login_uses_cached_client(self, mock_dns, client, db_session):
        mock_dns.return_value = "8.8.8.8"
        
        # Seed DB
        db_client = MastodonOAuthClient(
            domain="cached.example.com",
            client_id="cached_id",
            client_secret="cached_secret"
        )
        db_session.add(db_client)
        db_session.commit()
        
        # We don't patch httpx, if it tries to register it will fail/hang or raise error.
        resp = client.get("/v1/auth/mastodon/login?domain=cached.example.com", follow_redirects=False)
        assert resp.status_code == 307
        assert "client_id=cached_id" in resp.headers["location"]


class TestMastodonCallback:
    @patch("httpx.AsyncClient.post")
    @patch("httpx.AsyncClient.get")
    def test_callback_success(self, mock_get, mock_post, client, db_session):
        # Setup session state and DB client
        db_client = MastodonOAuthClient(
            domain="mastodon.example.com",
            client_id="test_id",
            client_secret="test_secret"
        )
        db_session.add(db_client)
        db_session.commit()
        
        # Mock token exchange
        mock_token_resp = httpx.Response(200, json={"access_token": "test_access_token"}, request=httpx.Request("POST", "url"))
        mock_post.return_value = mock_token_resp
        
        # Mock credentials verify
        mock_verify_resp = httpx.Response(200, json={
            "id": "12345",
            "username": "testuser",
            "display_name": "Test User"
        }, request=httpx.Request("GET", "url"))
        mock_get.return_value = mock_verify_resp
        
        # We need to set cookies to simulate session
        # The easiest way is to let the login endpoint set them, but we mocked login above.
        # Let's mock the session directly or do a two-step.
        
        # Step 1: get login redirect to get session cookie
        with patch("app.auth.mastodon.socket.gethostbyname") as mock_dns:
            mock_dns.return_value = "8.8.8.8"
            login_resp = client.get("/v1/auth/mastodon/login?domain=mastodon.example.com", follow_redirects=False)
            
        # Extract state from redirect url
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(login_resp.headers["location"])
        qs = parse_qs(parsed.query)
        state = qs["state"][0]
        
        # Step 2: callback
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
            client_secret="test_secret"
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
