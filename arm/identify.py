# Volume-mounted overlay for ARM's identify.py — adds OVID fingerprint lookup
# before ARM's standard metadata lookup (OMDB/TMDB).
#
# This file is bind-mounted into the ARM container at:
#   /opt/arm/arm/ripper/identify.py
#
# It imports the OVID lookup wrapper (identify_ovid.py, mounted alongside it),
# runs the OVID check, and if it gets a high/medium-confidence hit, populates
# the ARM job directly.  Otherwise, it delegates to the original ARM identify
# functions via a backup-path import.
#
# The original identify.py is renamed to identify_original.py by the entrypoint
# wrapper so this shim can import it without circular conflicts.
#
# CRITICAL: ARM's main.py (line ~94) calls `identify.identify(job)`.
# This module MUST export `identify(job)` as its main entry point.

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
from typing import Any

logger = logging.getLogger("arm.identify")

# ---------------------------------------------------------------------------
# Import the OVID lookup helper (mounted alongside this file)
# ---------------------------------------------------------------------------

try:
    from arm.ripper.identify_ovid import lookup_ovid, fingerprint_disc, submit_to_ovid
except ImportError:
    try:
        from identify_ovid import lookup_ovid, fingerprint_disc, submit_to_ovid  # type: ignore[no-redef]
    except ImportError:
        logger.warning("identify_ovid module not found — OVID lookup disabled")
        lookup_ovid = None  # type: ignore[assignment]
        fingerprint_disc = None  # type: ignore[assignment]
        submit_to_ovid = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Import original ARM identify module from the backup copy
# ---------------------------------------------------------------------------

_original_module = None


def _load_original() -> Any:
    """Lazily load the original ARM identify module (identify_original.py)."""
    global _original_module
    if _original_module is not None:
        return _original_module

    # The entrypoint wrapper copies the original identify.py to
    # identify_original.py before this overlay is activated.
    original_path = os.path.join(os.path.dirname(__file__), "identify_original.py")

    if os.path.isfile(original_path):
        spec = importlib.util.spec_from_file_location(
            "arm.ripper.identify_original", original_path
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _original_module = mod
            return mod

    logger.warning(
        "Original identify.py not found at %s — delegation will fail", original_path
    )
    return None


# ---------------------------------------------------------------------------
# OVID hook
# ---------------------------------------------------------------------------


def _try_ovid(job: Any, disc_path: str) -> tuple[bool, str | None]:
    """Attempt an OVID fingerprint lookup for the disc at *disc_path*.

    On a high/medium-confidence hit, populates ``job.title``, ``job.year``,
    ``job.video_type``, sets ``job.hasnicetitle = True``, and returns
    ``(True, fingerprint)``.

    On miss, returns ``(False, fingerprint)`` so the caller can submit
    after ARM fills in OMDB metadata.

    On fingerprint failure, returns ``(False, None)``.
    """
    if lookup_ovid is None:
        return False, None

    api_url = os.environ.get("OVID_API_URL", "http://api:8000")

    try:
        result = lookup_ovid(disc_path, api_url=api_url)
    except Exception:  # noqa: BLE001
        logger.warning("OVID lookup raised unexpectedly — falling back to OMDB")
        return False, None

    if result is None:
        # Miss — but we still want the fingerprint for post-identify submit.
        # lookup_ovid returns None on miss, but it logged the fingerprint.
        # Re-fingerprint to capture the value (fast — already parsed).
        fp = None
        if fingerprint_disc is not None:
            try:
                fp = fingerprint_disc(disc_path)
            except Exception:  # noqa: BLE001
                pass
        logger.info("OVID miss, falling back to OMDB")
        return False, fp

    confidence = result.get("confidence")
    if confidence not in ("high", "medium"):
        logger.info(
            "OVID match confidence too low (%s), falling back to OMDB", confidence
        )
        return False, result.get("fingerprint")

    # Populate the ARM job from OVID data
    if result.get("title"):
        job.title = result["title"]
    if result.get("year"):
        job.year = result["year"]
    if result.get("video_type"):
        job.video_type = result["video_type"]

    # Tell ARM the disc has a nice title so it skips fuzzy matching
    job.hasnicetitle = True

    logger.info("OVID lookup: %s", result.get("fingerprint", "unknown"))
    return True, result.get("fingerprint")


# ---------------------------------------------------------------------------
# Public API — identify(job) is what ARM's main.py calls
# ---------------------------------------------------------------------------


def _ensure_mounted(job: Any, retries: int = 6, retry_delay: float = 2.0) -> bool:
    """Mount the disc at job.mountpoint if not already mounted.

    ARM's original identify() does this too, but we need the disc
    filesystem visible *before* OVID fingerprinting so we can read
    VIDEO_TS (DVD) or BDMV (Blu-ray) structures.

    Optical drives take several seconds to spin up after disc insertion.
    We retry the mount + findmnt verification up to *retries* times with
    *retry_delay* seconds between attempts.  ARM's identify code explicitly
    documents that ``mount`` can return 0 yet fail to mount the drive —
    so we always verify with ``findmnt -M`` as ARM does.

    Returns True if the disc is confirmed mounted after this call.
    """
    import time

    mountpoint = getattr(job, "mountpoint", "")
    if not mountpoint:
        return False

    # Already mounted? Verify with findmnt (not just os.path.ismount —
    # that checks filesystem device IDs, which can be unreliable here).
    if os.system(f"findmnt -M {mountpoint} >/dev/null 2>&1") == 0:
        logger.info("OVID: disc already mounted at %s", mountpoint)
        return True

    # Create mountpoint directory if needed
    if not os.path.exists(mountpoint):
        try:
            os.makedirs(mountpoint)
        except OSError as exc:
            logger.warning("OVID: could not create mountpoint %s: %s", mountpoint, exc)
            return False

    for attempt in range(1, retries + 1):
        mount_rc = os.system(f"mount {mountpoint} >/dev/null 2>&1")
        findmnt_rc = os.system(f"findmnt -M {mountpoint} >/dev/null 2>&1")

        if findmnt_rc == 0:
            logger.info(
                "OVID: pre-mount of %s succeeded (attempt %d/%d)",
                mountpoint,
                attempt,
                retries,
            )
            return True

        logger.info(
            "OVID: pre-mount attempt %d/%d failed (mount_rc=%d, findmnt_rc=%d) — "
            "disc may still be spinning up, retrying in %.0fs",
            attempt,
            retries,
            mount_rc,
            findmnt_rc,
            retry_delay,
        )
        time.sleep(retry_delay)

    logger.warning(
        "OVID: pre-mount of %s failed after %d attempts — skipping OVID fingerprint",
        mountpoint,
        retries,
    )
    return False


def identify(job: Any) -> Any:
    """Identify a disc, trying OVID first then falling back to ARM's original.

    This is the main entry point. ARM's main.py calls ``identify.identify(job)``
    at line ~94. The job object carries all disc metadata ARM needs.

    Strategy:
    1. Mount the disc so OVID can read VIDEO_TS / BDMV.
    2. Fingerprint and look up in OVID API.
    3. On hit: populate the job and return (skip OMDB entirely).
    4. On miss: delegate to ARM's original identify (OMDB fills title/year).
    5. After ARM identify: submit fingerprint + OMDB metadata to OVID API
       so the *next* insert of the same disc gets a hit.
    """
    # ── Guard: OVID can be disabled via environment variable ──────────
    ovid_enabled = os.environ.get("OVID_ENABLED", "true").lower() != "false"
    ovid_fingerprint = None

    if ovid_enabled:
        # ARM mounts discs at job.mountpoint (e.g. /mnt/dev/sr0)
        disc_path = getattr(job, "mountpoint", "") or getattr(job, "devpath", "")
        if disc_path:
            # Ensure disc is mounted so OVID can read VIDEO_TS / BDMV.
            # Only attempt fingerprinting if mount succeeds — avoids
            # wasting time on an empty directory (which produces misleading
            # "No VIDEO_TS directory found" errors instead of the real cause).
            if _ensure_mounted(job):
                hit, ovid_fingerprint = _try_ovid(job, disc_path)
                if hit:
                    # OVID populated the job — skip OMDB entirely
                    return job

    # ── Delegate to original ARM identify ─────────────────────────────
    original = _load_original()
    if original and hasattr(original, "identify"):
        result = original.identify(job)
    else:
        logger.error(
            "Cannot delegate to original identify — ARM's original module "
            "is not available.  Job will continue with whatever metadata is set."
        )
        result = job

    # ── Post-identify: submit to OVID on miss ─────────────────────────
    # ARM's original identify has now populated job.title, job.year, etc.
    # from OMDB.  Submit the fingerprint + metadata so the next insert
    # of this disc gets an OVID hit.
    if ovid_enabled and ovid_fingerprint and submit_to_ovid is not None:
        title = getattr(job, "title", "") or ""
        year = getattr(job, "year", None)
        disc_format = getattr(job, "disctype", "") or ""
        disc_label = getattr(job, "label", "") or ""
        video_type = getattr(job, "video_type", "") or ""

        if title:
            try:
                api_url = os.environ.get("OVID_API_URL", "http://api:8000")
                submit_to_ovid(
                    fingerprint=ovid_fingerprint,
                    title=title,
                    year=year,
                    disc_format=disc_format,
                    disc_label=disc_label,
                    video_type=video_type,
                    api_url=api_url,
                )
            except Exception:  # noqa: BLE001
                logger.warning("OVID auto-submit raised unexpectedly — ignoring")
        else:
            logger.info(
                "OVID auto-submit skipped — no title from OMDB for %s",
                ovid_fingerprint,
            )

    return result


def identify_disc(
    job: Any,
    dvd_info: Any = None,
    dvd_title: str = "",
    year: str = "",
    api: Any = None,
) -> Any:
    """Backward-compat alias — delegates to identify(job).

    The old S01 shim exported this, but ARM's main.py actually calls
    identify(job). Kept for safety in case any secondary code path calls it.
    """
    return identify(job)


# ---------------------------------------------------------------------------
# Re-export all original ARM symbols so other imports still work
# ---------------------------------------------------------------------------
# ARM code elsewhere may do:
#   from arm.ripper.identify import identify_dvd, identify_bluray, etc.
# We re-export everything from the original module.

_orig = _load_original()
if _orig:
    for _name in dir(_orig):
        if not _name.startswith("_") and _name not in ("identify", "identify_disc"):
            globals()[_name] = getattr(_orig, _name)
