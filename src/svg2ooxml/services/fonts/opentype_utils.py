"""Minimal OpenType table parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class OS2Metrics:
    fs_type: int = 0
    weight: int = 400
    panose: bytes = b"\x00" * 10
    unicode_ranges: tuple[int, int, int, int] = (0, 0, 0, 0)
    codepage_ranges: tuple[int, int] = (0, 0)
    fs_selection: int = 0


def parse_os2_table(data: bytes | None) -> OS2Metrics:
    if not data or len(data) < 10:
        return OS2Metrics()

    version = _read_u16(data, 0)
    weight = _read_u16(data, 4) or 400
    fs_type = _read_u16(data, 8)
    panose = data[32:42] if len(data) >= 42 else b"\x00" * 10

    unicode_ranges = (0, 0, 0, 0)
    if len(data) >= 58:
        unicode_ranges = struct.unpack_from(">LLLL", data, 42)

    fs_selection = _read_u16(data, 62) if len(data) >= 64 else 0

    codepage_ranges = (0, 0)
    if len(data) >= 86 and version >= 1:
        codepage_ranges = struct.unpack_from(">LL", data, 78)

    return OS2Metrics(
        fs_type=fs_type,
        weight=weight,
        panose=panose.ljust(10, b"\x00")[:10],
        unicode_ranges=tuple(int(value) for value in unicode_ranges),
        codepage_ranges=tuple(int(value) for value in codepage_ranges),
        fs_selection=fs_selection,
    )


def parse_head_checksum(data: bytes | None) -> int:
    if not data or len(data) < 12:
        return 0
    return int.from_bytes(data[8:12], "big") & 0xFFFFFFFF


def _read_u16(data: bytes, offset: int) -> int:
    if len(data) < offset + 2:
        return 0
    return struct.unpack_from(">H", data, offset)[0]


__all__ = ["OS2Metrics", "parse_head_checksum", "parse_os2_table"]
