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
    from arm.ripper.identify_ovid import lookup_ovid
except ImportError:
    try:
        from identify_ovid import lookup_ovid  # type: ignore[no-redef]
    except ImportError:
        logger.warning("identify_ovid module not found — OVID lookup disabled")
        lookup_ovid = None  # type: ignore[assignment]

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


def _try_ovid(job: Any, disc_path: str) -> bool:
    """Attempt an OVID fingerprint lookup for the disc at *disc_path*.

    On a high/medium-confidence hit, populates ``job.title``, ``job.year``,
    ``job.video_type``, sets ``job.hasnicetitle = True``, and returns ``True``.

    On miss, timeout, or any error, logs and returns ``False`` so ARM falls
    back to its normal OMDB / TMDB lookup.
    """
    if lookup_ovid is None:
        return False

    api_url = os.environ.get("OVID_API_URL", "http://api:8000")

    try:
        result = lookup_ovid(disc_path, api_url=api_url)
    except Exception:  # noqa: BLE001
        logger.warning("OVID lookup raised unexpectedly — falling back to OMDB")
        return False

    if result is None:
        logger.info("OVID miss, falling back to OMDB")
        return False

    confidence = result.get("confidence")
    if confidence not in ("high", "medium"):
        logger.info(
            "OVID match confidence too low (%s), falling back to OMDB", confidence
        )
        return False

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
    return True


# ---------------------------------------------------------------------------
# Public API — identify(job) is what ARM's main.py calls
# ---------------------------------------------------------------------------


def _ensure_mounted(job: Any) -> bool:
    """Mount the disc at job.mountpoint if not already mounted.

    ARM's original identify() does this too, but we need the disc
    filesystem visible *before* OVID fingerprinting so we can read
    VIDEO_TS (DVD) or BDMV (Blu-ray) structures.

    Returns True if the disc is mounted after this call.
    """
    mountpoint = getattr(job, "mountpoint", "")
    if not mountpoint:
        return False

    # Already mounted?
    if os.path.ismount(mountpoint):
        return True

    # Create mountpoint if needed
    if not os.path.exists(mountpoint):
        try:
            os.makedirs(mountpoint)
        except OSError as exc:
            logger.warning("Could not create mountpoint %s: %s", mountpoint, exc)
            return False

    rc = os.system(f"mount {mountpoint}")
    if rc == 0:
        logger.info("OVID pre-mount of %s succeeded", mountpoint)
        return True

    logger.warning("OVID pre-mount of %s failed (rc=%d)", mountpoint, rc)
    return False


def identify(job: Any) -> Any:
    """Identify a disc, trying OVID first then falling back to ARM's original.

    This is the main entry point. ARM's main.py calls ``identify.identify(job)``
    at line ~94. The job object carries all disc metadata ARM needs.

    Strategy: mount the disc first so OVID can read the disc filesystem
    (VIDEO_TS for DVD, BDMV for Blu-ray), attempt OVID fingerprint lookup,
    and if it hits with high/medium confidence, populate the job and skip
    ARM's OMDB/TMDB lookup entirely.  On miss, delegate to the original
    ARM identify which will re-use the existing mount.
    """
    # ── Guard: OVID can be disabled via environment variable ──────────
    ovid_enabled = os.environ.get("OVID_ENABLED", "true").lower() != "false"

    if ovid_enabled:
        # ARM mounts discs at job.mountpoint (e.g. /mnt/dev/sr0)
        disc_path = getattr(job, "mountpoint", "") or getattr(job, "devpath", "")
        if disc_path:
            # Ensure disc is mounted so OVID can read VIDEO_TS / BDMV
            _ensure_mounted(job)
            if _try_ovid(job, disc_path):
                # OVID populated the job — skip OMDB entirely
                return job

    # ── Delegate to original ARM identify ─────────────────────────────
    original = _load_original()
    if original and hasattr(original, "identify"):
        return original.identify(job)

    logger.error(
        "Cannot delegate to original identify — ARM's original module "
        "is not available.  Job will continue with whatever metadata is set."
    )
    return job


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
