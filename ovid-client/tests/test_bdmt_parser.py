"""Unit tests for ovid.bdmt_parser — bdmt XML parsing and BD chapter extraction."""

from __future__ import annotations

from pathlib import Path


from ovid.bdmt_parser import extract_bd_chapters, find_bdmt_file, parse_bdmt


# =========================================================================
# parse_bdmt
# =========================================================================

class TestParseBdmt:
    """parse_bdmt: extract disc title from bdmt_*.xml files."""

    def test_parse_bdmt_valid(self, tmp_path: Path) -> None:
        """Valid XML with namespace and di:name element returns disc title."""
        xml_content = """\
<?xml version="1.0" encoding="UTF-8"?>
<disclib xmlns="urn:BDA:bdmv;discinfo">
  <di:discinfo xmlns:di="urn:BDA:bdmv;discinfo">
    <di:title>
      <di:name>Test Movie</di:name>
    </di:title>
  </di:discinfo>
</disclib>
"""
        bdmt_file = tmp_path / "bdmt_eng.xml"
        bdmt_file.write_text(xml_content)
        result = parse_bdmt(bdmt_file)
        assert result == {"disc_title": "Test Movie"}

    def test_parse_bdmt_no_name(self, tmp_path: Path) -> None:
        """XML without di:name element returns disc_title=None."""
        xml_content = """\
<?xml version="1.0" encoding="UTF-8"?>
<disclib xmlns="urn:BDA:bdmv;discinfo">
  <di:discinfo xmlns:di="urn:BDA:bdmv;discinfo">
    <di:title/>
  </di:discinfo>
</disclib>
"""
        bdmt_file = tmp_path / "bdmt_eng.xml"
        bdmt_file.write_text(xml_content)
        result = parse_bdmt(bdmt_file)
        assert result == {"disc_title": None}

    def test_parse_bdmt_missing_file(self, tmp_path: Path) -> None:
        """Non-existent path returns None (silent skip per D-08)."""
        result = parse_bdmt(tmp_path / "nonexistent.xml")
        assert result is None

    def test_parse_bdmt_malformed_xml(self, tmp_path: Path) -> None:
        """Malformed XML returns None (silent skip)."""
        bdmt_file = tmp_path / "bdmt_eng.xml"
        bdmt_file.write_text("<not valid xml><<<")
        result = parse_bdmt(bdmt_file)
        assert result is None


# =========================================================================
# find_bdmt_file
# =========================================================================

class TestFindBdmtFile:
    """find_bdmt_file: locate best bdmt_*.xml in META/DL directory."""

    def test_find_bdmt_file_region_match(self, tmp_path: Path) -> None:
        """Region A matches bdmt_eng.xml when both eng and deu exist."""
        (tmp_path / "bdmt_eng.xml").write_text("<xml/>")
        (tmp_path / "bdmt_deu.xml").write_text("<xml/>")
        result = find_bdmt_file(tmp_path, region_code="A")
        assert result is not None
        assert result.name == "bdmt_eng.xml"

    def test_find_bdmt_file_fallback(self, tmp_path: Path) -> None:
        """When region-matched file missing, falls back to first found."""
        (tmp_path / "bdmt_deu.xml").write_text("<xml/>")
        result = find_bdmt_file(tmp_path, region_code="A")
        assert result is not None
        assert result.name == "bdmt_deu.xml"

    def test_find_bdmt_file_no_files(self, tmp_path: Path) -> None:
        """Empty directory returns None."""
        result = find_bdmt_file(tmp_path)
        assert result is None

    def test_find_bdmt_file_no_dir(self, tmp_path: Path) -> None:
        """Non-existent directory returns None."""
        result = find_bdmt_file(tmp_path / "nonexistent")
        assert result is None


# =========================================================================
# extract_bd_chapters
# =========================================================================

class TestExtractBdChapters:
    """extract_bd_chapters: convert MPLS ChapterMark list to chapter dicts."""

    def test_extract_bd_chapters(self) -> None:
        """Filters mark_type==1, converts 45kHz to int seconds, 1-based index."""
        from ovid.mpls_parser import ChapterMark

        marks = [
            ChapterMark(mark_type=1, play_item_ref=0, timestamp=0, duration_seconds=0.0),
            ChapterMark(mark_type=2, play_item_ref=0, timestamp=1000, duration_seconds=0.022),
            ChapterMark(mark_type=1, play_item_ref=0, timestamp=4500000, duration_seconds=100.0),
        ]
        chapters = extract_bd_chapters(marks)

        assert len(chapters) == 2
        assert chapters[0] == {"chapter_index": 1, "name": None, "start_time_secs": 0}
        assert chapters[1] == {"chapter_index": 2, "name": None, "start_time_secs": 100}

    def test_extract_bd_chapters_empty(self) -> None:
        """Empty marks list produces empty chapters."""
        chapters = extract_bd_chapters([])
        assert chapters == []

    def test_extract_bd_chapters_all_non_entry(self) -> None:
        """All mark_type=2 produces no chapters."""
        from ovid.mpls_parser import ChapterMark

        marks = [
            ChapterMark(mark_type=2, play_item_ref=0, timestamp=0, duration_seconds=0.0),
            ChapterMark(mark_type=2, play_item_ref=0, timestamp=1000, duration_seconds=0.022),
        ]
        chapters = extract_bd_chapters(marks)
        assert chapters == []
