"""OVID lookup wrapper for ARM (Automatic Ripping Machine).

Standalone script that ARM's identify.py can import.  Takes a disc mount
path, fingerprints the disc via the ovid-client library, queries the OVID
API with a hard 5-second timeout, and returns a structured result dict on
hit or ``None`` on miss/error.

**Contract:** this module never raises — every failure path logs to stderr
and returns ``None`` so ARM's ripping pipeline is never blocked by OVID.

Usage (imported)::

    from arm.identify_ovid import lookup_ovid
    result = lookup_ovid("/mnt/dev/sr0")
    if result:
        print(result["title"], result["year"])

Usage (standalone)::

    python -m arm.identify_ovid /mnt/dev/sr0
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import requests

logger = logging.getLogger("arm.identify_ovid")

# If no handler is attached, add a stderr handler so ARM log capture
# picks up OVID messages even when the root logger isn't configured.
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

# Hard timeout for all OVID API calls — ARM must never block on OVID.
_TIMEOUT_SECONDS = 5


# ------------------------------------------------------------------
# BD vs DVD detection (mirrors ovid.cli._is_bd_path)
# ------------------------------------------------------------------

def _is_bd_path(path: str) -> bool:
    """Return True if *path* contains a BDMV subdirectory."""
    if not os.path.isdir(path):
        return False
    basename = os.path.basename(os.path.normpath(path))
    if basename.upper() == "BDMV":
        return True
    try:
        for entry in os.listdir(path):
            if entry.upper() == "BDMV" and os.path.isdir(
                os.path.join(path, entry)
            ):
                return True
    except OSError:
        pass
    return False


# ------------------------------------------------------------------
# Fingerprinting
# ------------------------------------------------------------------

def _fingerprint_disc(disc_path: str) -> str:
    """Fingerprint a disc at *disc_path*, returning the fingerprint string.

    Detects BD vs DVD automatically. Raises on failure (caller catches).
    """
    if _is_bd_path(disc_path):
        from ovid.bd_disc import BDDisc

        disc = BDDisc.from_path(disc_path)
    else:
        from ovid.disc import Disc

        disc = Disc.from_path(disc_path)

    return disc.fingerprint


# ------------------------------------------------------------------
# OVID API lookup (with timeout)
# ------------------------------------------------------------------

def _lookup_api(fingerprint: str, api_url: str) -> dict[str, Any] | None:
    """GET /v1/disc/{fingerprint} with a hard timeout.

    Returns parsed JSON on 200, ``None`` on 404 or any error.
    """
    url = f"{api_url.rstrip('/')}/v1/disc/{fingerprint}"
    resp = requests.get(url, timeout=_TIMEOUT_SECONDS)

    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 404:
        return None

    logger.warning(
        "OVID API returned HTTP %d for fingerprint %s",
        resp.status_code,
        fingerprint,
    )
    return None


# ------------------------------------------------------------------
# Result extraction
# ------------------------------------------------------------------

def _extract_result(fingerprint: str, data: dict[str, Any]) -> dict[str, Any]:
    """Pull the fields ARM cares about from the OVID API response.

    Uses safe ``.get()`` everywhere — partial data is fine.
    """
    release = data.get("release") or {}
    return {
        "fingerprint": fingerprint,
        "title": release.get("title"),
        "year": release.get("year"),
        "imdb_id": release.get("imdb_id"),
        "tmdb_id": release.get("tmdb_id"),
        "confidence": data.get("confidence"),
        "video_type": data.get("format"),
    }


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def lookup_ovid(
    disc_path: str,
    api_url: str = "http://api:8000",
) -> dict[str, Any] | None:
    """Fingerprint a disc and look it up against the OVID API.

    Args:
        disc_path: Mount point of the disc (e.g. ``/mnt/dev/sr0``).
        api_url:   Base URL of the OVID API (default ``http://api:8000``
                   for the Docker-internal network).

    Returns:
        A dict with ``fingerprint``, ``title``, ``year``, ``imdb_id``,
        ``tmdb_id``, ``confidence``, and ``video_type`` on a hit.
        ``None`` on a miss or any error.
    """
    # ── Step 1: Fingerprint ──────────────────────────────────────────
    try:
        fingerprint = _fingerprint_disc(disc_path)
    except FileNotFoundError as exc:
        logger.info("OVID fingerprint skipped (not found): %s", exc)
        return None
    except (ValueError, OSError) as exc:
        logger.warning("OVID fingerprint failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("OVID fingerprint unexpected error: %s", exc)
        return None

    logger.info("OVID fingerprint: %s", fingerprint)

    # ── Step 2: API lookup ───────────────────────────────────────────
    try:
        data = _lookup_api(fingerprint, api_url)
    except requests.exceptions.Timeout:
        logger.warning(
            "OVID lookup timed out after %ds for %s",
            _TIMEOUT_SECONDS,
            fingerprint,
        )
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("OVID API unreachable at %s", api_url)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("OVID lookup unexpected error: %s", exc)
        return None

    if data is None:
        logger.info("OVID lookup: no match for %s", fingerprint)
        return None

    result = _extract_result(fingerprint, data)
    logger.info(
        "OVID lookup: %s → %s (%s) [%s]",
        fingerprint,
        result.get("title"),
        result.get("year"),
        result.get("confidence"),
    )
    return result


# ------------------------------------------------------------------
# Standalone entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    import json

    if len(sys.argv) < 2:
        print("Usage: python -m arm.identify_ovid <disc_path> [api_url]", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    url = sys.argv[2] if len(sys.argv) > 2 else "http://api:8000"
    r = lookup_ovid(path, url)
    print(json.dumps(r))
