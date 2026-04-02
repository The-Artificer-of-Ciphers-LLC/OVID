"""Expanded synthetic fixture suite — parametrized determinism and uniqueness tests.

Proves:
  - 8 diverse disc profiles all produce valid fingerprints (dvd1- prefix, 45 chars)
  - Each profile is deterministic: 100 invocations → same fingerprint every time
  - All profiles produce mutually unique fingerprints
"""

from __future__ import annotations

import os
import tempfile

import pytest

from ovid.disc import Disc
from conftest import encode_bcd_time, make_vts_ifo, make_vmg_ifo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_fixture_folder(
    tmpdir: str,
    vmg_bytes: bytes,
    vts_dict: dict[str, bytes],
) -> str:
    """Write VMG + VTS IFO files into a VIDEO_TS folder."""
    vts_dir = os.path.join(tmpdir, "VIDEO_TS")
    os.makedirs(vts_dir, exist_ok=True)

    with open(os.path.join(vts_dir, "VIDEO_TS.IFO"), "wb") as f:
        f.write(vmg_bytes)

    for name, data in vts_dict.items():
        with open(os.path.join(vts_dir, name), "wb") as f:
            f.write(data)

    return tmpdir


# ---------------------------------------------------------------------------
# 8 fixture profiles
# ---------------------------------------------------------------------------


def fixture_many_vts() -> tuple[str, bytes, dict[str, bytes]]:
    """9 title sets — exercises multi-VTS enumeration."""
    vmg = make_vmg_ifo(vts_count=9, title_entries=9)
    vts_dict = {}
    for i in range(1, 10):
        vts = make_vts_ifo(
            pgcs=[(0, 10 + i, 0, 3)],
            audio_streams=[(0, "en", 2)],
            subtitle_streams=["en"],
        )
        vts_dict[f"VTS_{i:02d}_0.IFO"] = vts
    return "many_vts", vmg, vts_dict


def fixture_many_pgcs() -> tuple[str, bytes, dict[str, bytes]]:
    """8 PGCs in a single VTS — exercises PGC iteration depth."""
    vmg = make_vmg_ifo(vts_count=1, title_entries=8)
    pgcs = [(0, 5 * (i + 1), 0, i + 1) for i in range(8)]
    vts = make_vts_ifo(
        pgcs=pgcs,
        audio_streams=[(0, "en", 6)],
        subtitle_streams=["en"],
    )
    return "many_pgcs", vmg, {"VTS_01_0.IFO": vts}


def fixture_max_streams() -> tuple[str, bytes, dict[str, bytes]]:
    """8 audio × 32 subtitle streams — exercises stream-count boundaries."""
    vmg = make_vmg_ifo(vts_count=1, title_entries=1)
    audio = [
        (0, "en", 6),
        (0, "fr", 6),
        (0, "de", 6),
        (0, "es", 6),
        (4, "it", 2),  # LPCM stereo
        (6, "ja", 6),  # DTS
        (0, "zh", 2),
        (0, "ko", 6),
    ]
    subs = [
        "en", "fr", "de", "es", "it", "ja", "zh", "ko",
        "pt", "nl", "sv", "da", "fi", "no", "pl", "cs",
        "hu", "ro", "bg", "hr", "sk", "sl", "et", "lv",
        "lt", "ga", "mt", "el", "tr", "ru", "uk", "ar",
    ]
    vts = make_vts_ifo(
        pgcs=[(1, 45, 0, 20)],
        audio_streams=audio,
        subtitle_streams=subs,
    )
    return "max_streams", vmg, {"VTS_01_0.IFO": vts}


def fixture_minimal() -> tuple[str, bytes, dict[str, bytes]]:
    """1 VTS, 1 PGC, 0 audio, 0 subtitles — absolute minimum."""
    vmg = make_vmg_ifo(vts_count=1, title_entries=1)
    vts = make_vts_ifo(
        pgcs=[(0, 30, 0, 1)],
        audio_streams=[],
        subtitle_streams=[],
    )
    return "minimal", vmg, {"VTS_01_0.IFO": vts}


def fixture_long_duration() -> tuple[str, bytes, dict[str, bytes]]:
    """9h59m59s BCD edge — max representable single-digit BCD hours."""
    vmg = make_vmg_ifo(vts_count=1, title_entries=1)
    vts = make_vts_ifo(
        pgcs=[(9, 59, 59, 99)],  # 99 chapters, max BCD time
        audio_streams=[(0, "en", 6)],
        subtitle_streams=["en"],
    )
    return "long_duration", vmg, {"VTS_01_0.IFO": vts}


def fixture_short_duration() -> tuple[str, bytes, dict[str, bytes]]:
    """1-second titles — near-zero durations."""
    vmg = make_vmg_ifo(vts_count=2, title_entries=2)
    vts1 = make_vts_ifo(
        pgcs=[(0, 0, 1, 1)],
        audio_streams=[(0, "en", 2)],
        subtitle_streams=[],
    )
    vts2 = make_vts_ifo(
        pgcs=[(0, 0, 1, 1)],
        audio_streams=[(0, "en", 2)],
        subtitle_streams=[],
    )
    return "short_duration", vmg, {"VTS_01_0.IFO": vts1, "VTS_02_0.IFO": vts2}


def fixture_mixed_complexity() -> tuple[str, bytes, dict[str, bytes]]:
    """3 VTS with varying PGC/stream counts — heterogeneous structure."""
    vmg = make_vmg_ifo(vts_count=3, title_entries=5)
    vts1 = make_vts_ifo(
        pgcs=[(2, 15, 30, 24)],
        audio_streams=[(0, "en", 6), (0, "fr", 6), (6, "en", 6)],
        subtitle_streams=["en", "fr", "es", "de"],
    )
    vts2 = make_vts_ifo(
        pgcs=[(0, 3, 0, 2), (0, 5, 0, 3), (0, 1, 30, 1)],
        audio_streams=[(0, "en", 2)],
        subtitle_streams=["en"],
    )
    vts3 = make_vts_ifo(
        pgcs=[(0, 45, 0, 10)],
        audio_streams=[(0, "en", 6), (4, "en", 2)],
        subtitle_streams=["en", "es"],
    )
    return "mixed_complexity", vmg, {
        "VTS_01_0.IFO": vts1,
        "VTS_02_0.IFO": vts2,
        "VTS_03_0.IFO": vts3,
    }


def fixture_zero_pgc_vts() -> tuple[str, bytes, dict[str, bytes]]:
    """VTS with 0 PGCs — edge case for empty title sets."""
    vmg = make_vmg_ifo(vts_count=2, title_entries=1)
    vts1 = make_vts_ifo(
        pgcs=[],
        audio_streams=[(0, "en", 6)],
        subtitle_streams=["en"],
    )
    vts2 = make_vts_ifo(
        pgcs=[(0, 30, 0, 5)],
        audio_streams=[(0, "en", 6)],
        subtitle_streams=["en"],
    )
    return "zero_pgc_vts", vmg, {"VTS_01_0.IFO": vts1, "VTS_02_0.IFO": vts2}


# All fixture builders, in order
ALL_FIXTURES = [
    fixture_many_vts,
    fixture_many_pgcs,
    fixture_max_streams,
    fixture_minimal,
    fixture_long_duration,
    fixture_short_duration,
    fixture_mixed_complexity,
    fixture_zero_pgc_vts,
]

ALL_FIXTURE_IDS = [
    "many_vts",
    "many_pgcs",
    "max_streams",
    "minimal",
    "long_duration",
    "short_duration",
    "mixed_complexity",
    "zero_pgc_vts",
]


# ---------------------------------------------------------------------------
# Parametrized tests
# ---------------------------------------------------------------------------


@pytest.fixture(params=ALL_FIXTURES, ids=ALL_FIXTURE_IDS)
def fixture_disc(request, tmp_path) -> Disc:
    """Materialize each fixture profile as a folder-backed Disc."""
    name, vmg, vts_dict = request.param()
    folder = _write_fixture_folder(str(tmp_path / name), vmg, vts_dict)
    return Disc.from_path(folder)


class TestFixtureValidity:
    """Every fixture profile produces a valid OVID fingerprint."""

    def test_fingerprint_format(self, fixture_disc: Disc):
        assert fixture_disc.fingerprint.startswith("dvd1-"), (
            f"Bad prefix: {fixture_disc.fingerprint}"
        )
        assert len(fixture_disc.fingerprint) == 45, (
            f"Bad length ({len(fixture_disc.fingerprint)}): {fixture_disc.fingerprint}"
        )


class TestDeterminism:
    """Each fixture produces the same fingerprint across 100 invocations."""

    @pytest.mark.parametrize("fixture_fn", ALL_FIXTURES, ids=ALL_FIXTURE_IDS)
    def test_100_calls_same_fingerprint(self, fixture_fn, tmp_path):
        name, vmg, vts_dict = fixture_fn()
        folder = _write_fixture_folder(str(tmp_path / name), vmg, vts_dict)

        first = Disc.from_path(folder).fingerprint
        for i in range(99):
            assert Disc.from_path(folder).fingerprint == first, (
                f"Determinism failure on invocation {i + 2} for profile '{name}'"
            )


class TestUniqueness:
    """All 8 fixture profiles produce mutually distinct fingerprints."""

    def test_all_fingerprints_unique(self, tmp_path):
        fingerprints: dict[str, str] = {}
        for fixture_fn in ALL_FIXTURES:
            name, vmg, vts_dict = fixture_fn()
            folder = _write_fixture_folder(str(tmp_path / name), vmg, vts_dict)
            fp = Disc.from_path(folder).fingerprint
            fingerprints[name] = fp

        # Check mutual uniqueness
        seen: dict[str, str] = {}
        for name, fp in fingerprints.items():
            if fp in seen:
                pytest.fail(
                    f"Fingerprint collision: '{name}' and '{seen[fp]}' "
                    f"both produced {fp}"
                )
            seen[fp] = name

        assert len(seen) == 8, f"Expected 8 unique fingerprints, got {len(seen)}"
