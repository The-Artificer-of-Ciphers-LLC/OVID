"""D-01 promotion transform: ``promote_one_disc`` / ``promote_all_dvdread1_discs``.

These test the plain, Alembic-independent functions in
``app.migrations_support`` directly against the project's in-memory SQLite
harness — no Alembic invocation anywhere in this file (Pitfall 5: CI never
runs a real ``alembic upgrade head`` against Postgres, so this transform
must be provable without one).
"""

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.migrations_support import promote_all_dvdread1_discs, promote_one_disc
from app.models import Disc, DiscIdentityAlias
from tests.conftest import _TestSession


def _seed_disc_with_alias(
    db: Session,
    *,
    dvd1_fingerprint: str,
    dvdread1_fingerprint: str | None,
) -> Disc:
    """Seed a Disc whose primary fingerprint is ``dvd1_fingerprint``, plus an
    optional ``dvdread1-*`` Lookup Alias row. Commits so the raw-SQL
    promotion helpers (which operate on ``connection`` rather than the ORM
    session) see durable state."""
    disc = Disc(fingerprint=dvd1_fingerprint, format="DVD", status="verified")
    db.add(disc)
    db.flush()
    if dvdread1_fingerprint is not None:
        db.add(DiscIdentityAlias(disc_id=disc.id, fingerprint=dvdread1_fingerprint))
    db.commit()
    return disc


def _fetch_disc_row(db: Session, disc_id: uuid.UUID):
    # .hex: raw text() binds are untyped and bypass the ORM UUID type
    # decorator's bind processor, so a bare uuid.UUID fails against sqlite3;
    # the column is physically stored as hex-no-dash under SQLite, so a
    # dashed str(disc_id) would silently match zero rows instead of erroring.
    return db.execute(
        text("SELECT id, fingerprint FROM discs WHERE id = :id"),
        {"id": disc_id.hex},
    ).first()


def _fetch_alias_rows(db: Session, disc_id: uuid.UUID):
    return db.execute(
        text(
            "SELECT id, fingerprint FROM disc_identity_aliases WHERE disc_id = :id"
        ),
        {"id": disc_id.hex},
    ).all()


class TestPromoteOneDisc:
    """Task 1: per-disc promotion + idempotency."""

    def test_promotes_disc_with_dvdread1_alias(self, db_session: Session) -> None:
        disc = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-promote-a",
            dvdread1_fingerprint="dvdread1-promote-a",
        )

        result = promote_one_disc(db_session.connection(), "dvd1-promote-a")

        assert result is True

        disc_row = _fetch_disc_row(db_session, disc.id)
        assert disc_row.fingerprint == "dvdread1-promote-a"

        alias_rows = _fetch_alias_rows(db_session, disc.id)
        alias_fingerprints = {row.fingerprint for row in alias_rows}
        assert alias_fingerprints == {"dvd1-promote-a"}, (
            "the OLD dvd1-* value must now exist as the sole alias row; the "
            "dvdread1-* alias row must be gone (deleted, not duplicated)"
        )

    def test_already_promoted_disc_is_safe_noop(self, db_session: Session) -> None:
        # discs.fingerprint no longer equals the dvd1-* value passed in
        # (already promoted, or was never that value) -> False, zero changes.
        disc = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvdread1-promote-b",
            dvdread1_fingerprint=None,
        )

        result = promote_one_disc(db_session.connection(), "dvd1-promote-b")

        assert result is False
        disc_row = _fetch_disc_row(db_session, disc.id)
        assert disc_row.fingerprint == "dvdread1-promote-b"
        assert _fetch_alias_rows(db_session, disc.id) == []

    def test_disc_with_no_dvdread1_alias_is_safe_noop(
        self, db_session: Session
    ) -> None:
        disc = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-promote-c",
            dvdread1_fingerprint=None,
        )

        result = promote_one_disc(db_session.connection(), "dvd1-promote-c")

        assert result is False
        disc_row = _fetch_disc_row(db_session, disc.id)
        assert disc_row.fingerprint == "dvd1-promote-c"
        assert _fetch_alias_rows(db_session, disc.id) == []

    def test_double_invocation_is_idempotent(self, db_session: Session) -> None:
        disc = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-promote-d",
            dvdread1_fingerprint="dvdread1-promote-d",
        )

        first = promote_one_disc(db_session.connection(), "dvd1-promote-d")
        second = promote_one_disc(db_session.connection(), "dvd1-promote-d")

        assert first is True
        assert second is False, (
            "a second invocation for the same dvd1-* value must be a no-op "
            "(idempotent re-run safety), proven via an actual double call"
        )

        disc_row = _fetch_disc_row(db_session, disc.id)
        assert disc_row.fingerprint == "dvdread1-promote-d"
        alias_rows = _fetch_alias_rows(db_session, disc.id)
        assert {row.fingerprint for row in alias_rows} == {"dvd1-promote-d"}


class TestPromoteAllDvdread1Discs:
    """Task 2: bulk driver with per-disc commit."""

    def test_promotes_only_eligible_discs(self, db_session: Session) -> None:
        disc_a = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-bulk-a",
            dvdread1_fingerprint="dvdread1-bulk-a",
        )
        disc_b = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-bulk-b",
            dvdread1_fingerprint="dvdread1-bulk-b",
        )
        disc_c = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-bulk-c",
            dvdread1_fingerprint=None,
        )

        promoted_count = promote_all_dvdread1_discs(db_session.connection())

        assert promoted_count == 2
        assert _fetch_disc_row(db_session, disc_a.id).fingerprint == "dvdread1-bulk-a"
        assert _fetch_disc_row(db_session, disc_b.id).fingerprint == "dvdread1-bulk-b"
        assert _fetch_disc_row(db_session, disc_c.id).fingerprint == "dvd1-bulk-c", (
            "a disc with no dvdread1-* alias must be left untouched"
        )

    def test_rerun_is_fully_idempotent(self, db_session: Session) -> None:
        _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-bulk-d",
            dvdread1_fingerprint="dvdread1-bulk-d",
        )
        _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-bulk-e",
            dvdread1_fingerprint="dvdread1-bulk-e",
        )

        first_run = promote_all_dvdread1_discs(db_session.connection())
        second_run = promote_all_dvdread1_discs(db_session.connection())

        assert first_run == 2
        assert second_run == 0, (
            "a full bulk re-run must be fully idempotent — both promoted "
            "discs now fail promote_one_disc's idempotency guard"
        )

    def test_each_promoted_disc_is_durably_committed_independently(
        self, db_session: Session
    ) -> None:
        disc = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-bulk-f",
            dvdread1_fingerprint="dvdread1-bulk-f",
        )

        promoted_count = promote_all_dvdread1_discs(db_session.connection())
        assert promoted_count == 1

        # A FRESH Session (not the same in-flight transaction as db_session)
        # must already see the promoted state — proves per-disc
        # connection.commit() actually ran (SQLAlchemy 2.0 commit-as-you-go),
        # not merely a single commit staged for the very end.
        fresh_db = _TestSession()
        try:
            fresh_row = fresh_db.execute(
                text("SELECT fingerprint FROM discs WHERE id = :id"),
                {"id": disc.id.hex},
            ).first()
            assert fresh_row is not None
            assert fresh_row.fingerprint == "dvdread1-bulk-f"
        finally:
            fresh_db.close()


class TestPromoteAllDvdread1DiscsCommitParam:
    """Regression test (post-cutover live bug): ``commit=False`` must leave
    ALL transaction control to the caller — pinning the fix for migration
    900000000006, which discarded Alembic's ``alembic_version`` stamp
    because ``promote_all_dvdread1_discs`` unconditionally committed
    Alembic's own bind mid-migration."""

    def test_commit_false_leaves_transaction_control_to_caller(
        self, db_session: Session
    ) -> None:
        disc = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-nocommit-a",
            dvdread1_fingerprint="dvdread1-nocommit-a",
        )

        promoted_count = promote_all_dvdread1_discs(
            db_session.connection(), commit=False
        )
        assert promoted_count == 1

        # Roll back the CALLER's transaction — simulating Alembic never
        # committing its own migration transaction (e.g. because it
        # rolled back on error, or simply hasn't reached its own commit
        # point yet). With commit=False, promote_all_dvdread1_discs must
        # not have committed anything of its own.
        db_session.rollback()

        # A FRESH Session/connection must NOT see the promotion — proving
        # commit=False left transaction control entirely to the caller,
        # unlike the commit=True (default) path exercised by
        # test_each_promoted_disc_is_durably_committed_independently above.
        fresh_db = _TestSession()
        try:
            fresh_row = fresh_db.execute(
                text("SELECT fingerprint FROM discs WHERE id = :id"),
                {"id": disc.id.hex},
            ).first()
            assert fresh_row is not None
            assert fresh_row.fingerprint == "dvd1-nocommit-a", (
                "commit=False must not commit the promotion; rolling back "
                "the caller's own transaction must fully undo it (this is "
                "the exact guarantee an Alembic migration relies on so its "
                "post-upgrade() alembic_version stamp commits atomically "
                "with the promotion, rather than being silently discarded)"
            )
        finally:
            fresh_db.close()

    def test_commit_true_default_persists_across_caller_rollback(
        self, db_session: Session
    ) -> None:
        disc = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-commit-b",
            dvdread1_fingerprint="dvdread1-commit-b",
        )

        connection = db_session.connection()
        promoted_count = promote_all_dvdread1_discs(connection)
        assert promoted_count == 1

        # commit=True (the default) commits as-you-go INSIDE the function
        # itself (SQLAlchemy 2.0 "commit as you go" directly on
        # ``connection`` -- the same Core Connection db_session is using).
        # That ends the transaction segment at the DBAPI level before this
        # function returns, which is exactly WHY a subsequent rollback on
        # the caller's own session/connection cannot undo it: there is
        # nothing left to roll back.
        #
        # We prove that directly here rather than by actually calling
        # ``db_session.rollback()``: the ORM Session object still believes
        # it owns an active transaction (``db_session.in_transaction()`` is
        # True) even though the underlying Connection's transaction was
        # already committed and cleared out from under it by the call
        # above. Calling ``db_session.rollback()`` in that state raises
        # ``SAWarning: transaction already deassociated from connection``
        # -- SQLAlchemy itself flagging, at the exact moment of the call,
        # that the rollback has nothing left to undo. That warning *is*
        # this guarantee firing, so we assert the same fact through the
        # public, warning-free ``Connection.in_transaction()`` API instead
        # of triggering it:
        assert not connection.in_transaction(), (
            "promote_all_dvdread1_discs(commit=True) must have already "
            "committed and cleared its transaction segment before "
            "returning -- proving there is no open transaction left for "
            "a caller-side rollback to undo"
        )

        # A FRESH Session (an entirely separate connection/transaction from
        # the one db_session was using) must independently see the
        # promotion -- confirming the commit above was real and durable,
        # not merely "no transaction open" for some unrelated reason.
        fresh_db = _TestSession()
        try:
            fresh_row = fresh_db.execute(
                text("SELECT fingerprint FROM discs WHERE id = :id"),
                {"id": disc.id.hex},
            ).first()
            assert fresh_row is not None
            assert fresh_row.fingerprint == "dvdread1-commit-b", (
                "commit=True (default) must commit as-you-go; with no "
                "open transaction left for a caller to roll back, rows "
                "this function already committed can never be undone"
            )
        finally:
            fresh_db.close()
