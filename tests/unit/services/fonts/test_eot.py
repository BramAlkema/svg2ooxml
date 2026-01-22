from __future__ import annotations

import struct
from pathlib import Path
import uuid

import pytest

from svg2ooxml.services.fonts.eot import (
    HEADER_SCHEMA,
    HEADER_SIZE,
    EOT_MAGIC,
    EOT_VERSION,
    build_eot,
)


def _unpack_header(blob: bytes) -> dict[str, int | bytes]:
    cursor = 0
    values: dict[str, int | bytes] = {}
    for field_type, field_name in HEADER_SCHEMA:
        if field_type == "panose":
            values[field_name] = blob[cursor : cursor + 10]
            cursor += 10
            continue
        fmt = {"u32": "<L", "u16": "<H", "u8": "<B"}[field_type]
        size = struct.calcsize(fmt)
        values[field_name] = struct.unpack_from(fmt, blob, cursor)[0]
        cursor += size
    return values


def test_build_eot_structure():
    pytest.importorskip("fontforge")
    font_path = Path("tests/resources/ScheherazadeRegOT.ttf")
    font_bytes = font_path.read_bytes()

    guid = uuid.UUID("12345678-1234-5678-9abc-123456789abc")
    root_string = "urn:fonts:test"

    result = build_eot(
        font_bytes,
        resolved_family="Test Family",
        resolved_style="Regular",
        root_string=root_string,
        guid=guid,
    )

    assert result.family_name == "Test Family"
    assert result.style_name == "Regular"
    assert result.root_string == root_string
    assert result.guid == guid
    assert result.data.endswith(font_bytes)

    header = result.data[:HEADER_SIZE]
    values = _unpack_header(header)

    assert values["EOTSize"] == len(result.data)
    assert values["FontDataSize"] == len(font_bytes)
    assert values["Version"] == EOT_VERSION
    assert values["MagicNumber"] == EOT_MAGIC
    assert values["FamilyNameOffset"] == HEADER_SIZE

    family_size = values["FamilyNameSize"]
    root_size = values["RootStringSize"]
    assert family_size > 0
    assert root_size == len(root_string.encode("utf-16le")) + 2

    family_blob = result.data[
        values["FamilyNameOffset"] : values["FamilyNameOffset"] + family_size
    ]
    root_blob = result.data[
        values["RootStringOffset"] : values["RootStringOffset"] + root_size
    ]
    assert family_blob.endswith(b"\x00\x00")
    assert root_blob.endswith(b"\x00\x00")
    decoded_family = family_blob.decode("utf-16le").rstrip("\x00")
    decoded_root = root_blob.decode("utf-16le").rstrip("\x00")
    assert decoded_family == "Test Family"
    assert decoded_root == root_string


def test_build_eot_obfuscation():
    pytest.importorskip("fontforge")
    font_path = Path("tests/resources/ScheherazadeRegOT.ttf")
    font_bytes = font_path.read_bytes()
    guid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    plain = build_eot(font_bytes, guid=guid)
    obfuscated = build_eot(font_bytes, guid=guid, obfuscate=True)

    assert plain.root_string == str(guid)
    assert obfuscated.guid == guid
    assert plain.data != obfuscated.data

    values = _unpack_header(plain.data[:HEADER_SIZE])
    font_offset = len(plain.data) - values["FontDataSize"]
    assert plain.data[:font_offset] == obfuscated.data[:font_offset]
    assert plain.data[font_offset + 32 :] == obfuscated.data[font_offset + 32 :]
