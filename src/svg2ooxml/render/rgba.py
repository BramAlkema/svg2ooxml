"""Straight RGBA8 pixel compositing and encoding helpers."""

from __future__ import annotations

import struct
import zlib


def source_over_straight_rgba8_pixel(
    pixels: bytearray,
    *,
    width_px: int,
    x: int,
    y: int,
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    """Composite a straight-alpha RGB source over one straight RGBA8 pixel."""
    alpha = max(0.0, min(1.0, alpha))
    if alpha <= 0.0:
        return

    index = (y * width_px + x) * 4
    dst_r = pixels[index] / 255.0
    dst_g = pixels[index + 1] / 255.0
    dst_b = pixels[index + 2] / 255.0
    dst_a = pixels[index + 3] / 255.0
    src_r = color[0] / 255.0
    src_g = color[1] / 255.0
    src_b = color[2] / 255.0
    out_a = alpha + dst_a * (1.0 - alpha)
    if out_a <= 0.0:
        return

    out_r = (src_r * alpha + dst_r * dst_a * (1.0 - alpha)) / out_a
    out_g = (src_g * alpha + dst_g * dst_a * (1.0 - alpha)) / out_a
    out_b = (src_b * alpha + dst_b * dst_a * (1.0 - alpha)) / out_a
    pixels[index] = int(round(out_r * 255.0))
    pixels[index + 1] = int(round(out_g * 255.0))
    pixels[index + 2] = int(round(out_b * 255.0))
    pixels[index + 3] = int(round(out_a * 255.0))


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Build a PNG chunk with CRC."""
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def encode_rgba8_png(pixels: bytearray | bytes, width_px: int, height_px: int) -> bytes:
    """Encode straight RGBA8 bytes as a minimal PNG."""
    rows = bytearray()
    row_stride = width_px * 4
    for row_idx in range(height_px):
        rows.append(0)
        start = row_idx * row_stride
        rows.extend(pixels[start : start + row_stride])

    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width_px, height_px, 8, 6, 0, 0, 0),
        )
        + png_chunk(b"IDAT", zlib.compress(bytes(rows)))
        + png_chunk(b"IEND", b"")
    )


__all__ = [
    "encode_rgba8_png",
    "png_chunk",
    "source_over_straight_rgba8_pixel",
]
