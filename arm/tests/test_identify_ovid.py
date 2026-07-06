"""Tests for arm.identify_ovid — fingerprint_disc_with_identity() and
submit_to_ovid()'s conditional fingerprint_aliases payload key.

Closes the genuine IDENT-03 gap: ARM's auto-register path must carry every
known Disc Identity string for the physical disc it just fingerprinted, not
just the bare primary (see RESEARCH.md Pitfall 1).
"""

from __future__ import annotations

import requests as requests_module

from arm import identify_ovid
from ovid.bd_disc import BDDisc
from ovid.disc import Disc
from ovid.disc_identity import DiscIdentity, DiscIdentitySet


def _identity(fingerprint: str, method: str, version: str) -> DiscIdentity:
    return DiscIdentity(fingerprint=fingerprint, method=method, fingerprint_version=version)


class _FakeDisc:
    """Lightweight stand-in for Disc/BDDisc exposing .fingerprint/._identity_set
    without parsing a real disc path."""

    def __init__(self, fingerprint: str, identity_set: DiscIdentitySet | None = None):
        self.fingerprint = fingerprint
        self._identity_set = identity_set


# ---------------------------------------------------------------------------
# fingerprint_disc_with_identity()
# ---------------------------------------------------------------------------


class TestFingerprintDiscWithIdentity:
    def test_returns_primary_and_aliases_when_identity_set_has_aliases(self):
        alias = _identity("dvd1-aaa", "ovid-dvd-1", "dvd1")
        primary = _identity("dvdread1-bbb", "libdvdread-disc-id", "dvdread1")
        identity_set = DiscIdentitySet(primary=primary, aliases=[alias])
        fake = _FakeDisc("dvdread1-bbb", identity_set=identity_set)

        original_from_path = Disc.from_path
        Disc.from_path = staticmethod(lambda path: fake)
        try:
            fingerprint, aliases = identify_ovid.fingerprint_disc_with_identity(
                "/mnt/dev/sr0"
            )
        finally:
            Disc.from_path = original_from_path

        assert fingerprint == "dvdread1-bbb"
        assert aliases == ["dvd1-aaa"]

    def test_returns_empty_aliases_when_identity_set_is_none(self):
        fake = _FakeDisc("dvd1-ccc", identity_set=None)

        original_from_path = Disc.from_path
        Disc.from_path = staticmethod(lambda path: fake)
        try:
            fingerprint, aliases = identify_ovid.fingerprint_disc_with_identity(
                "/mnt/dev/sr0"
            )
        finally:
            Disc.from_path = original_from_path

        assert fingerprint == "dvd1-ccc"
        assert aliases == []

    def test_returns_empty_aliases_when_identity_set_has_empty_aliases(self):
        primary = _identity("dvd1-ddd", "ovid-dvd-1", "dvd1")
        identity_set = DiscIdentitySet(primary=primary, aliases=[])
        fake = _FakeDisc("dvd1-ddd", identity_set=identity_set)

        original_from_path = Disc.from_path
        Disc.from_path = staticmethod(lambda path: fake)
        try:
            fingerprint, aliases = identify_ovid.fingerprint_disc_with_identity(
                "/mnt/dev/sr0"
            )
        finally:
            Disc.from_path = original_from_path

        assert fingerprint == "dvd1-ddd"
        assert aliases == []

    def test_bd_path_routes_through_bddisc_from_path(self, tmp_path):
        bd_root = tmp_path / "disc"
        (bd_root / "BDMV").mkdir(parents=True)

        alias = _identity("bd1-aacs-aaa", "aacs-disc-id", "bd1")
        primary = _identity("bd2-bbb", "ovid-bd-2", "bd2")
        identity_set = DiscIdentitySet(primary=primary, aliases=[alias])
        fake = _FakeDisc("bd2-bbb", identity_set=identity_set)

        original_from_path = BDDisc.from_path
        BDDisc.from_path = staticmethod(lambda path: fake)
        try:
            fingerprint, aliases = identify_ovid.fingerprint_disc_with_identity(
                str(bd_root)
            )
        finally:
            BDDisc.from_path = original_from_path

        assert fingerprint == "bd2-bbb"
        assert aliases == ["bd1-aacs-aaa"]

    def test_fingerprint_disc_is_a_backward_compatible_thin_wrapper(self):
        fake = _FakeDisc("dvd1-eee", identity_set=None)

        original_from_path = Disc.from_path
        Disc.from_path = staticmethod(lambda path: fake)
        try:
            result = identify_ovid.fingerprint_disc("/mnt/dev/sr0")
        finally:
            Disc.from_path = original_from_path

        assert result == "dvd1-eee"


# ---------------------------------------------------------------------------
# submit_to_ovid() fingerprint_aliases handling
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


def _capture_post(calls: list[dict]):
    def _fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return _FakeResponse(201)

    return _fake_post


class TestSubmitToOvidFingerprintAliases:
    def _post_and_capture(self, monkeypatch, **kwargs) -> list[dict]:
        monkeypatch.setenv("OVID_API_TOKEN", "test-token")
        calls: list[dict] = []
        original_post = requests_module.post
        requests_module.post = _capture_post(calls)
        try:
            identify_ovid.submit_to_ovid(
                fingerprint=kwargs.pop("fingerprint", "dvd1-primary"),
                disc_format=kwargs.pop("disc_format", "dvd"),
                **kwargs,
            )
        finally:
            requests_module.post = original_post
        return calls

    def test_includes_aliases_key_when_present(self, monkeypatch):
        calls = self._post_and_capture(
            monkeypatch, fingerprint_aliases=["dvdread1-x"]
        )
        assert calls[0]["json"]["fingerprint_aliases"] == ["dvdread1-x"]

    def test_omits_aliases_key_when_none(self, monkeypatch):
        calls = self._post_and_capture(monkeypatch, fingerprint_aliases=None)
        assert "fingerprint_aliases" not in calls[0]["json"]

    def test_omits_aliases_key_when_empty_list(self, monkeypatch):
        calls = self._post_and_capture(monkeypatch, fingerprint_aliases=[])
        assert "fingerprint_aliases" not in calls[0]["json"]

    def test_default_call_without_aliases_arg_is_unchanged(self, monkeypatch):
        """Proves backward compatibility: existing callers that never pass
        fingerprint_aliases at all keep getting the pre-existing payload
        shape with no such key."""
        calls = self._post_and_capture(monkeypatch, disc_label="My Movie")
        assert "fingerprint_aliases" not in calls[0]["json"]
        assert calls[0]["json"]["fingerprint"] == "dvd1-primary"
        assert calls[0]["json"]["format"] == "dvd"
        assert calls[0]["json"]["disc_label"] == "My Movie"
