from __future__ import annotations

import struct

from svg2ooxml.io.emf.blob import EMFBlob, EMFRecordType


def _make_test_bmp(width: int = 2, height: int = 2) -> bytes:
    """Return a simple 24-bit BMP payload suitable for embedding."""

    row_stride = ((width * 3 + 3) // 4) * 4
    pixels = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            r = int(255 * x / max(1, width - 1))
            g = int(255 * y / max(1, height - 1))
            b = 128
            row.extend((b, g, r))
        row.extend(b"\x00" * (row_stride - len(row)))
        pixels.append(row)
    pixel_data = b"".join(reversed(pixels))
    info_header = struct.pack(
        "<IIIHHIIIIII",
        40,  # header size
        width,
        height,
        1,  # planes
        24,  # bpp
        0,  # compression
        len(pixel_data),
        2835,
        2835,
        0,
        0,
    )
    file_header = b"BM" + struct.pack(
        "<IHHI",
        14 + len(info_header) + len(pixel_data),
        0,
        0,
        14 + len(info_header),
    )
    return file_header + info_header + pixel_data


def test_create_dib_pattern_brush_caches_handles() -> None:
    blob = EMFBlob(width_emu=1000, height_emu=1000)
    bmp = _make_test_bmp()

    handle_first = blob.get_dib_pattern_brush(bmp)
    handle_second = blob.get_dib_pattern_brush(bmp)

    assert handle_first == handle_second

    emf_bytes = blob.finalize()
    assert struct.unpack_from("<I", emf_bytes, 0)[0] == EMFRecordType.EMR_HEADER
    record_token = struct.pack("<I", EMFRecordType.EMR_CREATEDIBPATTERNBRUSHPT)
    assert record_token in emf_bytes


def test_draw_bitmap_appends_stretchdibits_record() -> None:
    blob = EMFBlob(width_emu=2000, height_emu=2000)
    bmp = _make_test_bmp()

    blob.draw_bitmap(0, 0, 200, 200, 0, 0, 2, 2, bmp)
    emf_bytes = blob.finalize()

    assert struct.unpack_from("<I", emf_bytes, 0)[0] == EMFRecordType.EMR_HEADER
    record_token = struct.pack("<I", EMFRecordType.EMR_STRETCHDIBITS)
    assert record_token in emf_bytes
