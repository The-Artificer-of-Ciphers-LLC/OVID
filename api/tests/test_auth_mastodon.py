import socket

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
import httpx

from app.models import MastodonOAuthClient
from app.auth.mastodon import validate_mastodon_domain


def _gai(*ips):
    """Build a ``socket.getaddrinfo``-shaped return value from IP strings.

    Each entry is a 5-tuple ``(family, socktype, proto, canonname, sockaddr)``.
    ``validate_mastodon_domain`` only reads ``sockaddr[0]`` (the IP string), so
    the port/flow fields are zero-filled. IPv6 literals get a 4-tuple sockaddr,
    IPv4 a 2-tuple, matching what the stdlib returns. This keeps every test
    network-free and deterministic (no real DNS).
    """
    result = []
    for ip in ips:
        if ":" in ip:
            result.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 0, 0, 0)))
        else:
            result.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)))
    return result


class TestValidateMastodonDomainSSRF:
    """AUTH-05: dual-stack SSRF validation of the Mastodon instance URL.

    Every resolution is mocked at ``app.auth.mastodon.socket.getaddrinfo`` — no
    test in this file depends on real network DNS.
    """

    @patch("app.auth.mastodon.socket.getaddrinfo")
    def test_ssrf_public_domain_passes(self, mock_gai):
        # Public IPv4 resolves fine -> normalized bare domain returned. Also
        # confirms scheme-stripping ("https://host" -> "host") still works.
        mock_gai.return_value = _gai("93.184.216.34")
        assert validate_mastodon_domain("mastodon.social") == "mastodon.social"
        assert validate_mastodon_domain("https://mastodon.social") == "mastodon.social"

    @patch("app.auth.mastodon.socket.getaddrinfo")
    def test_ssrf_public_ipv6_only_passes(self, mock_gai):
        # A domain resolving only to a public IPv6 address is accepted.
        mock_gai.return_value = _gai("2606:2800:220:1:248:1893:25c8:1946")
        assert validate_mastodon_domain("v6.example.com") == "v6.example.com"

    @patch("app.auth.mastodon.socket.getaddrinfo")
    def test_ssrf_ipv6_only_private_rejected(self, mock_gai):
        # AAAA-only host pointing at a private/ULA IPv6 must be rejected. This is
        # exactly the bypass the old IPv4-only gethostbyname check missed.
        mock_gai.return_value = _gai("fc00::1")
        with pytest.raises(ValueError, match="Domain resolves to private or restricted IP"):
            validate_mastodon_domain("evil-v6.example.com")

    @patch("app.auth.mastodon.socket.getaddrinfo")
    def test_ssrf_ipv6_only_loopback_rejected(self, mock_gai):
        mock_gai.return_value = _gai("::1")
        with pytest.raises(ValueError, match="Domain resolves to private or restricted IP"):
            validate_mastodon_domain("localhost6.example.com")

    @patch("app.auth.mastodon.socket.getaddrinfo")
    def test_ssrf_dual_stack_mixed_rejected(self, mock_gai):
        # One public IPv4 AND one private IPv6 -> any bad address in any family
        # fails the whole domain.
        mock_gai.return_value = _gai("93.184.216.34", "fc00::1")
        with pytest.raises(ValueError, match="Domain resolves to private or restricted IP"):
            validate_mastodon_domain("dualstack.example.com")

    @patch("app.auth.mastodon.socket.getaddrinfo")
    def test_ssrf_ipv4_loopback_rejected(self, mock_gai):
        mock_gai.return_value = _gai("127.0.0.1")
        with pytest.raises(ValueError, match="Domain resolves to private or restricted IP"):
            validate_mastodon_domain("loopback.example.com")

    @patch("app.auth.mastodon.socket.getaddrinfo")
    def test_ssrf_ipv4_private_rejected(self, mock_gai):
        mock_gai.return_value = _gai("10.0.0.1")
        with pytest.raises(ValueError, match="Domain resolves to private or restricted IP"):
            validate_mastodon_domain("internal.example.com")

    @patch("app.auth.mastodon.socket.getaddrinfo")
    def test_ssrf_reserved_range_rejected(self, mock_gai):
        # 240.0.0.0/4 is a reserved range; the added is_reserved guard rejects it.
        mock_gai.return_value = _gai("240.0.0.1")
        with pytest.raises(ValueError, match="Domain resolves to private or restricted IP"):
            validate_mastodon_domain("reserved.example.com")

    @patch("app.auth.mastodon.socket.getaddrinfo")
    def test_ssrf_unresolvable_domain_rejected(self, mock_gai):
        mock_gai.side_effect = socket.gaierror("name resolution failed")
        with pytest.raises(ValueError, match="Could not resolve domain"):
            validate_mastodon_domain("does-not-exist.invalid")

    def test_ssrf_empty_and_space_rejected(self):
        # Empty/space rejection happens before any DNS resolution, so no mock
        # is needed here.
        with pytest.raises(ValueError, match="Invalid domain format"):
            validate_mastodon_domain("")
        with pytest.raises(ValueError, match="Invalid domain format"):
            validate_mastodon_domain("has space.example.com")


class TestMastodonLogin:
    @patch("app.auth.mastodon.socket.getaddrinfo")
    @patch("httpx.AsyncClient.post")
    def test_login_dynamic_registration(self, mock_post, mock_dns, client, db_session):
        # Setup mocks
        mock_dns.return_value = _gai("8.8.8.8")  # Fake valid public IP

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

    @patch("app.auth.mastodon.socket.getaddrinfo")
    def test_login_uses_cached_client(self, mock_dns, client, db_session):
        mock_dns.return_value = _gai("8.8.8.8")

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


class TestMastodonRegistrationHardening:
    """AUTH-05: no-redirect-following and no-raw-response-reflection on the
    dynamic-registration POST to ``/api/v1/apps`` (T-06-05b, T-06-05c).
    """

    @patch("app.auth.mastodon.socket.getaddrinfo")
    @patch("httpx.AsyncClient.post")
    def test_ssrf_registration_does_not_follow_redirect_to_private(self, mock_post, mock_dns, client, db_session):
        # Validation passes (public IP), then the instance answers the
        # registration POST with a 302 whose Location points at a private/
        # link-local IP (cloud metadata endpoint).
        mock_dns.return_value = _gai("8.8.8.8")
        private_location = "http://169.254.169.254/latest/meta-data/"
        mock_resp = httpx.Response(
            302,
            headers={"location": private_location},
            request=httpx.Request("POST", "https://mastodon.example.com/api/v1/apps"),
        )
        mock_post.return_value = mock_resp

        resp = client.get(
            "/v1/auth/mastodon/login?domain=redirect.example.com", follow_redirects=False
        )

        # The 302 is treated as a non-200 failure — OVID does NOT chase the
        # redirect to the private Location (httpx AsyncClient default
        # follow_redirects=False is preserved).
        assert resp.status_code == 502
        detail = resp.json()["detail"]
        assert detail["error"] == "bad_gateway"
        assert "Registration failed with status 302" in detail["reason"]
        # The private Location is never reflected back to the caller.
        assert private_location not in resp.text
        assert "169.254.169.254" not in resp.text
        # Exactly one outbound request was made (no follow-up to the Location).
        assert mock_post.call_count == 1

    @patch("app.auth.mastodon.socket.getaddrinfo")
    @patch("httpx.AsyncClient.post")
    def test_ssrf_registration_error_does_not_reflect_upstream_body(self, mock_post, mock_dns, client, db_session):
        # A non-200 registration response with a body containing internal detail
        # must NOT be reflected into the error surfaced to the caller.
        mock_dns.return_value = _gai("8.8.8.8")
        leaky_body = "internal db error at 10.0.0.5: connection refused"
        mock_resp = httpx.Response(
            500,
            text=leaky_body,
            request=httpx.Request("POST", "https://mastodon.example.com/api/v1/apps"),
        )
        mock_post.return_value = mock_resp

        resp = client.get(
            "/v1/auth/mastodon/login?domain=broken.example.com", follow_redirects=False
        )

        assert resp.status_code == 502
        detail = resp.json()["detail"]
        assert detail["error"] == "bad_gateway"
        # Generic status-only message — raw upstream body (and the internal IP it
        # contained) is never reflected to the caller.
        assert detail["reason"] == "Registration failed with status 500"
        assert leaky_body not in resp.text
        assert "10.0.0.5" not in resp.text


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
        with patch("app.auth.mastodon.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = _gai("8.8.8.8")
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

        with patch("app.auth.mastodon.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = _gai("8.8.8.8")
            login_resp = client.get("/v1/auth/mastodon/login?domain=mastodon.example.com", follow_redirects=False)

        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(login_resp.headers["location"])
        qs = parse_qs(parsed.query)
        state = qs["state"][0]

        resp = client.get(f"/v1/auth/mastodon/callback?code=test_code&state={state}")

        assert resp.status_code == 504
        assert resp.json()["detail"]["error"] == "gateway_timeout"
