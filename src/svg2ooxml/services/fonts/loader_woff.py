"""WOFF and WOFF2 decompression helpers for the font loader."""

from __future__ import annotations

import logging
import zlib
from io import BytesIO

from .fontforge_utils import generate_font_bytes, open_font
from .loader_types import WOFFTableEntry


def decompress_woff2(
    data: bytes,
    *,
    max_size: int,
    fontforge_available: bool,
    logger: logging.Logger,
) -> bytes | None:
    """Decompress WOFF2 font to TTF/OTF using FontForge."""
    if not fontforge_available:
        logger.warning("FontForge not available, cannot decompress WOFF2.")
        return None

    try:
        if len(data) < 48:
            logger.warning("WOFF2 data too short")
            return None
        if data[:4] != b"wOF2":
            logger.warning("Invalid WOFF2 signature")
            return None
        try:
            reported_length = int.from_bytes(data[8:12], "big")
            num_tables = int.from_bytes(data[12:14], "big")
            total_sfnt_size = int.from_bytes(data[16:20], "big")
            total_compressed_size = int.from_bytes(data[20:24], "big")
        except Exception:
            logger.warning("Invalid WOFF2 header fields")
            return None

        if reported_length and reported_length != len(data):
            logger.warning("WOFF2 length mismatch")
            return None
        if num_tables == 0 or total_sfnt_size == 0 or total_compressed_size == 0:
            logger.warning("WOFF2 header indicates empty payload")
            return None
        if total_compressed_size > len(data) - 48:
            logger.warning("WOFF2 compressed payload size is invalid")
            return None

        with open_font(data, suffix=".woff2") as font:
            result = generate_font_bytes(font, suffix=".ttf")

        logger.debug("Decompressed WOFF2: %d → %d bytes", len(data), len(result))
        if len(result) > max_size:
            logger.warning("Decompressed WOFF2 exceeds size limit: %d > %d", len(result), max_size)
            return None
        return result

    except Exception as exc:
        logger.warning("WOFF2 decompression failed: %s", exc)
        return None


def decompress_woff(
    data: bytes,
    *,
    max_size: int,
    logger: logging.Logger,
) -> bytes | None:
    """Decompress WOFF font to TTF/OTF."""
    try:
        if len(data) < 44:
            logger.warning("WOFF data too short")
            return None

        signature = data[0:4]
        if signature != b"wOFF":
            logger.warning("Invalid WOFF signature")
            return None

        flavor = data[4:8]
        num_tables = int.from_bytes(data[12:14], "big")
        total_sfnt_size = int.from_bytes(data[16:20], "big")
        if total_sfnt_size > max_size:
            logger.warning("Decompressed WOFF exceeds size limit")
            return None

        output = BytesIO()
        _write_sfnt_header(output, flavor, num_tables)
        table_entries = _read_woff_table_entries(data, num_tables, logger)
        if table_entries is None:
            return None
        _write_table_directory(output, table_entries, num_tables)
        if not _write_table_data(output, data, table_entries, logger):
            return None

        result = output.getvalue()
        logger.debug("Decompressed WOFF: %d → %d bytes", len(data), len(result))
        return result

    except Exception as exc:
        logger.warning("WOFF decompression failed: %s", exc)
        return None


def _write_sfnt_header(output: BytesIO, flavor: bytes, num_tables: int) -> None:
    output.write(flavor)
    output.write(num_tables.to_bytes(2, "big"))

    entry_selector = 0
    search_range = 1
    while search_range <= num_tables:
        search_range *= 2
        entry_selector += 1
    entry_selector -= 1
    search_range = (2**entry_selector) * 16
    range_shift = num_tables * 16 - search_range

    output.write(search_range.to_bytes(2, "big"))
    output.write(entry_selector.to_bytes(2, "big"))
    output.write(range_shift.to_bytes(2, "big"))


def _read_woff_table_entries(
    data: bytes,
    num_tables: int,
    logger: logging.Logger,
) -> list[WOFFTableEntry] | None:
    table_entries: list[WOFFTableEntry] = []
    offset = 44
    for _ in range(num_tables):
        if offset + 20 > len(data):
            logger.warning("WOFF table directory truncated")
            return None
        entry: WOFFTableEntry = {
            "tag": data[offset : offset + 4],
            "comp_offset": int.from_bytes(data[offset + 4 : offset + 8], "big"),
            "comp_length": int.from_bytes(data[offset + 8 : offset + 12], "big"),
            "orig_length": int.from_bytes(data[offset + 12 : offset + 16], "big"),
            "checksum": data[offset + 16 : offset + 20],
        }
        table_entries.append(entry)
        offset += 20
    return table_entries


def _write_table_directory(
    output: BytesIO,
    table_entries: list[WOFFTableEntry],
    num_tables: int,
) -> None:
    current_offset = 12 + num_tables * 16
    for entry in table_entries:
        output.write(entry["tag"])
        output.write(entry["checksum"])
        output.write(current_offset.to_bytes(4, "big"))
        output.write(entry["orig_length"].to_bytes(4, "big"))
        current_offset += entry["orig_length"]
        if current_offset % 4 != 0:
            current_offset += 4 - (current_offset % 4)


def _write_table_data(
    output: BytesIO,
    data: bytes,
    table_entries: list[WOFFTableEntry],
    logger: logging.Logger,
) -> bool:
    for entry in table_entries:
        comp_offset = entry["comp_offset"]
        comp_length = entry["comp_length"]
        orig_length = entry["orig_length"]

        if comp_offset + comp_length > len(data):
            logger.warning("WOFF table data out of bounds")
            return False

        compressed_data = data[comp_offset : comp_offset + comp_length]
        if comp_length < orig_length:
            try:
                table_data = zlib.decompress(compressed_data)
            except Exception as exc:
                logger.warning("Failed to decompress WOFF table: %s", exc)
                return False
        else:
            table_data = compressed_data

        if len(table_data) != orig_length:
            logger.warning("WOFF table size mismatch")
            return False

        output.write(table_data)
        padding = (4 - (len(table_data) % 4)) % 4
        if padding:
            output.write(b"\x00" * padding)
    return True


__all__ = ["decompress_woff", "decompress_woff2"]
