"""DriveReader — thin wrapper that delegates to FolderReader or ISOReader based on path type."""

from __future__ import annotations

import os
import stat
import sys
from typing import List

from ovid.readers.base import DiscReader
from ovid.readers.folder import FolderReader
from ovid.readers.iso import ISOReader


class DriveReader(DiscReader):
    """Read IFO files from a physical drive or mounted volume.

    Behaviour:
    - If *path* is a directory (mounted volume), delegates to :class:`FolderReader`.
    - If *path* is a block device, opens it as an ISO via :class:`ISOReader`.

    On macOS ``/dev/diskN`` typically requires the volume to be unmounted first
    (``diskutil unmountDisk /dev/diskN``) or an ISO export.

    Raises:
        PermissionError: if the block device cannot be opened (hint about sudo/unmount).
        FileNotFoundError: if *path* does not exist.
    """

    def __init__(self, path: str) -> None:
        self._delegate: DiscReader

        if os.path.isdir(path):
            self._delegate = FolderReader(path)
            return

        # Check for block device
        try:
            st = os.stat(path)
        except FileNotFoundError:
            raise FileNotFoundError(f"Drive path does not exist: {path}")

        if stat.S_ISBLK(st.st_mode):
            if sys.platform == "darwin":
                import logging
                logging.getLogger("ovid.readers.drive").info(
                    "Opening macOS block device %s — the disc must be unmounted "
                    "(diskutil unmountDisk) or exported as ISO for raw access.",
                    path,
                )
            try:
                self._delegate = ISOReader(path)
            except (ValueError, PermissionError) as exc:
                raise PermissionError(
                    f"Cannot open block device {path!r}. "
                    f"Try: sudo or unmount the disc first. Detail: {exc}"
                ) from exc
        else:
            # Not a directory, not a block device — try as ISO file
            self._delegate = ISOReader(path)

    # ------------------------------------------------------------------
    # DiscReader interface — pure delegation
    # ------------------------------------------------------------------

    def list_ifo_files(self) -> List[str]:
        return self._delegate.list_ifo_files()

    def read_ifo(self, name: str) -> bytes:
        return self._delegate.read_ifo(name)

    def close(self) -> None:
        self._delegate.close()
