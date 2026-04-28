"""Types shared by font loader modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


class WOFFTableEntry(TypedDict):
    """WOFF table directory entry."""

    tag: bytes
    comp_offset: int
    comp_length: int
    orig_length: int
    checksum: bytes


@dataclass
class LoadedFont:
    """Result of loading a font from a source."""

    data: bytes
    format: str
    source_url: str
    decompressed: bool = False
    size_bytes: int = 0

    def __post_init__(self) -> None:
        if self.size_bytes == 0:
            self.size_bytes = len(self.data)


__all__ = ["LoadedFont", "WOFFTableEntry"]
