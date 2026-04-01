"""Tests for ovid.fingerprint — canonical string builder and hash computation."""

from __future__ import annotations

import hashlib

from ovid.fingerprint import build_canonical_string, compute_fingerprint
from ovid.ifo_parser import (
    AudioStream,
    PGCInfo,
    SubtitleStream,
    VMGInfo,
    VTSInfo,
)


# ---------------------------------------------------------------------------
# Canonical string builder
# ---------------------------------------------------------------------------


class TestBuildCanonicalString:
    """Verify the canonical string exactly matches spec §2.1 format."""

    def test_single_vts_single_pgc(self):
        vmg = VMGInfo(vts_count=1, title_count=1)
        vts = VTSInfo(
            pgc_list=[PGCInfo(duration_seconds=7287, chapter_count=28)],
            audio_streams=[
                AudioStream(codec="AC3", language="en", channels=6),
                AudioStream(codec="AC3", language="fr", channels=6),
                AudioStream(codec="AC3", language="es", channels=6),
            ],
            subtitle_streams=[
                SubtitleStream(language="en"),
                SubtitleStream(language="fr"),
                SubtitleStream(language="es"),
                SubtitleStream(language="pt"),
            ],
        )
        result = build_canonical_string(vmg, [vts])
        assert result == "OVID-DVD-1|1|1|1:7287:28:en,fr,es:en,fr,es,pt"

    def test_multiple_vts_multiple_pgcs(self):
        """Matches structure of spec example (simplified)."""
        vmg = VMGInfo(vts_count=2, title_count=3)
        vts1 = VTSInfo(
            pgc_list=[PGCInfo(duration_seconds=104, chapter_count=3)],
            audio_streams=[AudioStream(codec="AC3", language="en", channels=2)],
            subtitle_streams=[SubtitleStream(language="en")],
        )
        vts2 = VTSInfo(
            pgc_list=[
                PGCInfo(duration_seconds=134, chapter_count=5),
                PGCInfo(duration_seconds=134, chapter_count=4),
            ],
            audio_streams=[
                AudioStream(codec="AC3", language="en", channels=6),
                AudioStream(codec="AC3", language="fr", channels=6),
            ],
            subtitle_streams=[
                SubtitleStream(language="en"),
                SubtitleStream(language="fr"),
            ],
        )
        result = build_canonical_string(vmg, [vts1, vts2])
        assert result == (
            "OVID-DVD-1|2|3|"
            "1:104:3:en:en|"
            "2:134:5:en,fr:en,fr,134:4:en,fr:en,fr"
        )

    def test_no_audio_no_subs(self):
        """VTS with zero audio/subtitle streams → empty strings, no crash."""
        vmg = VMGInfo(vts_count=1, title_count=1)
        vts = VTSInfo(
            pgc_list=[PGCInfo(duration_seconds=60, chapter_count=1)],
            audio_streams=[],
            subtitle_streams=[],
        )
        result = build_canonical_string(vmg, [vts])
        assert result == "OVID-DVD-1|1|1|1:60:1::"

    def test_no_pgcs(self):
        """VTS with zero PGCs → just the count."""
        vmg = VMGInfo(vts_count=1, title_count=0)
        vts = VTSInfo(pgc_list=[], audio_streams=[], subtitle_streams=[])
        result = build_canonical_string(vmg, [vts])
        assert result == "OVID-DVD-1|1|0|0"

    def test_codec_not_in_canonical_string(self):
        """Codec is parsed on AudioStream but NOT included in canonical string."""
        vmg = VMGInfo(vts_count=1, title_count=1)
        vts = VTSInfo(
            pgc_list=[PGCInfo(duration_seconds=100, chapter_count=2)],
            audio_streams=[
                AudioStream(codec="AC3", language="en", channels=6),
                AudioStream(codec="DTS", language="fr", channels=6),
            ],
            subtitle_streams=[],
        )
        result = build_canonical_string(vmg, [vts])
        # Languages only — no codec identifiers in the string
        assert "AC3" not in result
        assert "DTS" not in result
        assert ":en,fr:" in result


# ---------------------------------------------------------------------------
# Fingerprint computation
# ---------------------------------------------------------------------------


class TestComputeFingerprint:
    """Verify SHA-256 → first 40 hex → dvd1- prefix."""

    def test_known_hash(self):
        canonical = "OVID-DVD-1|1|1|1:7287:28:en,fr,es:en,fr,es,pt"
        expected_hex = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:40]
        result = compute_fingerprint(canonical)
        assert result == f"dvd1-{expected_hex}"

    def test_prefix_format(self):
        result = compute_fingerprint("anything")
        assert result.startswith("dvd1-")
        # dvd1- (5 chars) + 40 hex chars = 45 total
        assert len(result) == 45

    def test_determinism(self):
        """Same input always produces the same fingerprint."""
        canonical = "OVID-DVD-1|2|5|1:120:3:en:en"
        results = {compute_fingerprint(canonical) for _ in range(100)}
        assert len(results) == 1
