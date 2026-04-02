"""CLI tests for the ``ovid lookup`` command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from ovid.cli import main

# OVIDClient is imported locally inside the lookup command as
# ``from ovid.client import OVIDClient``, so we patch it at the
# canonical module path.
PATCH_CLIENT = "ovid.client.OVIDClient"


SAMPLE_LOOKUP = {
    "request_id": "abc-123",
    "fingerprint": "sha256:deadbeef",
    "format": "DVD",
    "status": "verified",
    "confidence": "high",
    "edition_name": "Special Edition",
    "disc_number": 1,
    "total_discs": 2,
    "release": {
        "title": "The Matrix",
        "year": 1999,
        "content_type": "movie",
    },
    "titles": [
        {
            "title_index": 1,
            "is_main_feature": True,
            "title_type": "feature",
            "display_name": "Main Feature",
            "duration_secs": 8160,
            "chapter_count": 34,
            "audio_tracks": [
                {"index": 0, "language": "en", "codec": "ac3", "channels": 6},
            ],
            "subtitle_tracks": [
                {"index": 0, "language": "en"},
            ],
        },
    ],
}


class TestLookupCommand:
    @patch(PATCH_CLIENT)
    def test_found(self, MockClient: MagicMock) -> None:
        instance = MockClient.return_value
        instance.lookup.return_value = SAMPLE_LOOKUP

        runner = CliRunner()
        result = runner.invoke(main, ["lookup", "sha256:deadbeef"])

        assert result.exit_code == 0
        assert "The Matrix" in result.output
        assert "1999" in result.output
        assert "high" in result.output
        assert "Special Edition" in result.output

    @patch(PATCH_CLIENT)
    def test_not_found(self, MockClient: MagicMock) -> None:
        instance = MockClient.return_value
        instance.lookup.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["lookup", "sha256:missing"])

        assert result.exit_code == 1
        # stderr goes to output when not separated
        assert "No disc found" in result.output

    @patch(PATCH_CLIENT)
    def test_api_url_and_token_passed(self, MockClient: MagicMock) -> None:
        instance = MockClient.return_value
        instance.lookup.return_value = SAMPLE_LOOKUP

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["lookup", "sha256:x", "--api-url", "https://custom.api", "--token", "tok123"],
        )

        assert result.exit_code == 0
        MockClient.assert_called_once_with(base_url="https://custom.api", token="tok123")

    @patch(PATCH_CLIENT)
    def test_title_duration_formatting(self, MockClient: MagicMock) -> None:
        """Duration of 8160s should render as 2:16:00."""
        instance = MockClient.return_value
        instance.lookup.return_value = SAMPLE_LOOKUP

        runner = CliRunner()
        result = runner.invoke(main, ["lookup", "sha256:deadbeef"])

        assert result.exit_code == 0
        assert "2:16:00" in result.output

    @patch(PATCH_CLIENT)
    def test_no_titles(self, MockClient: MagicMock) -> None:
        """Response with empty titles list should still render cleanly."""
        data = {**SAMPLE_LOOKUP, "titles": []}
        instance = MockClient.return_value
        instance.lookup.return_value = data

        runner = CliRunner()
        result = runner.invoke(main, ["lookup", "sha256:deadbeef"])

        assert result.exit_code == 0
        assert "No title information available" in result.output
