"""ISOReader — read IFO files from an ISO 9660/UDF disc image via pycdlib."""

from __future__ import annotations

import io
from typing import List

import pycdlib

from ovid.readers.base import DiscReader


class ISOReader(DiscReader):
    """Read IFO files from an ISO image.

    Tries ISO 9660 paths first (``/VIDEO_TS/FILE.IFO;1``).  If the ISO lacks
    an ISO 9660 directory listing for VIDEO_TS, falls back to UDF paths
    (``/VIDEO_TS/FILE.IFO``).

    Raises:
        ValueError: if the file is not a valid ISO or has no VIDEO_TS directory.
    """

    def __init__(self, path: str) -> None:
        self._iso = pycdlib.PyCdlib()
        try:
            self._iso.open(path)
        except Exception as exc:
            raise ValueError(f"Cannot open ISO image {path!r}: {exc}") from exc

        # Determine which accessor to use (ISO 9660 vs UDF).
        self._use_udf = False
        self._video_ts_prefix_iso = "/VIDEO_TS"
        self._video_ts_prefix_udf = "/VIDEO_TS"

        if not self._has_video_ts_iso9660():
            if not self._has_video_ts_udf():
                self._iso.close()
                raise ValueError(
                    f"No VIDEO_TS directory found in ISO image {path!r}"
                )
            self._use_udf = True

    # ------------------------------------------------------------------
    # DiscReader interface
    # ------------------------------------------------------------------

    def list_ifo_files(self) -> List[str]:
        """Sorted list of ``.IFO`` filenames in the ISO's VIDEO_TS directory."""
        names: list[str] = []
        if self._use_udf:
            for child in self._iso.list_children(udf_path="/VIDEO_TS"):
                name = child.file_identifier().decode("utf-8", errors="replace")
                if name in (".", ".."):
                    continue
                if name.upper().endswith(".IFO"):
                    names.append(name.upper())
        else:
            for child in self._iso.list_children(iso_path="/VIDEO_TS"):
                ident = child.file_identifier().decode("utf-8", errors="replace")
                if ident in (".", "..") or ident == "\x00" or ident == "\x01":
                    continue
                # ISO 9660 names include ";1" version suffix
                base = ident.split(";")[0]
                if base.upper().endswith(".IFO"):
                    names.append(base.upper())
        names.sort()
        return names

    def read_ifo(self, name: str) -> bytes:
        """Read raw bytes of the IFO file *name* from the ISO image.

        Raises:
            FileNotFoundError: if the file is not present in VIDEO_TS.
        """
        buf = io.BytesIO()
        try:
            if self._use_udf:
                udf_path = f"/VIDEO_TS/{name.upper()}"
                self._iso.get_file_from_iso_fp(buf, udf_path=udf_path)
            else:
                iso_path = f"/VIDEO_TS/{name.upper()};1"
                self._iso.get_file_from_iso_fp(buf, iso_path=iso_path)
        except pycdlib.pycdlibexception.PyCdlibInvalidInput as exc:
            raise FileNotFoundError(
                f"IFO file not found in ISO: {name}"
            ) from exc
        return buf.getvalue()

    def close(self) -> None:
        """Close the underlying pycdlib ISO handle."""
        try:
            self._iso.close()
        except Exception:
            pass  # already closed or never fully opened

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _has_video_ts_iso9660(self) -> bool:
        """Check if VIDEO_TS exists as an ISO 9660 directory."""
        try:
            list(self._iso.list_children(iso_path="/VIDEO_TS"))
            return True
        except pycdlib.pycdlibexception.PyCdlibInvalidInput:
            return False

    def _has_video_ts_udf(self) -> bool:
        """Check if VIDEO_TS exists as a UDF directory."""
        try:
            list(self._iso.list_children(udf_path="/VIDEO_TS"))
            return True
        except (pycdlib.pycdlibexception.PyCdlibInvalidInput, AttributeError):
            return False
