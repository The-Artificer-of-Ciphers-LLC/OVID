# Volume-mounted overlay for ARM's identify.py — adds OVID fingerprint lookup
# before metadata_selector().
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

from __future__ import annotations

import importlib
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
    and ``job.video_type`` and returns ``True``.

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
        logging.info("OVID miss, falling back to OMDB")
        return False

    confidence = result.get("confidence")
    if confidence not in ("high", "medium"):
        logging.info(
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

    logging.info("OVID lookup: %s", result["fingerprint"])
    return True


# ---------------------------------------------------------------------------
# Public API — drop-in replacement for ARM's identify_disc()
# ---------------------------------------------------------------------------

def identify_disc(
    job: Any,
    dvd_info: Any = None,
    dvd_title: str = "",
    year: str = "",
    api: Any = None,
) -> Any:
    """Identify a disc, trying OVID first then falling back to ARM's original.

    This function is the main entry point that ARM's ripper module calls.
    It mirrors the signature of the original ``identify_disc`` so it is a
    transparent drop-in replacement.
    """
    # ── Guard: OVID can be disabled via environment variable ──────────
    ovid_enabled = os.environ.get("OVID_ENABLED", "true").lower() != "false"

    if ovid_enabled:
        disc_path = getattr(job, "devpath", None) or getattr(job, "mountpoint", "")
        if disc_path:
            if _try_ovid(job, disc_path):
                # OVID populated the job — skip OMDB entirely
                return job

    # ── Delegate to original ARM identify_disc ────────────────────────
    original = _load_original()
    if original and hasattr(original, "identify_disc"):
        return original.identify_disc(job, dvd_info, dvd_title, year, api)

    logger.error(
        "Cannot delegate to original identify_disc — ARM's original module "
        "is not available.  Job will continue with whatever metadata is set."
    )
    return job


# Re-export everything from the original module so callers that do
# ``from arm.ripper.identify import some_helper`` still work.
_orig = _load_original()
if _orig:
    for _name in dir(_orig):
        if not _name.startswith("_") and _name != "identify_disc":
            globals()[_name] = getattr(_orig, _name)
