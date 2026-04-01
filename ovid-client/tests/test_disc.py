"""Integration tests for Disc class and CLI entry point.

Proves:
  - Disc.from_path() works with folder and ISO sources
  - Cross-source identity: same fixture → identical fingerprint (R002)
  - Different fixtures → different fingerprints
  - CLI prints fingerprint to stdout
  - Negative cases: missing path, no VIDEO_TS, etc.
"""

from __future__ import annotations

import os
import tempfile

import pycdlib
import pytest
from click.testing import CliRunner

from ovid.cli import main as cli_main
from ovid.disc import Disc

# Re-use the fixture builders from conftest
from conftest import encode_bcd_time, make_vts_ifo, make_vmg_ifo


# ---------------------------------------------------------------------------
# Helpers — build test fixture directories and ISOs
# ---------------------------------------------------------------------------


def _write_fixture_folder(
    tmpdir: str,
    vmg_bytes: bytes,
    vts_dict: dict[str, bytes],
) -> str:
    """Write VMG + VTS IFO files into a VIDEO_TS folder.

    Returns the path to the root directory (parent of VIDEO_TS).
    """
    vts_dir = os.path.join(tmpdir, "VIDEO_TS")
    os.makedirs(vts_dir, exist_ok=True)

    with open(os.path.join(vts_dir, "VIDEO_TS.IFO"), "wb") as f:
        f.write(vmg_bytes)

    for name, data in vts_dict.items():
        with open(os.path.join(vts_dir, name), "wb") as f:
            f.write(data)

    return tmpdir


def _write_fixture_iso(
    iso_path: str,
    vmg_bytes: bytes,
    vts_dict: dict[str, bytes],
) -> str:
    """Write VMG + VTS IFO files into an ISO image.

    Returns the path to the ISO file.
    """
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=1)

    # Add VIDEO_TS directory
    iso.add_directory("/VIDEO_TS")

    # Add VMG
    iso.add_fp(
        _bytes_fp(vmg_bytes),
        len(vmg_bytes),
        "/VIDEO_TS/VIDEO_TS.IFO;1",
    )

    # Add each VTS
    for name, data in vts_dict.items():
        iso.add_fp(
            _bytes_fp(data),
            len(data),
            f"/VIDEO_TS/{name};1",
        )

    iso.write(iso_path)
    iso.close()
    return iso_path


def _bytes_fp(data: bytes):
    """Wrap bytes in a file-like object for pycdlib."""
    import io
    return io.BytesIO(data)


# ---------------------------------------------------------------------------
# Fixture data sets
# ---------------------------------------------------------------------------


def _fixture_set_a() -> tuple[bytes, dict[str, bytes]]:
    """Simple disc: 1 VTS, 1 PGC, 2 audio streams, 1 subtitle."""
    vmg = make_vmg_ifo(vts_count=1, title_entries=1)
    vts = make_vts_ifo(
        pgcs=[(1, 30, 0, 12)],  # 1h30m = 5400s, 12 chapters
        audio_streams=[(0, "en", 6), (0, "fr", 6)],
        subtitle_streams=["en"],
    )
    return vmg, {"VTS_01_0.IFO": vts}


def _fixture_set_b() -> tuple[bytes, dict[str, bytes]]:
    """Different disc: 2 VTS, multiple PGCs."""
    vmg = make_vmg_ifo(vts_count=2, title_entries=3)
    vts1 = make_vts_ifo(
        pgcs=[(0, 45, 30, 8)],  # 45m30s = 2730s, 8 chapters
        audio_streams=[(0, "en", 6)],
        subtitle_streams=["en", "es"],
    )
    vts2 = make_vts_ifo(
        pgcs=[(0, 5, 0, 2), (0, 3, 0, 1)],
        audio_streams=[(0, "en", 2)],
        subtitle_streams=[],
    )
    return vmg, {"VTS_01_0.IFO": vts1, "VTS_02_0.IFO": vts2}


# ---------------------------------------------------------------------------
# Disc integration tests
# ---------------------------------------------------------------------------


class TestDiscFromPath:
    """Test Disc.from_path() with folder and ISO sources."""

    def test_folder_source(self, tmp_path):
        vmg, vts_dict = _fixture_set_a()
        folder = _write_fixture_folder(str(tmp_path), vmg, vts_dict)

        disc = Disc.from_path(folder)
        assert disc.fingerprint.startswith("dvd1-")
        assert len(disc.fingerprint) == 45
        assert disc.source_type == "FolderReader"
        assert disc.vts_count == 1
        assert disc.title_count == 1

    def test_iso_source(self, tmp_path):
        vmg, vts_dict = _fixture_set_a()
        iso_path = str(tmp_path / "test.iso")
        _write_fixture_iso(iso_path, vmg, vts_dict)

        disc = Disc.from_path(iso_path)
        assert disc.fingerprint.startswith("dvd1-")
        assert len(disc.fingerprint) == 45
        assert disc.source_type == "ISOReader"

    def test_cross_source_identity(self, tmp_path):
        """Same fixture from folder and ISO → identical fingerprint (R002)."""
        vmg, vts_dict = _fixture_set_a()

        folder = _write_fixture_folder(str(tmp_path / "folder"), vmg, vts_dict)
        iso_path = str(tmp_path / "test.iso")
        _write_fixture_iso(iso_path, vmg, vts_dict)

        folder_disc = Disc.from_path(folder)
        iso_disc = Disc.from_path(iso_path)

        assert folder_disc.fingerprint == iso_disc.fingerprint
        assert folder_disc.canonical_string == iso_disc.canonical_string

    def test_different_fixtures_different_fingerprints(self, tmp_path):
        """Different disc structures → different fingerprints."""
        vmg_a, vts_a = _fixture_set_a()
        vmg_b, vts_b = _fixture_set_b()

        folder_a = _write_fixture_folder(str(tmp_path / "disc_a"), vmg_a, vts_a)
        folder_b = _write_fixture_folder(str(tmp_path / "disc_b"), vmg_b, vts_b)

        disc_a = Disc.from_path(folder_a)
        disc_b = Disc.from_path(folder_b)

        assert disc_a.fingerprint != disc_b.fingerprint

    def test_canonical_string_format(self, tmp_path):
        """Canonical string matches expected pipe-delimited format."""
        vmg, vts_dict = _fixture_set_a()
        folder = _write_fixture_folder(str(tmp_path), vmg, vts_dict)

        disc = Disc.from_path(folder)
        parts = disc.canonical_string.split("|")

        assert parts[0] == "OVID-DVD-1"
        assert parts[1] == "1"  # vts_count
        assert parts[2] == "1"  # title_count
        # VTS block: pgc_count:dur:chaps:audio:subs
        assert parts[3].startswith("1:")


# ---------------------------------------------------------------------------
# Negative tests — Disc
# ---------------------------------------------------------------------------


class TestDiscNegative:
    """Error paths for Disc.from_path()."""

    def test_nonexistent_path(self):
        with pytest.raises(FileNotFoundError, match="does not exist"):
            Disc.from_path("/nonexistent/path/nowhere")

    def test_no_video_ts(self, tmp_path):
        """Directory with no VIDEO_TS → FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            Disc.from_path(str(tmp_path))


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Test the `ovid fingerprint` command via CliRunner."""

    def test_fingerprint_command_success(self, tmp_path):
        vmg, vts_dict = _fixture_set_a()
        folder = _write_fixture_folder(str(tmp_path), vmg, vts_dict)

        runner = CliRunner()
        result = runner.invoke(cli_main, ["fingerprint", folder])

        assert result.exit_code == 0
        output = result.output.strip()
        assert output.startswith("dvd1-")
        assert len(output) == 45

    def test_fingerprint_command_invalid_path(self):
        runner = CliRunner()
        result = runner.invoke(cli_main, ["fingerprint", "/no/such/path"])

        assert result.exit_code == 1
        # Error should go to stderr (captured as output in CliRunner with mix_stderr=True default)

    def test_fingerprint_command_no_video_ts(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli_main, ["fingerprint", str(tmp_path)])

        assert result.exit_code == 1
