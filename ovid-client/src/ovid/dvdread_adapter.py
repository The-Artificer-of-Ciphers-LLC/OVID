"""Native libdvdread adapter for DVD Disc ID."""

from __future__ import annotations

import ctypes
import os
from ctypes.util import find_library


class LibdvdreadError(Exception):
    """Base class for libdvdread adapter failures."""

    code = "libdvdread_error"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)


class LibdvdreadUnavailable(LibdvdreadError):
    """Raised when libdvdread cannot be loaded."""

    code = "libdvdread_unavailable"

    def __init__(self) -> None:
        super().__init__("libdvdread library not found")


class LibdvdreadOpenError(LibdvdreadError):
    """Raised when libdvdread cannot open a DVD source."""

    code = "libdvdread_open_failed"

    def __init__(self, path: str) -> None:
        super().__init__(f"libdvdread could not open DVD source: {path}")


class LibdvdreadDiscIdUnavailable(LibdvdreadError):
    """Raised when libdvdread cannot produce a Disc ID."""

    code = "libdvdread_disc_id_unavailable"

    def __init__(self) -> None:
        super().__init__("libdvdread Disc ID unavailable")


def read_libdvdread_disc_id(path: str) -> str:
    """Return the 16-byte libdvdread Disc ID as 32 lowercase hex characters."""
    library_path = find_library("dvdread")
    if library_path is None:
        raise LibdvdreadUnavailable()

    lib = ctypes.CDLL(library_path)
    lib.DVDOpen.argtypes = [ctypes.c_char_p]
    lib.DVDOpen.restype = ctypes.c_void_p
    lib.DVDDiscID.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ubyte),
    ]
    lib.DVDDiscID.restype = ctypes.c_int
    lib.DVDClose.argtypes = [ctypes.c_void_p]
    lib.DVDClose.restype = None

    dvd = lib.DVDOpen(os.fsencode(path))
    if not dvd:
        raise LibdvdreadOpenError(path)

    disc_id = (ctypes.c_ubyte * 16)()
    try:
        status = lib.DVDDiscID(dvd, disc_id)
        if status != 0:
            raise LibdvdreadDiscIdUnavailable()
        return bytes(disc_id).hex()
    finally:
        lib.DVDClose(dvd)
