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

def fingerprint_disc(disc_path: str) -> str:
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
        fingerprint = fingerprint_disc(disc_path)
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
# Auto-submit on miss
# ------------------------------------------------------------------

def submit_to_ovid(
    fingerprint: str,
    title: str,
    year: int | str | None,
    disc_format: str,
    disc_label: str | None = None,
    video_type: str | None = None,
    api_url: str = "http://api:8000",
) -> bool:
    """Submit a disc to OVID after a miss, using metadata from ARM/OMDB.

    Called after ARM's original identify populates the job with title/year
    from OMDB.  This seeds the OVID database so the *next* insert of the
    same disc gets a hit.

    Requires ``OVID_API_TOKEN`` environment variable to be set with a valid
    JWT.  If missing, the submit is silently skipped.

    Args:
        fingerprint: OVID fingerprint string (dvd1-*, bd1-aacs-*, etc.).
        title: Disc title from ARM/OMDB (may have dashes instead of spaces).
        year: Release year from OMDB.
        disc_format: ``'dvd'`` or ``'bluray'`` (ARM's disctype).
        disc_label: Disc volume label (e.g. ``DOCTOR_WHO``).
        video_type: ``'movie'`` or ``'series'`` from ARM.
        api_url: Base URL of the OVID API.

    Returns:
        True if the submission succeeded (HTTP 201 or 409), False otherwise.
    """
    token = os.environ.get("OVID_API_TOKEN", "")
    if not token:
        # Fallback: read from file (useful when env var can't be set
        # on a running container without restart)
        token_file = os.path.join(
            os.path.dirname(__file__), "..", "..", "home", "arm", "ovid", ".ovid_token"
        )
        # Also try a fixed path inside the container
        for path in [token_file, "/home/arm/ovid/.ovid_token"]:
            try:
                with open(path) as f:
                    token = f.read().strip()
                if token:
                    break
            except OSError:
                continue
    if not token:
        logger.info("OVID auto-submit skipped — no OVID_API_TOKEN or .ovid_token")
        return False

    if not fingerprint or not title:
        logger.info("OVID submit skipped — missing fingerprint or title")
        return False

    # Clean up ARM's dash-separated title → spaces
    clean_title = title.replace("-", " ").replace("  ", " ").strip()

    # Map ARM's disctype to OVID format
    fmt = "bluray" if disc_format and "blu" in disc_format.lower() else "dvd"

    # Map ARM's video_type to OVID content_type
    content_type = "movie"
    if video_type and video_type.lower() in ("series", "tv", "tvshow"):
        content_type = "series"

    # Parse year
    parsed_year = None
    if year:
        try:
            parsed_year = int(str(year).strip())
        except (ValueError, TypeError):
            pass

    payload = {
        "fingerprint": fingerprint,
        "format": fmt,
        "disc_label": disc_label or "",
        "release": {
            "title": clean_title,
            "year": parsed_year,
            "content_type": content_type,
        },
        "titles": [],
    }

    headers = {"Authorization": f"Bearer {token}"}
    url = f"{api_url.rstrip('/')}/v1/disc"
    try:
        resp = requests.post(
            url, json=payload, headers=headers, timeout=_TIMEOUT_SECONDS
        )
    except requests.exceptions.Timeout:
        logger.warning("OVID submit timed out after %ds", _TIMEOUT_SECONDS)
        return False
    except requests.exceptions.ConnectionError:
        logger.warning("OVID API unreachable at %s for submit", api_url)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("OVID submit unexpected error: %s", exc)
        return False

    if resp.status_code == 201:
        logger.info(
            "OVID submit: %s → %s (%s) — disc seeded in database",
            fingerprint,
            clean_title,
            parsed_year,
        )
        return True

    if resp.status_code == 409:
        logger.info("OVID submit: %s already exists (409)", fingerprint)
        return True  # Already there — that's fine

    logger.warning(
        "OVID submit failed: HTTP %d for %s — %s",
        resp.status_code,
        fingerprint,
        resp.text[:200] if resp.text else "(no body)",
    )
    return False


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
