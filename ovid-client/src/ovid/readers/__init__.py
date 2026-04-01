"""Disc reader API — abstracts reading IFO files from folders, ISOs, and drives.

Public API:
    DiscReader   — abstract base class
    FolderReader — reads from VIDEO_TS directory on disk
    ISOReader    — reads from ISO 9660/UDF image via pycdlib
    DriveReader  — auto-delegates based on path type
    open_reader  — factory: auto-detects source type and returns the right reader
"""

from ovid.readers.base import DiscReader
from ovid.readers.folder import FolderReader
from ovid.readers.iso import ISOReader
from ovid.readers.drive import DriveReader

__all__ = [
    "DiscReader",
    "FolderReader",
    "ISOReader",
    "DriveReader",
    "open_reader",
]


def open_reader(path: str) -> DiscReader:
    """Auto-detect source type and return the appropriate DiscReader.

    - If *path* ends with ``.iso`` (case-insensitive) → ISOReader
    - If *path* is a block device → DriveReader
    - If *path* is a directory → FolderReader
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

    # Directory → FolderReader
    if os.path.isdir(path):
        return FolderReader(path)

    # Fallback: try as ISO image (extensionless or other extension)
    return ISOReader(path)
