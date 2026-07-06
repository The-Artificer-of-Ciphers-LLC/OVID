"""Regression test for CR-01: self-confirmation bypass via register→identify→resubmit.

A disc pre-registered via ``POST /v1/disc/register`` carries only a
``submitted_by`` for the fingerprint-only registrant — it has no release
metadata yet. The FIRST submission of release metadata (the identify path,
WR-03) must make ITS submitter the disc's ``submitted_by``, so that same
submitter cannot resubmit their own metadata and trip the auto-verify path
(the self-confirm guards in ``verification.verify`` and the same-submitter
409 check both key off ``disc.submitted_by``). Before the fix,
``submitted_by`` stays pinned to the ORIGINAL registrant forever, so the
identifier is never recognized as "the submitter" and can freely re-submit
their own claim to auto-verify it alone — one human, two accounts, no
independent confirmation.
"""

import uuid

from app.auth.jwt import create_access_token
from app.models import User


def _seed_third_user(db) -> User:
    """A third, wholly distinct contributor (neither the registrant nor the
    identifier) used to prove genuine two-contributor confirmation still
    works after the fix."""
    user = User(
        id=uuid.uuid4(),
        username="testuser3",
        email="test3@example.com",
        display_name="Test User 3",
        role="contributor",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _identify_payload(fingerprint: str) -> dict:
    return {
        "fingerprint": fingerprint,
        "format": "BD",
        "region_code": "A",
        "release": {
            "title": "Self Confirm Film",
            "year": 2023,
            "content_type": "movie",
            "tmdb_id": 424242,
            "original_language": "en",
        },
        "titles": [
            {
                "title_index": 0,
                "title_type": "main_feature",
                "duration_secs": 6600,
                "chapter_count": 20,
                "is_main_feature": True,
                "display_name": "Self Confirm Film",
                "audio_tracks": [
                    {
                        "track_index": 0,
                        "language_code": "en",
                        "codec": "dts-hd",
                        "channels": 6,
                        "is_default": True,
                    }
                ],
                "subtitle_tracks": [
                    {
                        "track_index": 0,
                        "language_code": "en",
                        "codec": "pgs",
                        "is_default": False,
                    }
                ],
            }
        ],
    }


class TestIdentifySelfConfirmBypass:
    def test_identifier_cannot_self_confirm_after_register(
        self, client, db_session, auth_header, second_auth_header
    ):
        """A registers the bare fingerprint; B supplies the first release
        metadata (identify). B resubmitting the SAME metadata must NOT
        auto-verify — B becomes the disc's submitted_by on identify and
        hits the same-submitter 409 guard, exactly like any other first
        submitter (VERIFY-01/D-05)."""
        register_payload = {
            "fingerprint": "bd-SELFCONF-001",
            "format": "BD",
            "disc_label": "SELFCONF",
        }
        reg_resp = client.post(
            "/v1/disc/register", json=register_payload, headers=auth_header
        )
        assert reg_resp.status_code == 201

        payload = _identify_payload("bd-SELFCONF-001")
        identify_resp = client.post("/v1/disc", json=payload, headers=second_auth_header)
        assert identify_resp.status_code == 200
        assert identify_resp.json()["status"] == "unverified"

        # B (the identifier) resubmits the exact same structural payload.
        resubmit_resp = client.post("/v1/disc", json=payload, headers=second_auth_header)
        assert resubmit_resp.status_code == 409
        data = resubmit_resp.json()
        assert data["error"] == "conflict"

        get_resp = client.get("/v1/disc/bd-SELFCONF-001")
        assert get_resp.json()["status"] == "unverified"

    def test_distinct_third_user_can_still_confirm(
        self, client, db_session, auth_header, second_auth_header
    ):
        """A registers, B identifies, and a THIRD distinct contributor C
        reproducing the identified structure legitimately verifies the
        disc — genuine two-contributor confirmation must keep working."""
        register_payload = {
            "fingerprint": "bd-SELFCONF-002",
            "format": "BD",
            "disc_label": "SELFCONF2",
        }
        client.post("/v1/disc/register", json=register_payload, headers=auth_header)

        payload = _identify_payload("bd-SELFCONF-002")
        identify_resp = client.post("/v1/disc", json=payload, headers=second_auth_header)
        assert identify_resp.status_code == 200
        assert identify_resp.json()["status"] == "unverified"

        third_user = _seed_third_user(db_session)
        third_auth_header = {
            "Authorization": f"Bearer {create_access_token(third_user.id)}"
        }
        confirm_resp = client.post("/v1/disc", json=payload, headers=third_auth_header)
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["status"] == "verified"
