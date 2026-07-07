"""D-04: the verified-email merge OFFER must 302-redirect the browser back to
the web app instead of dead-ending on raw 409 JSON on the API host.

Covers WEBUI-04 / D-04:
- with a `web_redirect_uri` in session, `finalize_auth`'s merge-offer branch
  returns a 302 whose `Location` carries `error=email_conflict` +
  `pending_link_id=<id>`, mirroring the existing success-path redirect.
- that `Location` NEVER carries `token` or `existing_user_id` (ME-02
  enumeration guard — ``resolve_auth``'s ``PendingAccountLink`` offer must
  never leak the matched account's identity to the browser).
- with NO `web_redirect_uri` in session, the merge offer still returns the
  existing enumeration-safe 409 JSON (non-browser/API callers keep working).

Drives the scenario through the real HTTP surface (`/v1/auth/google/login` +
`/v1/auth/google/callback`) rather than calling `resolve_auth` directly, so
the assertions exercise `finalize_auth`'s actual redirect-building code path —
not just the pure resolver already covered by ``test_auth_merge.py``.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import PendingAccountLink, User, UserOAuthLink


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _seed_owner(db_session: Session) -> User:
    """Seed an existing GitHub-linked user with a verified email — the account
    a NEW provider's verified-email match will collide against (the exact
    resolve_auth merge-offer trigger, see api/app/auth/merge.py)."""
    owner = User(
        username="owner",
        email="shared@example.com",
        display_name="Owner",
        email_verified=True,
        role="contributor",
    )
    db_session.add(owner)
    db_session.flush()
    db_session.add(UserOAuthLink(user_id=owner.id, provider="github", provider_id="gh_owner"))
    db_session.commit()
    db_session.refresh(owner)
    return owner


def _register_google_if_needed():
    """Mirror test_auth_google.py's registration guard so `oauth.google` exists
    to be patched (GOOGLE_CLIENT_ID is unset in the test environment)."""
    from app.auth.routes import oauth

    if "google" not in oauth._registry:
        oauth.register(name="google", client_id="test")


def _mock_google_callback_oauth(email: str, sub: str) -> MagicMock:
    """A mock google oauth client whose callback resolves a PROVIDER-VERIFIED
    email — the merge-offer trigger."""
    mock = MagicMock()
    mock.authorize_access_token = AsyncMock(
        return_value={
            "access_token": "google_access_token",
            "userinfo": {
                "sub": sub,
                "email": email,
                "email_verified": True,
                "name": "Same Person",
            },
        }
    )
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestMergeOfferRedirect:
    def test_merge_offer_redirects_and_is_enumeration_safe(
        self, client: TestClient, db_session: Session
    ):
        owner = _seed_owner(db_session)

        # Step 1: store web_redirect_uri in session via login (mocked authorize_redirect,
        # mirrors TestWebRedirectUri in test_auth_github.py).
        from starlette.responses import JSONResponse

        mock_login_oauth = MagicMock()
        mock_login_oauth.google.authorize_redirect = AsyncMock(
            return_value=JSONResponse(content={"ok": True})
        )
        with patch("app.auth.routes.oauth", mock_login_oauth), patch(
            "app.auth.routes._GOOGLE_CLIENT_ID", "google_test_client_id"
        ):
            login_resp = client.get(
                "/v1/auth/google/login?web_redirect_uri=http://localhost:3000/auth/callback"
            )
        assert login_resp.status_code == 200

        # Step 2: callback with a VERIFIED email matching the seeded owner.
        _register_google_if_needed()
        mock_cb_oauth = _mock_google_callback_oauth(email="shared@example.com", sub="google.new")
        with patch("app.auth.routes._GOOGLE_CLIENT_ID", "google_test_client_id"), patch(
            "app.auth.routes.oauth.google", mock_cb_oauth
        ):
            resp = client.get("/v1/auth/google/callback?code=abc", follow_redirects=False)

        # (1) 302 back to the web app with error=email_conflict + a real pending_link_id.
        assert resp.status_code == 302
        location = resp.headers["location"]
        assert location.startswith("http://localhost:3000/auth/callback?")

        parsed = urlparse(location)
        qs = parse_qs(parsed.query)
        assert qs.get("error") == ["email_conflict"]
        pending_ids = qs.get("pending_link_id")
        assert pending_ids and pending_ids[0]

        # (2) ME-02: the redirect NEVER carries a token or the internal existing_user_id.
        assert "token" not in qs
        assert "existing_user_id" not in qs

        # The pending link row genuinely exists and targets the seeded owner.
        pending = (
            db_session.query(PendingAccountLink)
            .filter(PendingAccountLink.id == uuid.UUID(pending_ids[0]))
            .first()
        )
        assert pending is not None
        assert str(pending.existing_user_id) == str(owner.id)
        assert pending.new_provider == "google"
        assert pending.new_provider_id == "google.new"

    def test_merge_offer_without_web_redirect_uri_returns_409_json(
        self, client: TestClient, db_session: Session
    ):
        """(3) No web_redirect_uri in session (non-browser/API caller) → the
        existing enumeration-safe 409 JSON fallback, unchanged."""
        _seed_owner(db_session)

        _register_google_if_needed()
        mock_cb_oauth = _mock_google_callback_oauth(email="shared@example.com", sub="google.new2")
        with patch("app.auth.routes._GOOGLE_CLIENT_ID", "google_test_client_id"), patch(
            "app.auth.routes.oauth.google", mock_cb_oauth
        ):
            resp = client.get("/v1/auth/google/callback?code=abc")

        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "email_conflict"
        assert data["pending_link_id"]
        assert "existing_user_id" not in data
        assert "token" not in data
