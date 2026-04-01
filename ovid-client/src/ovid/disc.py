"""High-level Disc class — the public API for fingerprinting a DVD source.

Usage::

    disc = Disc.from_path("/path/to/VIDEO_TS")
    print(disc.fingerprint)      # dvd1-abc123...
    print(disc.canonical_string)  # OVID-DVD-1|3|8|...
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ovid.fingerprint import build_canonical_string, compute_fingerprint
from ovid.ifo_parser import VMGInfo, VTSInfo, parse_vmg, parse_vts
from ovid.readers import DiscReader, open_reader


@dataclass(frozen=True)
class Disc:
    """A parsed DVD disc with its OVID fingerprint.

    Create via :meth:`from_path` — do not instantiate directly.
    """
    fingerprint: str
    canonical_string: str
    source_type: str
    vts_count: int
    title_count: int
    _vmg: VMGInfo = field(repr=False)
    _vts_list: list[VTSInfo] = field(repr=False)

    @classmethod
    def from_path(cls, path: str) -> "Disc":
        """Auto-detect source type, parse IFO files, and compute fingerprint.

        Args:
            path: Path to a VIDEO_TS folder, an ISO image, or a block device.

        Returns:
            A :class:`Disc` instance with fingerprint and structural metadata.

        Raises:
            FileNotFoundError: If *path* does not exist or has no VIDEO_TS data.
            ValueError: If IFO files are malformed or missing.
        """
        import os

        if not os.path.exists(path):
            raise FileNotFoundError(f"Path does not exist: {path}")

        reader = open_reader(path)
        source_type = type(reader).__name__

        try:
            ifo_files = reader.list_ifo_files()
        except FileNotFoundError:
            reader.close()
            raise FileNotFoundError(
                f"No VIDEO_TS directory found at: {path}"
            )

        if not ifo_files:
            reader.close()
            raise FileNotFoundError(
                f"No IFO files found in VIDEO_TS at: {path}"
            )

        try:
            # Parse VMG (VIDEO_TS.IFO)
            vmg_data = reader.read_ifo("VIDEO_TS.IFO")
            vmg = parse_vmg(vmg_data)

            # Parse each VTS in order
            vts_list: list[VTSInfo] = []
            for i in range(1, vmg.vts_count + 1):
                vts_name = f"VTS_{i:02d}_0.IFO"
                vts_data = reader.read_ifo(vts_name)
                vts_list.append(parse_vts(vts_data))

            canonical = build_canonical_string(vmg, vts_list)
            fp = compute_fingerprint(canonical)

            return cls(
                fingerprint=fp,
                canonical_string=canonical,
                source_type=source_type,
                vts_count=vmg.vts_count,
                title_count=vmg.title_count,
                _vmg=vmg,
                _vts_list=vts_list,
            )
        finally:
            reader.close()
