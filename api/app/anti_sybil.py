"""VERIFY-04 anti-Sybil confirmation gate.

Decides whether a second contributor's re-submission is ALLOWED to trigger
``verify()`` — it never writes ``disc.status`` (VERIFY-02 keeps every status
transition in ``verification.py``). Three layers, composed by
``evaluate_confirmation``:

  1. Hard floor — a Postgres-native confirmation cooldown counted over the
     existing ``disc_edits`` rows (``edit_type="verify"``). This is worker-safe
     by construction: Postgres is the single shared source of truth across all
     gunicorn workers, unlike the Nx-inflated in-memory slowapi limiter
     (D-13/D-14). It is the launch-safe floor that still holds when every soft
     signal is absent (D-07).
  2. IP pseudonymization — a salted, /24-(IPv4)/ /48-(IPv6)-truncated
     HMAC-SHA256 of the client subnet. Raw IP is never stored or logged (D-06).
     An absent/invalid IP or an unset salt yields NO signal, never a block.
  3. Weighted, offsetting, fail-open trust score over account-age +
     IP-diversity. A merely-distinct ``user_id`` is not, by itself, proof of
     independence (D-05); only the exact Sybil signature (fresh account AND
     same subnet) drops below the block threshold. Any absent signal counts
     for nothing — never against the confirmer (fail-open, D-07).

All thresholds are named, tunable module constants (D-08), not magic numbers:
no fraud data exists yet to calibrate them, so they are launch-safe defaults
chosen to avoid false-rejecting genuine early contributors.
"""

import hashlib
import hmac
import ipaddress
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Disc, DiscEdit, User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunable thresholds (D-08) — launch-safe defaults, easy to retune once real
# usage data exists. The *shape* (hard cooldown floor + weighted, offsetting,
# fail-open soft signals) is locked; these *numbers* are not.
# ---------------------------------------------------------------------------
# Accounts younger than this are treated as a soft negative signal (never a
# hard reject on their own — offsettable by IP diversity).
ACCOUNT_AGE_SOFT_CUTOFF_HOURS = 24

# Confirmation cooldown hard floor: a conservative per-account cap on
# confirmation actions. Exceeding either bound hard-blocks (429).
CONFIRMATION_COOLDOWN_WINDOW_HOURS = 1
CONFIRMATION_MAX_PER_WINDOW = 5
CONFIRMATION_MAX_PER_DAY = 20

# Soft-signal weights (offsetting). The score starts at 0; the ONLY combination
# that reaches the block threshold (-2) is a fresh account AND the same subnet.
YOUNG_ACCOUNT_PENALTY = -1
ESTABLISHED_ACCOUNT_BONUS = +1
SAME_SUBNET_PENALTY = -1
DISTINCT_SUBNET_BONUS = +1
TRUST_BLOCK_THRESHOLD = -2

# Subnet truncation prefixes before hashing (D-06 pseudonymization floor).
IPV4_PREFIX = 24
IPV6_PREFIX = 48

# Environment variable holding the IP-hash salt. Optional-with-warning (A5/D-07):
# a missing salt degrades the IP signal to "absent", it never hard-fails.
_IP_HASH_SALT_ENV = "OVID_IP_HASH_SALT"

# Edit types that record the disc's original submission (source of the
# submitter subnet hash used for the IP-diversity comparison).
_SUBMITTER_EDIT_TYPES = ("create", "identify")

# Guards the one-time "salt unset" warning so logs are not spammed per request.
_salt_warning_emitted = False


@dataclass(frozen=True)
class ConfirmationGate:
    """Outcome of the anti-Sybil pre-check for one confirmation attempt.

    ``hard_blocked``  — cooldown floor exceeded → caller returns 429.
    ``trust_ok``      — weighted soft score above threshold → confirmation
                        allowed (fail-open already applied for absent signals).
    ``ip_hash``       — the confirmer's salted /24 subnet hash (or None), to be
                        stored on the resulting verify ``DiscEdit`` (D-06).
    """

    hard_blocked: bool
    trust_ok: bool
    ip_hash: str | None


def ip_subnet_hash(raw_ip: str | None, salt: bytes | None) -> str | None:
    """Return a salted HMAC-SHA256 hex of the /24 (IPv4) or /48 (IPv6) subnet.

    Fails open (returns None) when the IP is absent/malformed or the salt is
    unset — an absent IP signal must never count against a confirmer (D-07).
    """
    if not raw_ip or not salt:
        return None
    try:
        addr = ipaddress.ip_address(raw_ip)
    except ValueError:
        return None
    prefix = IPV4_PREFIX if addr.version == 4 else IPV6_PREFIX
    net = ipaddress.ip_network(f"{raw_ip}/{prefix}", strict=False)
    return hmac.new(salt, net.network_address.packed, hashlib.sha256).hexdigest()


def client_ip_hash(request) -> str | None:
    """Return the salted /24 (or /48) subnet hash of ``request``'s client IP.

    Thin public wrapper over :func:`ip_subnet_hash` + :func:`_ip_hash_salt` so
    both the confirmation gate and the original-submission create-edit capture
    the subnet hash the same way (D-06). Fails open to ``None`` when the IP or
    salt is absent (D-07).
    """
    raw_ip: str | None = None
    client = getattr(request, "client", None)
    if client is not None:
        raw_ip = getattr(client, "host", None)
    return ip_subnet_hash(raw_ip, _ip_hash_salt())


def _ip_hash_salt() -> bytes | None:
    """Return the IP-hash salt from the environment, or None with a one-time
    warning if unset (optional-with-warning, NOT the fail-fast _require_env
    pattern — preserves fail-open, A5/D-07)."""
    global _salt_warning_emitted
    raw = os.environ.get(_IP_HASH_SALT_ENV)
    if not raw:
        if not _salt_warning_emitted:
            logger.warning(
                "%s is unset — anti-Sybil IP-diversity signal disabled "
                "(fail-open, D-07). Set it to enable the /24 subnet signal.",
                _IP_HASH_SALT_ENV,
            )
            _salt_warning_emitted = True
        return None
    return raw.encode()


def _recent_confirmation_count(
    db: Session, user_id, cutoff: datetime
) -> int:
    """Count a user's ``verify`` edits at/after ``cutoff``.

    ``cutoff`` is computed in Python and passed as a bound parameter, so the
    query is portable across the SQLite test engine and prod Postgres — no
    dialect-specific INTERVAL arithmetic (Pitfall 4).
    """
    count = (
        db.query(func.count())
        .select_from(DiscEdit)
        .filter(
            DiscEdit.user_id == user_id,
            DiscEdit.edit_type == "verify",
            DiscEdit.created_at >= cutoff,
        )
        .scalar()
    )
    return int(count or 0)


def _submitter_ip_hash(db: Session, disc: Disc) -> str | None:
    """Return the ip_hash of the disc's earliest create/identify edit, if any.

    This is the original submitter's subnet hash — the reference the confirmer's
    subnet is compared against for the IP-diversity signal. Absent → no signal.
    """
    edit = (
        db.query(DiscEdit)
        .filter(
            DiscEdit.disc_id == disc.id,
            DiscEdit.edit_type.in_(_SUBMITTER_EDIT_TYPES),
        )
        .order_by(DiscEdit.created_at.asc())
        .first()
    )
    return edit.ip_hash if edit is not None else None


def _account_age_hours(actor: User) -> float | None:
    """Return the actor's account age in hours (None if unknown)."""
    created = actor.created_at
    if created is None:
        return None
    if created.tzinfo is None:
        # SQLite round-trips DateTime(timezone=True) as naive — treat as UTC.
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).total_seconds() / 3600.0


def evaluate_confirmation(
    db: Session, disc: Disc, actor: User, request
) -> ConfirmationGate:
    """Pre-check whether ``actor``'s confirmation of ``disc`` may fire verify().

    Never mutates ``disc.status`` and never commits — it only decides. The
    caller (Plan 03's ``_handle_existing_disc``) turns the result into a 429
    (hard_blocked) or 403 (not trust_ok), and stores ``ip_hash`` on the verify
    DiscEdit when the confirmation proceeds.
    """
    confirmer_hash = client_ip_hash(request)

    # --- Layer 1: hard cooldown floor (Postgres, worker-safe; D-13) ---
    now = datetime.now(timezone.utc)
    hourly = _recent_confirmation_count(
        db, actor.id, now - timedelta(hours=CONFIRMATION_COOLDOWN_WINDOW_HOURS)
    )
    daily = _recent_confirmation_count(db, actor.id, now - timedelta(hours=24))
    hard_blocked = (
        hourly > CONFIRMATION_MAX_PER_WINDOW or daily > CONFIRMATION_MAX_PER_DAY
    )

    # --- Layer 3: weighted, offsetting, fail-open soft score (D-04/D-07) ---
    score = 0
    age_hours = _account_age_hours(actor)
    if age_hours is not None:
        if age_hours < ACCOUNT_AGE_SOFT_CUTOFF_HOURS:
            score += YOUNG_ACCOUNT_PENALTY
        else:
            score += ESTABLISHED_ACCOUNT_BONUS

    submitter_hash = _submitter_ip_hash(db, disc)
    if confirmer_hash is not None and submitter_hash is not None:
        if confirmer_hash == submitter_hash:
            score += SAME_SUBNET_PENALTY
        else:
            score += DISTINCT_SUBNET_BONUS
    # confirmer_hash or submitter_hash absent → 0 contribution (fail-open, D-07)

    trust_ok = score > TRUST_BLOCK_THRESHOLD

    return ConfirmationGate(
        hard_blocked=hard_blocked, trust_ok=trust_ok, ip_hash=confirmer_hash
    )
