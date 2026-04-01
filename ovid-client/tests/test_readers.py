"""Tests for disc readers: FolderReader, ISOReader, DriveReader, and open_reader factory.

Proves R002: FolderReader and ISOReader on the same fixture data return identical
IFO bytes for every file (cross-source identity).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pycdlib
import pytest

from conftest import make_vmg_ifo, make_vts_ifo, encode_bcd_time
from ovid.readers import FolderReader, ISOReader, DriveReader, open_reader


# ---------------------------------------------------------------------------
# Fixture: a temp VIDEO_TS folder with synthetic IFO files
# ---------------------------------------------------------------------------

@pytest.fixture()
def video_ts_folder(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    """Create a temp directory with VIDEO_TS/ containing synthetic IFO files.

    Returns (root_dir, {filename: raw_bytes}) so tests can verify round-trip.
    """
    vts_dir = tmp_path / "VIDEO_TS"
    vts_dir.mkdir()

    files: dict[str, bytes] = {}

    # VMG
    vmg_data = make_vmg_ifo(vts_count=2, title_entries=3)
    files["VIDEO_TS.IFO"] = vmg_data

    # VTS 01
    vts1_data = make_vts_ifo(
        pgcs=[(1, 30, 0, 12)],
        audio_streams=[(0, "en", 6)],
        subtitle_streams=["en", "fr"],
    )
    files["VTS_01_0.IFO"] = vts1_data

    # VTS 02
    vts2_data = make_vts_ifo(
        pgcs=[(0, 45, 30, 8), (0, 5, 0, 1)],
        audio_streams=[(0, "en", 2), (6, "de", 6)],
        subtitle_streams=["en"],
    )
    files["VTS_02_0.IFO"] = vts2_data

    for name, data in files.items():
        (vts_dir / name).write_bytes(data)

    return tmp_path, files


@pytest.fixture()
def iso_from_folder(video_ts_folder: tuple[Path, dict[str, bytes]]) -> tuple[Path, dict[str, bytes]]:
    """Build an ISO image from the same fixture files using pycdlib.

    Returns (iso_path, {filename: raw_bytes}).
    """
    root_dir, files = video_ts_folder
    iso_path = root_dir / "test_disc.iso"

    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=1)
    iso.add_directory(iso_path="/VIDEO_TS")

    for name, data in sorted(files.items()):
        iso_full = f"/VIDEO_TS/{name};1"
        iso.add_fp(
            fp=__import__("io").BytesIO(data),
            length=len(data),
            iso_path=iso_full,
        )

    iso.write(str(iso_path))
    iso.close()

    return iso_path, files


# ===================================================================
# FolderReader tests
# ===================================================================

class TestFolderReader:
    """FolderReader: reads IFO files from a VIDEO_TS directory."""

    def test_list_ifo_files_sorted(self, video_ts_folder):
        root, files = video_ts_folder
        with FolderReader(str(root)) as reader:
            names = reader.list_ifo_files()
        assert names == sorted(files.keys())

    def test_read_ifo_returns_exact_bytes(self, video_ts_folder):
        root, files = video_ts_folder
        with FolderReader(str(root)) as reader:
            for name, expected in files.items():
                assert reader.read_ifo(name) == expected

    def test_accepts_video_ts_dir_directly(self, video_ts_folder):
        root, _ = video_ts_folder
        vts_dir = root / "VIDEO_TS"
        with FolderReader(str(vts_dir)) as reader:
            assert len(reader.list_ifo_files()) > 0

    def test_case_insensitive_detection(self, tmp_path):
        """VIDEO_TS directory found even when named 'video_ts'."""
        vts = tmp_path / "video_ts"
        vts.mkdir()
        (vts / "VIDEO_TS.IFO").write_bytes(make_vmg_ifo(1, 1))
        with FolderReader(str(tmp_path)) as reader:
            assert "VIDEO_TS.IFO" in reader.list_ifo_files()

    def test_empty_video_ts(self, tmp_path):
        """Empty VIDEO_TS directory → empty list, no crash."""
        (tmp_path / "VIDEO_TS").mkdir()
        with FolderReader(str(tmp_path)) as reader:
            assert reader.list_ifo_files() == []

    def test_missing_video_ts_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No VIDEO_TS"):
            FolderReader(str(tmp_path))

    def test_not_a_directory_raises(self, tmp_path):
        f = tmp_path / "somefile.txt"
        f.write_text("nope")
        with pytest.raises(FileNotFoundError, match="not a directory"):
            FolderReader(str(f))

    def test_read_missing_ifo_raises(self, video_ts_folder):
        root, _ = video_ts_folder
        with FolderReader(str(root)) as reader:
            with pytest.raises(FileNotFoundError):
                reader.read_ifo("NONEXISTENT.IFO")


# ===================================================================
# ISOReader tests
# ===================================================================

class TestISOReader:
    """ISOReader: reads IFO files from an ISO image via pycdlib."""

    def test_list_ifo_files_sorted(self, iso_from_folder):
        iso_path, files = iso_from_folder
        with ISOReader(str(iso_path)) as reader:
            names = reader.list_ifo_files()
        assert names == sorted(files.keys())

    def test_read_ifo_returns_exact_bytes(self, iso_from_folder):
        iso_path, files = iso_from_folder
        with ISOReader(str(iso_path)) as reader:
            for name, expected in files.items():
                actual = reader.read_ifo(name)
                assert actual == expected, f"Mismatch for {name}: {len(actual)} vs {len(expected)} bytes"

    def test_read_missing_ifo_raises(self, iso_from_folder):
        iso_path, _ = iso_from_folder
        with ISOReader(str(iso_path)) as reader:
            with pytest.raises(FileNotFoundError):
                reader.read_ifo("NONEXISTENT.IFO")

    def test_non_iso_file_raises(self, tmp_path):
        """Opening a non-ISO file raises ValueError."""
        bad = tmp_path / "not_an_iso.iso"
        bad.write_text("this is not an iso")
        with pytest.raises(ValueError, match="Cannot open ISO"):
            ISOReader(str(bad))

    def test_iso_without_video_ts_raises(self, tmp_path):
        """ISO with no VIDEO_TS directory raises ValueError."""
        iso_path = tmp_path / "empty.iso"
        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=1)
        iso.write(str(iso_path))
        iso.close()
        with pytest.raises(ValueError, match="No VIDEO_TS"):
            ISOReader(str(iso_path))


# ===================================================================
# Cross-source identity test (R002)
# ===================================================================

class TestCrossSourceIdentity:
    """FolderReader and ISOReader on the same data return identical bytes."""

    def test_folder_and_iso_produce_identical_bytes(self, video_ts_folder, iso_from_folder):
        root, files = video_ts_folder
        iso_path, _ = iso_from_folder

        with FolderReader(str(root)) as folder_rdr, ISOReader(str(iso_path)) as iso_rdr:
            folder_names = folder_rdr.list_ifo_files()
            iso_names = iso_rdr.list_ifo_files()
            assert folder_names == iso_names, "File lists differ between folder and ISO"

            for name in folder_names:
                folder_bytes = folder_rdr.read_ifo(name)
                iso_bytes = iso_rdr.read_ifo(name)
                assert folder_bytes == iso_bytes, (
                    f"Cross-source mismatch for {name}: "
                    f"folder={len(folder_bytes)}B vs iso={len(iso_bytes)}B"
                )


# ===================================================================
# Auto-detection factory (open_reader)
# ===================================================================

class TestOpenReader:
    """open_reader() picks the correct reader based on path type."""

    def test_directory_returns_folder_reader(self, video_ts_folder):
        root, _ = video_ts_folder
        reader = open_reader(str(root))
        try:
            assert isinstance(reader, FolderReader)
        finally:
            reader.close()

    def test_iso_file_returns_iso_reader(self, iso_from_folder):
        iso_path, _ = iso_from_folder
        reader = open_reader(str(iso_path))
        try:
            assert isinstance(reader, ISOReader)
        finally:
            reader.close()

    def test_factory_reader_returns_valid_data(self, iso_from_folder):
        iso_path, files = iso_from_folder
        with open_reader(str(iso_path)) as reader:
            assert reader.list_ifo_files() == sorted(files.keys())


# ===================================================================
# DriveReader tests
# ===================================================================

class TestDriveReader:
    """DriveReader delegates to FolderReader for directories."""

    def test_directory_delegates_to_folder(self, video_ts_folder):
        root, files = video_ts_folder
        with DriveReader(str(root)) as reader:
            names = reader.list_ifo_files()
            assert names == sorted(files.keys())
            # Verify bytes match
            for name, expected in files.items():
                assert reader.read_ifo(name) == expected

    def test_nonexistent_path_raises(self):
        with pytest.raises(FileNotFoundError):
            DriveReader("/nonexistent/path/to/drive")
