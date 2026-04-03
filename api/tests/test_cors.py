"""Tests for CORS middleware configuration."""


class TestCORS:
    def test_options_preflight(self, client):
        """OPTIONS preflight to a disc endpoint returns CORS allow-origin header."""
        resp = client.options(
            "/v1/disc/anything",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"

    def test_get_includes_cors_header(self, client):
        """GET to a disc endpoint with Origin header gets CORS headers back."""
        resp = client.get(
            "/v1/disc/nonexistent",
            headers={"Origin": "http://localhost:3000"},
        )
        # Endpoint returns 404 JSON, but CORS header must still be present
        assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"

    def test_post_includes_cors_header(self, client, auth_header):
        """POST to /v1/disc with Origin header gets CORS headers back."""
        headers = {**auth_header, "Origin": "http://localhost:3000"}
        resp = client.post(
            "/v1/disc",
            json={"fingerprint": "x"},  # will fail validation, that's fine
            headers=headers,
        )
        # Even a 422 validation error should carry CORS headers
        assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"
