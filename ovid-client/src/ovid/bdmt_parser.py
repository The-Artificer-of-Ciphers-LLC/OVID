"""Parse bdmt_*.xml files for Blu-ray disc title and title names.

The bdmt (Blu-ray Disc Meta) XML files live at BDMV/META/DL/bdmt_*.xml.
They use the namespace urn:BDA:bdmv;discinfo with prefix di:.
~20-40% of Blu-rays include these files.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)

_BDMT_NS = {"di": "urn:BDA:bdmv;discinfo"}

# ---------------------------------------------------------------------------
# Region code to bdmt language file mapping (D-09)
# ---------------------------------------------------------------------------

_REGION_LANG_MAP: dict[str, str] = {
    "A": "eng",
    "B": "eng",
    "C": "eng",
}


# ---------------------------------------------------------------------------
# bdmt file discovery
# ---------------------------------------------------------------------------

def find_bdmt_file(meta_dir: Path, region_code: str | None = None) -> Path | None:
    """Find the best bdmt_*.xml file in the META/DL directory.

    Tries region-matched file first (D-09), falls back to first found.
    Returns None if no bdmt files exist.

    Args:
        meta_dir: Path to the BDMV/META/DL directory.
        region_code: Optional disc region code (A, B, C).

    Returns:
        Path to the best bdmt file, or None.
    """
    if not meta_dir.is_dir():
        return None

    bdmt_files = sorted(meta_dir.glob("bdmt_*.xml"))
    if not bdmt_files:
        return None

    if region_code:
        lang = _REGION_LANG_MAP.get(region_code, "eng")
        target = f"bdmt_{lang}.xml"
        for f in bdmt_files:
            if f.name == target:
                return f

    return bdmt_files[0]


# ---------------------------------------------------------------------------
# bdmt XML parsing
# ---------------------------------------------------------------------------

def parse_bdmt(path: str | Path) -> dict | None:
    """Parse a bdmt_*.xml file and return disc title info.

    Returns dict with 'disc_title' key, or None on parse failure.
    Silent skip on missing file or malformed XML (D-08).

    Args:
        path: Path to a bdmt_*.xml file.

    Returns:
        Dict with 'disc_title' key, or None on failure.
    """
    try:
        tree = ET.parse(str(path))
        root = tree.getroot()
        name_elem = root.find(".//di:name", _BDMT_NS)
        disc_title = (
            name_elem.text.strip()
            if name_elem is not None and name_elem.text
            else None
        )
        return {"disc_title": disc_title}
    except (ET.ParseError, OSError):
        return None


# ---------------------------------------------------------------------------
# BD chapter extraction from MPLS marks
# ---------------------------------------------------------------------------

def extract_bd_chapters(chapter_marks: list) -> list[dict]:
    """Extract chapter data from MPLS PlayListMark objects.

    Filters to mark_type==1 (entry marks only), converts 45kHz timestamps
    to integer seconds (D-03), uses 1-based chapter_index (D-05).

    Args:
        chapter_marks: List of ChapterMark objects from MPLS parser.

    Returns:
        List of chapter dicts with chapter_index, name, start_time_secs.
    """
    chapters = []
    chapter_idx = 1
    for mark in chapter_marks:
        if mark.mark_type != 1:
            continue
        chapters.append({
            "chapter_index": chapter_idx,
            "name": None,
            "start_time_secs": int(round(mark.timestamp / 45000)),
        })
        chapter_idx += 1
    return chapters
