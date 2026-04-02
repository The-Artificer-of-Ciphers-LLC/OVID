"""End-to-end pipeline test: fingerprint → submit → lookup → verify metadata.

Proves the full round-trip from ovid-client Disc.from_path() through the
FastAPI POST /v1/disc and GET /v1/disc/{fingerprint} endpoints, verifying
that fingerprint, release metadata, title structure, and track details
survive the trip intact.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from ovid.disc import Disc

# Import the payload builder from the CLI module
from ovid.cli import _build_submit_payload



# ---------------------------------------------------------------------------
# Fixture: a synthetic disc with known structure
# ---------------------------------------------------------------------------

def _write_fixture_folder(
    tmpdir: str,
    vmg_bytes: bytes,
    vts_dict: dict[str, bytes],
) -> str:
    """Write VMG + VTS IFO files into a VIDEO_TS folder. Returns root path."""
    vts_dir = os.path.join(tmpdir, "VIDEO_TS")
    os.makedirs(vts_dir, exist_ok=True)

    with open(os.path.join(vts_dir, "VIDEO_TS.IFO"), "wb") as f:
        f.write(vmg_bytes)

    for name, data in vts_dict.items():
        with open(os.path.join(vts_dir, name), "wb") as f:
            f.write(data)

    return tmpdir


def _make_vmg_ifo(vts_count: int, title_entries: int) -> bytes:
    """Thin wrapper — import from ovid-client test helpers via importlib."""
    import importlib.util

    conftest_path = os.path.join(
        os.path.dirname(__file__), os.pardir, "ovid-client", "tests", "conftest.py"
    )
    spec = importlib.util.spec_from_file_location(
        "ovid_client_test_conftest", os.path.abspath(conftest_path)
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.make_vmg_ifo(vts_count, title_entries)


def _make_vts_ifo(**kwargs) -> bytes:
    """Thin wrapper — import from ovid-client test helpers via importlib."""
    import importlib.util

    conftest_path = os.path.join(
        os.path.dirname(__file__), os.pardir, "ovid-client", "tests", "conftest.py"
    )
    spec = importlib.util.spec_from_file_location(
        "ovid_client_test_conftest", os.path.abspath(conftest_path)
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.make_vts_ifo(**kwargs)


def _make_matrix_fixture() -> tuple[bytes, dict[str, bytes]]:
    """Build a synthetic disc resembling a movie with 2 VTS.

    VTS 1: Main feature — 2h 16m, 39 chapters, 2 audio (en-5.1, fr-2.0), 3 subs
    VTS 2: Extras — 2 short PGCs, 1 audio, 1 sub
    """
    vmg = _make_vmg_ifo(vts_count=2, title_entries=4)

    vts1 = _make_vts_ifo(
        pgcs=[(2, 16, 0, 39)],
        audio_streams=[(0, "en", 6), (0, "fr", 2)],
        subtitle_streams=["en", "fr", "es"],
    )
    vts2 = _make_vts_ifo(
        pgcs=[(0, 12, 30, 5), (0, 3, 45, 2)],
        audio_streams=[(0, "en", 2)],
        subtitle_streams=["en"],
    )
    return vmg, {"VTS_01_0.IFO": vts1, "VTS_02_0.IFO": vts2}


@pytest.fixture()
def synthetic_disc(tmp_path) -> Disc:
    """Create a synthetic disc on disk and return the parsed Disc object."""
    vmg, vts_dict = _make_matrix_fixture()
    folder = _write_fixture_folder(str(tmp_path / "matrix"), vmg, vts_dict)
    return Disc.from_path(folder)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineRoundTrip:
    """Full submit → lookup round-trip with metadata verification."""

    def test_submit_and_lookup(
        self,
        synthetic_disc: Disc,
        client: TestClient,
        auth_header: dict[str, str],
    ):
        """Fingerprint → POST /v1/disc → GET /v1/disc/{fp} → verify all fields."""
        disc = synthetic_disc

        # Build the payload exactly as the real CLI would
        payload = _build_submit_payload(
            disc=disc,
            title="The Matrix",
            year=1999,
            tmdb_id=603,
            imdb_id="tt0133093",
            edition_name="10th Anniversary",
            disc_number=1,
            total_discs=1,
        )

        # ── Submit ──────────────────────────────────────────────────
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 201, f"Submit failed: {resp.text}"

        submit_data = resp.json()
        assert submit_data["fingerprint"] == disc.fingerprint
        assert submit_data["status"] == "unverified"

        # ── Lookup ──────────────────────────────────────────────────
        resp = client.get(f"/v1/disc/{disc.fingerprint}")
        assert resp.status_code == 200, f"Lookup failed: {resp.text}"

        data = resp.json()

        # Fingerprint round-trip
        assert data["fingerprint"] == disc.fingerprint

        # Release metadata
        release = data["release"]
        assert release["title"] == "The Matrix"
        assert release["year"] == 1999
        assert release["content_type"] == "movie"
        assert release["tmdb_id"] == 603
        assert release["imdb_id"] == "tt0133093"

        # Disc-level fields
        assert data["format"] == "DVD"
        assert data["edition_name"] == "10th Anniversary"
        assert data["disc_number"] == 1
        assert data["total_discs"] == 1
        assert data["status"] == "unverified"
        assert data["confidence"] == "medium"  # unverified → medium

        # Titles: VTS1 has 1 PGC, VTS2 has 2 PGCs → 3 titles total
        titles = data["titles"]
        assert len(titles) == 3, f"Expected 3 titles, got {len(titles)}"

        # Title 0 — main feature (first PGC is always main_feature)
        t0 = titles[0]
        assert t0["title_index"] == 0
        assert t0["is_main_feature"] is True
        assert t0["duration_secs"] == 2 * 3600 + 16 * 60  # 8160s
        assert t0["chapter_count"] == 39

        # Audio tracks on title 0 (from VTS1: en-5.1 + fr-2.0)
        assert len(t0["audio_tracks"]) == 2
        audio_en = t0["audio_tracks"][0]
        assert audio_en["language"] == "en"
        assert audio_en["channels"] == 6
        audio_fr = t0["audio_tracks"][1]
        assert audio_fr["language"] == "fr"
        assert audio_fr["channels"] == 2

        # Subtitle tracks on title 0 (from VTS1: en, fr, es)
        assert len(t0["subtitle_tracks"]) == 3
        sub_langs = [s["language"] for s in t0["subtitle_tracks"]]
        assert sub_langs == ["en", "fr", "es"]

        # Title 1 — first extras PGC (not main feature)
        t1 = titles[1]
        assert t1["title_index"] == 1
        assert t1["is_main_feature"] is False
        assert t1["duration_secs"] == 12 * 60 + 30  # 750s
        assert t1["chapter_count"] == 5

        # Title 2 — second extras PGC
        t2 = titles[2]
        assert t2["title_index"] == 2
        assert t2["is_main_feature"] is False
        assert t2["duration_secs"] == 3 * 60 + 45  # 225s
        assert t2["chapter_count"] == 2

    def test_duplicate_submit_returns_409(
        self,
        synthetic_disc: Disc,
        client: TestClient,
        auth_header: dict[str, str],
    ):
        """Submitting the same fingerprint twice returns 409 Conflict."""
        payload = _build_submit_payload(
            disc=synthetic_disc,
            title="The Matrix",
            year=1999,
            tmdb_id=None,
            imdb_id="",
            edition_name=None,
            disc_number=1,
            total_discs=1,
        )

        resp1 = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp1.status_code == 201

        resp2 = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp2.status_code == 409

    def test_lookup_nonexistent_returns_404(self, client: TestClient):
        """Looking up a fingerprint that was never submitted returns 404."""
        resp = client.get("/v1/disc/dvd1-does-not-exist-00000000000000000")
        assert resp.status_code == 404


class TestFingerprintStability:
    """Fingerprint computed client-side matches what the API stores and returns."""

    def test_fingerprint_survives_roundtrip(
        self,
        synthetic_disc: Disc,
        client: TestClient,
        auth_header: dict[str, str],
    ):
        """The exact fingerprint string from Disc.from_path() is stored and
        returned unchanged by the API — no truncation, normalisation, or
        encoding drift."""
        original_fp = synthetic_disc.fingerprint

        payload = _build_submit_payload(
            disc=synthetic_disc,
            title="Fingerprint Stability Test",
            year=2025,
            tmdb_id=None,
            imdb_id="",
            edition_name=None,
            disc_number=1,
            total_discs=1,
        )

        client.post("/v1/disc", json=payload, headers=auth_header)
        resp = client.get(f"/v1/disc/{original_fp}")
        assert resp.status_code == 200
        assert resp.json()["fingerprint"] == original_fp
