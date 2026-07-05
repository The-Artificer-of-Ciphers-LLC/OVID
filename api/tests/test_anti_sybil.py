"""Unit + integration tests for the VERIFY-04 anti-Sybil gate (anti_sybil.py).

Covers three concerns, all against the in-memory SQLite test engine so the
cooldown query is proven portable (D-13):

  1. ``ip_subnet_hash`` — salted, /24-truncated HMAC (D-06): same-subnet
     collapse, distinct-subnet difference, and fail-open on None/malformed
     IP or absent salt (D-07).
  2. The Postgres-backed confirmation cooldown floor over ``disc_edits``
     (``edit_type="verify"``): under-limit passes, over-limit hard-blocks,
     stale (out-of-window) edits are not counted.
  3. The weighted, offsetting, fail-open trust score over account-age +
     IP-diversity: only the exact Sybil signature (fresh account AND same
     subnet) fails; young-alone, established+same-subnet, fresh+distinct,
     and all-absent-signal all pass (D-04/D-05/D-07/D-08).
"""

import types
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import anti_sybil
from app.models import Disc, DiscEdit

from tests.conftest import (
    make_user_with_age,
    seed_second_user,
    seed_test_disc,
    seed_test_user,
)


SALT = "unit-test-salt"
SALT_BYTES = SALT.encode()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _request(host: str | None | object) -> types.SimpleNamespace:
    """Build a minimal Request stub exposing ``.client.host``.

    Pass ``host=None`` for a client with no host; pass ``client=None`` case
    via ``_request_no_client`` below.
    """
    return types.SimpleNamespace(client=types.SimpleNamespace(host=host))


def _request_no_client() -> types.SimpleNamespace:
    return types.SimpleNamespace(client=None)


def _seed_verify_edits(db, user_id, disc_id, count, minutes_ago):
    now = datetime.now(timezone.utc)
    for _ in range(count):
        db.add(
            DiscEdit(
                disc_id=disc_id,
                user_id=user_id,
                edit_type="verify",
                created_at=now - timedelta(minutes=minutes_ago),
            )
        )
    db.commit()


def _seed_submitter_ip(db, disc_id, submitter_id, raw_ip):
    """Seed the disc's original create-edit carrying the submitter subnet hash."""
    db.add(
        DiscEdit(
            disc_id=disc_id,
            user_id=submitter_id,
            edit_type="create",
            ip_hash=anti_sybil.ip_subnet_hash(raw_ip, SALT_BYTES),
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# 1. ip_subnet_hash (D-06)
# ---------------------------------------------------------------------------
class TestIpSubnetHash:
    def test_same_slash24_hashes_equal(self):
        a = anti_sybil.ip_subnet_hash("1.2.3.10", SALT_BYTES)
        b = anti_sybil.ip_subnet_hash("1.2.3.200", SALT_BYTES)
        assert a is not None
        assert a == b

    def test_different_slash24_hashes_differ(self):
        a = anti_sybil.ip_subnet_hash("1.2.3.10", SALT_BYTES)
        c = anti_sybil.ip_subnet_hash("1.2.9.10", SALT_BYTES)
        assert a != c

    def test_none_ip_returns_none(self):
        assert anti_sybil.ip_subnet_hash(None, SALT_BYTES) is None

    def test_malformed_ip_returns_none(self):
        assert anti_sybil.ip_subnet_hash("not-an-ip", SALT_BYTES) is None

    def test_absent_salt_returns_none(self):
        assert anti_sybil.ip_subnet_hash("1.2.3.10", None) is None

    def test_ipv6_same_slash48_collapse(self):
        a = anti_sybil.ip_subnet_hash("2001:db8:abcd:1::1", SALT_BYTES)
        b = anti_sybil.ip_subnet_hash("2001:db8:abcd:ffff::99", SALT_BYTES)
        assert a is not None
        assert a == b


# ---------------------------------------------------------------------------
# 2. Confirmation cooldown floor (D-13)
# ---------------------------------------------------------------------------
class TestCooldown:
    def test_recent_count_ignores_stale_edits(self, db_session):
        user = seed_test_user(db_session)
        ids = seed_test_disc(db_session, status="unverified")
        _seed_verify_edits(db_session, user.id, ids["disc_id"], count=3, minutes_ago=30)
        _seed_verify_edits(db_session, user.id, ids["disc_id"], count=4, minutes_ago=120)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        assert anti_sybil._recent_confirmation_count(db_session, user.id, cutoff) == 3

    def test_under_limit_not_hard_blocked(self, db_session):
        user = seed_test_user(db_session)
        ids = seed_test_disc(db_session, status="unverified")
        disc = db_session.get(Disc, ids["disc_id"])
        _seed_verify_edits(
            db_session, user.id, ids["disc_id"],
            count=anti_sybil.CONFIRMATION_MAX_PER_WINDOW - 1, minutes_ago=10,
        )
        gate = anti_sybil.evaluate_confirmation(
            db_session, disc, user, _request_no_client()
        )
        assert gate.hard_blocked is False

    def test_over_limit_hard_blocked(self, db_session):
        user = seed_test_user(db_session)
        ids = seed_test_disc(db_session, status="unverified")
        disc = db_session.get(Disc, ids["disc_id"])
        _seed_verify_edits(
            db_session, user.id, ids["disc_id"],
            count=anti_sybil.CONFIRMATION_MAX_PER_WINDOW + 1, minutes_ago=10,
        )
        gate = anti_sybil.evaluate_confirmation(
            db_session, disc, user, _request_no_client()
        )
        assert gate.hard_blocked is True

    def test_stale_window_edits_not_counted_for_hard_block(self, db_session):
        user = seed_test_user(db_session)
        ids = seed_test_disc(db_session, status="unverified")
        disc = db_session.get(Disc, ids["disc_id"])
        # Many edits, but all older than the hourly window → not counted.
        _seed_verify_edits(
            db_session, user.id, ids["disc_id"],
            count=anti_sybil.CONFIRMATION_MAX_PER_WINDOW + 5, minutes_ago=120,
        )
        gate = anti_sybil.evaluate_confirmation(
            db_session, disc, user, _request_no_client()
        )
        assert gate.hard_blocked is False


# ---------------------------------------------------------------------------
# 3. Weighted, offsetting, fail-open trust score (D-04/D-05/D-07/D-08)
# ---------------------------------------------------------------------------
class TestWeightedScore:
    @pytest.fixture(autouse=True)
    def _salt_env(self, monkeypatch):
        monkeypatch.setenv("OVID_IP_HASH_SALT", SALT)

    def _disc_with_submitter(self, db, raw_ip: str | None = None):
        submitter = seed_test_user(db)
        ids = seed_test_disc(db, submitted_by_id=submitter.id, status="unverified")
        if raw_ip is not None:
            _seed_submitter_ip(db, ids["disc_id"], submitter.id, raw_ip)
        return db.get(Disc, ids["disc_id"])

    def test_all_signals_absent_passes(self, db_session):
        # No submitter IP hash, no confirmer client → IP signal absent (fail-open).
        disc = self._disc_with_submitter(db_session, raw_ip=None)
        confirmer = make_user_with_age(
            db_session, hours_old=0, username="c1", email="c1@test.local"
        )
        gate = anti_sybil.evaluate_confirmation(
            db_session, disc, confirmer, _request_no_client()
        )
        assert gate.trust_ok is True
        assert gate.hard_blocked is False

    def test_fresh_account_same_subnet_blocks(self, db_session):
        # The exact Sybil signature: young account AND same /24 → -2 → block.
        disc = self._disc_with_submitter(db_session, raw_ip="1.2.3.10")
        confirmer = make_user_with_age(
            db_session, hours_old=0, username="c2", email="c2@test.local"
        )
        gate = anti_sybil.evaluate_confirmation(
            db_session, disc, confirmer, _request("1.2.3.200")
        )
        assert gate.trust_ok is False
        assert gate.hard_blocked is False

    def test_fresh_account_absent_ip_passes(self, db_session):
        # Young alone (-1) never hard-rejects.
        disc = self._disc_with_submitter(db_session, raw_ip=None)
        confirmer = make_user_with_age(
            db_session, hours_old=0, username="c3", email="c3@test.local"
        )
        gate = anti_sybil.evaluate_confirmation(
            db_session, disc, confirmer, _request(None)
        )
        assert gate.trust_ok is True

    def test_established_account_same_subnet_passes(self, db_session):
        # Established (+1) offsets same-subnet (-1) → 0 → pass.
        disc = self._disc_with_submitter(db_session, raw_ip="1.2.3.10")
        confirmer = make_user_with_age(
            db_session, hours_old=30 * 24, username="c4", email="c4@test.local"
        )
        gate = anti_sybil.evaluate_confirmation(
            db_session, disc, confirmer, _request("1.2.3.200")
        )
        assert gate.trust_ok is True

    def test_fresh_account_distinct_subnet_passes(self, db_session):
        # Distinct subnet (+1) offsets young (-1) → 0 → pass.
        disc = self._disc_with_submitter(db_session, raw_ip="1.2.3.10")
        confirmer = make_user_with_age(
            db_session, hours_old=0, username="c5", email="c5@test.local"
        )
        gate = anti_sybil.evaluate_confirmation(
            db_session, disc, confirmer, _request("9.9.9.9")
        )
        assert gate.trust_ok is True

    def test_returned_ip_hash_matches_submitter_on_same_subnet(self, db_session):
        # The gate returns the confirmer's ip_hash for storage on the verify edit.
        disc = self._disc_with_submitter(db_session, raw_ip="1.2.3.10")
        confirmer = make_user_with_age(
            db_session, hours_old=30 * 24, username="c6", email="c6@test.local"
        )
        gate = anti_sybil.evaluate_confirmation(
            db_session, disc, confirmer, _request("1.2.3.200")
        )
        assert gate.ip_hash == anti_sybil.ip_subnet_hash("1.2.3.10", SALT_BYTES)


# ---------------------------------------------------------------------------
# Salt configuration (A5/D-07): missing OVID_IP_HASH_SALT must not raise.
# ---------------------------------------------------------------------------
class TestSaltFailOpen:
    def test_missing_salt_yields_no_ip_signal(self, db_session, monkeypatch):
        monkeypatch.delenv("OVID_IP_HASH_SALT", raising=False)
        submitter = seed_test_user(db_session)
        ids = seed_test_disc(
            db_session, submitted_by_id=submitter.id, status="unverified"
        )
        disc = db_session.get(Disc, ids["disc_id"])
        confirmer = make_user_with_age(
            db_session, hours_old=0, username="c7", email="c7@test.local"
        )
        # No salt → ip_hash None → IP signal absent → young alone passes (fail-open).
        gate = anti_sybil.evaluate_confirmation(
            db_session, disc, confirmer, _request("1.2.3.10")
        )
        assert gate.ip_hash is None
        assert gate.trust_ok is True
