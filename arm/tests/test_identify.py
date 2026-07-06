"""Tests for arm.identify — threading Disc Identity aliases from the
miss-fallback fingerprint through to the OVID auto-register call
(IDENT-03), while preserving ARM's never-raise contract.
"""

from __future__ import annotations

import types

from arm import identify


def _fake_job(**overrides):
    defaults = dict(
        mountpoint="/mnt/dev/sr0",
        devpath="",
        disctype="dvd",
        label="MY_MOVIE",
        title=None,
        year=None,
        video_type=None,
        hasnicetitle=False,
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _patch(module, name, value):
    """Save the current attribute value and override it. Returns the
    original value so the caller can restore it in a `finally` block."""
    original = getattr(module, name)
    setattr(module, name, value)
    return original


def _restore(module, name, original):
    setattr(module, name, original)


class TestIdentifyThreadsFingerprintAliases:
    def test_miss_threads_aliases_into_submit_to_ovid(self, monkeypatch):
        """A miss (lookup_ovid returns None) with fingerprint_disc_with_identity
        mocked to return ("dvd1-x", ["dvdread1-y"]) must result in
        submit_to_ovid receiving fingerprint="dvd1-x",
        fingerprint_aliases=["dvdread1-y"]."""
        monkeypatch.delenv("OVID_ENABLED", raising=False)

        submit_calls: list[dict] = []

        def _fake_lookup(disc_path, api_url=""):
            return None

        def _fake_fp_with_identity(disc_path):
            return "dvd1-x", ["dvdread1-y"]

        def _fake_submit(**kwargs):
            submit_calls.append(kwargs)
            return True

        orig_lookup = _patch(identify, "lookup_ovid", _fake_lookup)
        orig_fp = _patch(
            identify, "fingerprint_disc_with_identity", _fake_fp_with_identity
        )
        orig_submit = _patch(identify, "submit_to_ovid", _fake_submit)
        orig_ensure_mounted = _patch(identify, "_ensure_mounted", lambda job: True)
        orig_load_original = _patch(
            identify,
            "_load_original",
            lambda: types.SimpleNamespace(identify=lambda job: job),
        )
        try:
            job = _fake_job()
            result = identify.identify(job)
        finally:
            _restore(identify, "lookup_ovid", orig_lookup)
            _restore(identify, "fingerprint_disc_with_identity", orig_fp)
            _restore(identify, "submit_to_ovid", orig_submit)
            _restore(identify, "_ensure_mounted", orig_ensure_mounted)
            _restore(identify, "_load_original", orig_load_original)

        assert result is job
        assert len(submit_calls) == 1
        assert submit_calls[0]["fingerprint"] == "dvd1-x"
        assert submit_calls[0]["fingerprint_aliases"] == ["dvdread1-y"]

    def test_fingerprint_disc_with_identity_raising_never_raises_and_skips_registration(
        self, monkeypatch
    ):
        """If fingerprint_disc_with_identity raises, identify() must still
        complete without raising, and — because the resulting fingerprint is
        None — the registration call is skipped entirely (unchanged
        pre-existing `if ovid_enabled and ovid_fingerprint and
        submit_to_ovid is not None` guard behavior)."""
        monkeypatch.delenv("OVID_ENABLED", raising=False)

        submit_calls: list[dict] = []

        def _fake_lookup(disc_path, api_url=""):
            return None

        def _raising_fp_with_identity(disc_path):
            raise RuntimeError("boom")

        def _fake_submit(**kwargs):
            submit_calls.append(kwargs)
            return True

        orig_lookup = _patch(identify, "lookup_ovid", _fake_lookup)
        orig_fp = _patch(
            identify, "fingerprint_disc_with_identity", _raising_fp_with_identity
        )
        orig_submit = _patch(identify, "submit_to_ovid", _fake_submit)
        orig_ensure_mounted = _patch(identify, "_ensure_mounted", lambda job: True)
        orig_load_original = _patch(
            identify,
            "_load_original",
            lambda: types.SimpleNamespace(identify=lambda job: job),
        )
        try:
            job = _fake_job()
            result = identify.identify(job)  # must not raise
        finally:
            _restore(identify, "lookup_ovid", orig_lookup)
            _restore(identify, "fingerprint_disc_with_identity", orig_fp)
            _restore(identify, "submit_to_ovid", orig_submit)
            _restore(identify, "_ensure_mounted", orig_ensure_mounted)
            _restore(identify, "_load_original", orig_load_original)

        assert result is job
        assert submit_calls == []

    def test_ovid_disabled_never_calls_submit_to_ovid(self, monkeypatch):
        """OVID_ENABLED=false must skip the entire OVID block — submit_to_ovid
        is never called (unchanged pre-existing regression guard)."""
        monkeypatch.setenv("OVID_ENABLED", "false")

        lookup_calls: list[str] = []
        submit_calls: list[dict] = []

        def _fake_lookup(disc_path, api_url=""):
            lookup_calls.append(disc_path)
            return None

        def _fake_fp_with_identity(disc_path):
            return "dvd1-x", ["dvdread1-y"]

        def _fake_submit(**kwargs):
            submit_calls.append(kwargs)
            return True

        orig_lookup = _patch(identify, "lookup_ovid", _fake_lookup)
        orig_fp = _patch(
            identify, "fingerprint_disc_with_identity", _fake_fp_with_identity
        )
        orig_submit = _patch(identify, "submit_to_ovid", _fake_submit)
        orig_ensure_mounted = _patch(identify, "_ensure_mounted", lambda job: True)
        orig_load_original = _patch(
            identify,
            "_load_original",
            lambda: types.SimpleNamespace(identify=lambda job: job),
        )
        try:
            job = _fake_job()
            result = identify.identify(job)
        finally:
            _restore(identify, "lookup_ovid", orig_lookup)
            _restore(identify, "fingerprint_disc_with_identity", orig_fp)
            _restore(identify, "submit_to_ovid", orig_submit)
            _restore(identify, "_ensure_mounted", orig_ensure_mounted)
            _restore(identify, "_load_original", orig_load_original)

        assert result is job
        assert lookup_calls == []
        assert submit_calls == []
