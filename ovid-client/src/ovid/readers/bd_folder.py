"""BDFolderReader — read MPLS playlist and AACS files from a BDMV directory."""

from __future__ import annotations

import logging
import os
from typing import List

from ovid.readers.base import DiscReader

logger = logging.getLogger(__name__)


class BDFolderReader(DiscReader):
    """Read MPLS and AACS files from a Blu-ray disc folder structure.

    Expects either a directory containing a BDMV subdirectory, or the BDMV
    directory itself.  Lookup is case-insensitive.

    The BDMV directory must contain a PLAYLIST subdirectory with .mpls files.
    An optional AACS sibling directory may contain Unit_Key_RO.inf and other
    AACS metadata.

    Raises:
        FileNotFoundError: if no BDMV directory can be located.
    """

    def __init__(self, path: str) -> None:
        self._root, self._bdmv = self._find_bdmv(path)
        self._playlist_dir = self._find_subdir(self._bdmv, "PLAYLIST")
        # AACS directory is optional — sibling of BDMV
        self._aacs_dir = self._find_aacs(self._root)

    # ------------------------------------------------------------------
    # DiscReader interface (DVD methods — not applicable for BD)
    # ------------------------------------------------------------------

    def list_ifo_files(self) -> List[str]:
        """Not supported for Blu-ray discs.

        Raises:
            NotImplementedError: Always — use BD-specific methods instead.
        """
        raise NotImplementedError(
            "BDFolderReader does not support IFO files. "
            "Use list_mpls_files() for Blu-ray playlists."
        )

    def read_ifo(self, name: str) -> bytes:
        """Not supported for Blu-ray discs.

        Raises:
            NotImplementedError: Always — use BD-specific methods instead.
        """
        raise NotImplementedError(
            "BDFolderReader does not support IFO files. "
            "Use read_mpls() for Blu-ray playlists."
        )

    def close(self) -> None:
        """No resources to release for folder access."""

    # ------------------------------------------------------------------
    # BD-specific methods
    # ------------------------------------------------------------------

    def list_mpls_files(self) -> list[str]:
        """Return sorted list of ``.mpls`` filenames in BDMV/PLAYLIST.

        Returns an empty list if the PLAYLIST directory does not exist.
        Filenames are returned in their original case.
        """
        if self._playlist_dir is None:
            return []

        entries: list[str] = []
        for entry in os.listdir(self._playlist_dir):
            if entry.upper().endswith(".MPLS"):
                entries.append(entry)
        entries.sort()
        return entries

    def read_mpls(self, name: str) -> bytes:
        """Read raw bytes of MPLS file *name* from BDMV/PLAYLIST.

        Case-insensitive lookup.

        Raises:
            FileNotFoundError: if the file does not exist or PLAYLIST dir missing.
        """
        if self._playlist_dir is None:
            raise FileNotFoundError(
                f"No PLAYLIST directory found under BDMV at {self._bdmv}"
            )

        target = name.upper()
        for entry in os.listdir(self._playlist_dir):
            if entry.upper() == target:
                full = os.path.join(self._playlist_dir, entry)
                with open(full, "rb") as fh:
                    return fh.read()

        raise FileNotFoundError(
            f"MPLS file not found: {name} in {self._playlist_dir}"
        )

    def read_aacs_file(self, name: str) -> bytes | None:
        """Read a file from the AACS directory.

        Returns None if the AACS directory does not exist or the file is missing.
        """
        if self._aacs_dir is None:
            return None

        target = name.upper()
        for entry in os.listdir(self._aacs_dir):
            if entry.upper() == target:
                full = os.path.join(self._aacs_dir, entry)
                try:
                    with open(full, "rb") as fh:
                        return fh.read()
                except OSError:
                    logger.warning("Failed to read AACS file: %s", full)
                    return None

        return None

    def has_aacs(self) -> bool:
        """Return True if an AACS directory exists at the disc root."""
        return self._aacs_dir is not None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _find_bdmv(path: str) -> tuple[str, str]:
        """Locate the BDMV directory starting from *path*.

        Returns (root_dir, bdmv_dir) where root_dir is the parent of BDMV.

        Raises:
            FileNotFoundError: if BDMV cannot be found.
        """
        if not os.path.isdir(path):
            raise FileNotFoundError(f"Path is not a directory: {path}")

        # Check if path itself is BDMV
        basename = os.path.basename(os.path.normpath(path))
        if basename.upper() == "BDMV":
            return os.path.dirname(os.path.normpath(path)), path

        # Look for a BDMV child (case-insensitive)
        for entry in os.listdir(path):
            if entry.upper() == "BDMV" and os.path.isdir(
                os.path.join(path, entry)
            ):
                return path, os.path.join(path, entry)

        raise FileNotFoundError(
            f"No BDMV directory found in {path}"
        )

    @staticmethod
    def _find_subdir(parent: str, name: str) -> str | None:
        """Find a subdirectory by name (case-insensitive).  Returns None if missing."""
        target = name.upper()
        for entry in os.listdir(parent):
            if entry.upper() == target and os.path.isdir(
                os.path.join(parent, entry)
            ):
                return os.path.join(parent, entry)
        return None

    @staticmethod
    def _find_aacs(root: str) -> str | None:
        """Find the AACS directory as a sibling of BDMV (case-insensitive)."""
        for entry in os.listdir(root):
            if entry.upper() == "AACS" and os.path.isdir(
                os.path.join(root, entry)
            ):
                return os.path.join(root, entry)
        return None
