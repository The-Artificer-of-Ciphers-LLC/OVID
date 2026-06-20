"""Tests for the native libdvdread adapter."""

from __future__ import annotations

import ctypes

import pytest

from ovid import dvdread_adapter
from ovid.dvdread_adapter import (
    LibdvdreadDiscIdUnavailable,
    LibdvdreadUnavailable,
    read_libdvdread_disc_id,
)


class _FakeFunc:
    def __init__(self, func):
        self._func = func
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self._func(*args)


class _FakeLibdvdread:
    def __init__(self, *, disc_id_status: int = 0):
        self.closed = False
        self.disc_id_status = disc_id_status
        self.DVDOpen = _FakeFunc(lambda path: ctypes.c_void_p(1))
        self.DVDClose = _FakeFunc(self._close)
        self.DVDDiscID = _FakeFunc(self._disc_id)

    def _close(self, dvd) -> None:
        self.closed = True

    def _disc_id(self, dvd, buffer) -> int:
        for index in range(16):
            buffer[index] = index
        return self.disc_id_status


def test_read_libdvdread_disc_id_raises_when_library_missing(monkeypatch) -> None:
    monkeypatch.setattr(dvdread_adapter, "find_library", lambda name: None)

    with pytest.raises(LibdvdreadUnavailable) as exc_info:
        read_libdvdread_disc_id("/disc/path")

    assert exc_info.value.code == "libdvdread_unavailable"


def test_read_libdvdread_disc_id_returns_32_hex_chars(monkeypatch) -> None:
    fake_lib = _FakeLibdvdread()
    monkeypatch.setattr(dvdread_adapter, "find_library", lambda name: "libdvdread")
    monkeypatch.setattr(dvdread_adapter.ctypes, "CDLL", lambda path: fake_lib)

    disc_id = read_libdvdread_disc_id("/disc/path")

    assert disc_id == "000102030405060708090a0b0c0d0e0f"
    assert fake_lib.closed is True


def test_read_libdvdread_disc_id_closes_on_disc_id_failure(monkeypatch) -> None:
    fake_lib = _FakeLibdvdread(disc_id_status=1)
    monkeypatch.setattr(dvdread_adapter, "find_library", lambda name: "libdvdread")
    monkeypatch.setattr(dvdread_adapter.ctypes, "CDLL", lambda path: fake_lib)

    with pytest.raises(LibdvdreadDiscIdUnavailable) as exc_info:
        read_libdvdread_disc_id("/disc/path")

    assert exc_info.value.code == "libdvdread_disc_id_unavailable"
    assert fake_lib.closed is True
