"""FolderReader — read IFO files from a VIDEO_TS directory on the filesystem."""

from __future__ import annotations

import os
from typing import List

from ovid.readers.base import DiscReader


class FolderReader(DiscReader):
    """Read IFO files from a VIDEO_TS folder (or its parent directory).

    Accepts either the VIDEO_TS directory itself or a parent that contains it.
    The lookup is case-insensitive so ``video_ts`` on a case-preserving FS works.

    Raises:
        FileNotFoundError: if no VIDEO_TS directory can be located.
    """

    def __init__(self, path: str) -> None:
        self._video_ts = self._find_video_ts(path)

    # ------------------------------------------------------------------
    # DiscReader interface
    # ------------------------------------------------------------------

    def list_ifo_files(self) -> List[str]:
        """Sorted list of ``.IFO`` filenames in VIDEO_TS."""
        entries = []
        for entry in os.listdir(self._video_ts):
            if entry.upper().endswith(".IFO"):
                entries.append(entry.upper())  # normalise to uppercase
        entries.sort()
        return entries

    def read_ifo(self, name: str) -> bytes:
        """Read raw bytes of *name* from the VIDEO_TS directory.

        Performs a case-insensitive match so ``VIDEO_TS.IFO`` finds
        ``video_ts.ifo`` on case-preserving filesystems.

        Raises:
            FileNotFoundError: if the IFO file does not exist.
        """
        # Case-insensitive lookup
        target = name.upper()
        for entry in os.listdir(self._video_ts):
            if entry.upper() == target:
                full = os.path.join(self._video_ts, entry)
                with open(full, "rb") as fh:
                    return fh.read()
        raise FileNotFoundError(f"IFO file not found: {name} in {self._video_ts}")

    def close(self) -> None:
        """No resources to release for folder access."""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _find_video_ts(path: str) -> str:
        """Locate the VIDEO_TS directory starting from *path*.

        If *path* itself is named VIDEO_TS (case-insensitive), return it.
        Otherwise look for a VIDEO_TS child directory.

        Raises:
            FileNotFoundError: if VIDEO_TS cannot be found.
        """
        if not os.path.isdir(path):
            raise FileNotFoundError(f"Path is not a directory: {path}")

        # Check if path itself is VIDEO_TS
        basename = os.path.basename(os.path.normpath(path))
        if basename.upper() == "VIDEO_TS":
            return path

        # Look for a VIDEO_TS child (case-insensitive)
        for entry in os.listdir(path):
            if entry.upper() == "VIDEO_TS" and os.path.isdir(
                os.path.join(path, entry)
            ):
                return os.path.join(path, entry)

        raise FileNotFoundError(
            f"No VIDEO_TS directory found in {path}"
        )
