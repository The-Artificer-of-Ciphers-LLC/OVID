"""Disc reader API — abstracts reading IFO/MPLS files from folders, ISOs, and drives.

Public API:
    DiscReader     — abstract base class
    FolderReader   — reads from VIDEO_TS directory on disk (DVD)
    BDFolderReader — reads from BDMV directory on disk (Blu-ray / UHD)
    ISOReader      — reads from ISO 9660/UDF image via pycdlib
    DriveReader    — auto-delegates based on path type
    open_reader    — factory: auto-detects source type and returns the right reader
"""

import logging

from ovid.readers.base import DiscReader
from ovid.readers.folder import FolderReader
from ovid.readers.bd_folder import BDFolderReader
from ovid.readers.iso import ISOReader
from ovid.readers.drive import DriveReader

logger = logging.getLogger(__name__)

__all__ = [
    "DiscReader",
    "FolderReader",
    "BDFolderReader",
    "ISOReader",
    "DriveReader",
    "open_reader",
]


def _has_bdmv(path: str) -> bool:
    """Check if a directory contains a BDMV subdirectory (case-insensitive)."""
    import os

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


def _has_video_ts(path: str) -> bool:
    """Check if a directory contains a VIDEO_TS subdirectory (case-insensitive)."""
    import os

    basename = os.path.basename(os.path.normpath(path))
    if basename.upper() == "VIDEO_TS":
        return True

    try:
        for entry in os.listdir(path):
            if entry.upper() == "VIDEO_TS" and os.path.isdir(
                os.path.join(path, entry)
            ):
                return True
    except OSError:
        pass
    return False


def open_reader(path: str) -> DiscReader:
    """Auto-detect source type and return the appropriate DiscReader.

    Detection order for directories:
    - If *path* contains a BDMV subdirectory → BDFolderReader (Blu-ray / UHD)
    - If *path* contains a VIDEO_TS subdirectory → FolderReader (DVD)

    Other paths:
    - If *path* ends with ``.iso`` (case-insensitive) → ISOReader
    - If *path* is a block device → DriveReader
    - Otherwise → attempt ISOReader (covers extensionless ISO images)

    The caller is responsible for closing the returned reader (or using it as
    a context manager).
    """
    import os
    import stat

    # Block device → DriveReader
    try:
        st = os.stat(path)
        if stat.S_ISBLK(st.st_mode):
            return DriveReader(path)
    except OSError:
        pass

    # Explicit .iso extension
    if path.lower().endswith(".iso"):
        return ISOReader(path)

    # Directory → check for BDMV first (BD takes priority), then VIDEO_TS
    if os.path.isdir(path):
        if _has_bdmv(path):
            logger.info("Detected BDMV directory at %s — using BDFolderReader", path)
            return BDFolderReader(path)
        if _has_video_ts(path):
            logger.info("Detected VIDEO_TS directory at %s — using FolderReader", path)
            return FolderReader(path)
        # Neither found — try FolderReader which will raise a clear error
        return FolderReader(path)

    # Fallback: try as ISO image (extensionless or other extension)
    return ISOReader(path)
