"""The bodyless POST /v1/disc/{fingerprint}/verify route is retired (D-02).

Re-submission via POST /v1/disc is now the ONLY confirmation path (D-01); a
no-proof status-flip endpoint on a bare bearer token was a pure Sybil bypass
with no legitimate caller, so it — and its test file — are deleted. These
tests assert the surface is genuinely gone (404 not-registered / 405
method-not-allowed), for both a seeded fingerprint and an unknown one, with
and without auth (a retired route must never fall through to a 401/200).
"""

from tests.conftest import seed_test_disc


class TestVerifyRouteRetired:
    """POST /v1/disc/{fingerprint}/verify — no longer registered (D-02)."""

    def test_retired_verify_route_seeded_fingerprint(self, client, db_session):
        seed_test_disc(db_session, status="unverified")
        resp = client.post("/v1/disc/dvd-ABC123-main/verify")
        assert resp.status_code in (404, 405)

    def test_retired_verify_route_with_auth(
        self, client, db_session, seeded_disc_with_owner, auth_header
    ):
        resp = client.post("/v1/disc/dvd-ABC123-main/verify", headers=auth_header)
        assert resp.status_code in (404, 405)

    def test_retired_verify_route_unknown_fingerprint(self, client, auth_header):
        resp = client.post("/v1/disc/nonexistent-fp/verify", headers=auth_header)
        assert resp.status_code in (404, 405)
