"""Abstract base class for disc readers."""

from __future__ import annotations

import abc
from typing import List


class DiscReader(abc.ABC):
    """Read IFO files from a DVD source (folder, ISO image, or block device).

    Subclasses must implement :meth:`list_ifo_files`, :meth:`read_ifo`, and
    :meth:`close`.  All readers support the context-manager protocol.
    """

    @abc.abstractmethod
    def list_ifo_files(self) -> List[str]:
        """Return sorted list of ``.IFO`` filenames found in VIDEO_TS."""

    @abc.abstractmethod
    def read_ifo(self, name: str) -> bytes:
        """Return the raw bytes of the IFO file *name* (e.g. ``VIDEO_TS.IFO``)."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release any held resources (file handles, ISO objects)."""

    # -- context manager support --

    def __enter__(self) -> "DiscReader":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
