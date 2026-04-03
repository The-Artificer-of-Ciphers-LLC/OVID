"""Rate limiting tests — verifies slowapi integration with auth-aware thresholds.

Tests:
- Unauthenticated requests hit 429 after 100 requests/minute
- Authenticated requests use a higher 500/minute threshold
- 429 response body has the required JSON structure
- Auth and unauth counters are independent
"""


def test_unauth_rate_limit_429(client) -> None:
    """Sending 101 unauthenticated GET /health triggers a 429 on the 101st."""
    for i in range(100):
        resp = client.get("/health")
        assert resp.status_code == 200, f"Request {i+1} failed early with {resp.status_code}"

    # The 101st request should be rejected
    resp = client.get("/health")
    assert resp.status_code == 429, (
        f"Expected 429 on request 101, got {resp.status_code}"
    )


def test_auth_rate_limit_higher_threshold(client, auth_header) -> None:
    """Authenticated users get 500/min, not 100/min.

    Send 101 authenticated GET /v1/sync/head requests — all should
    succeed because the auth limit is 500/min.
    """
    for i in range(101):
        resp = client.get("/v1/sync/head", headers=auth_header)
        assert resp.status_code == 200, (
            f"Authenticated request {i+1} unexpectedly got {resp.status_code}"
        )


def test_rate_limit_response_format(client) -> None:
    """The 429 response body must contain 'error', 'message', and 'retry_after' fields."""
    # Exhaust the limit
    for _ in range(100):
        client.get("/health")

    resp = client.get("/health")
    assert resp.status_code == 429

    body = resp.json()
    assert body["error"] == "rate_limited", f"Unexpected error field: {body}"
    assert "retry_after" in body, f"Missing retry_after field: {body}"
    assert isinstance(body["retry_after"], int), (
        f"retry_after should be int, got {type(body['retry_after'])}"
    )
    assert "message" in body, f"Missing message field: {body}"


def test_auth_and_unauth_counters_independent(client, auth_header) -> None:
    """Authenticated and unauthenticated requests have independent rate counters.

    Exhaust the unauth limit (100), then verify an auth request still succeeds.
    """
    # Exhaust unauth counter
    for _ in range(100):
        client.get("/health")

    # Unauth should now be blocked
    resp = client.get("/health")
    assert resp.status_code == 429

    # Auth request uses a different key — should succeed
    resp = client.get("/v1/sync/head", headers=auth_header)
    assert resp.status_code == 200


def test_rate_limit_429_has_retry_after_header(client) -> None:
    """The 429 response should include a Retry-After header."""
    for _ in range(100):
        client.get("/health")

    resp = client.get("/health")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers, (
        f"Missing Retry-After header. Headers: {dict(resp.headers)}"
    )
