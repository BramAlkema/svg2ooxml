"""Embedded OpenType (EOT) helpers for PresentationML font packaging.

PowerPoint stores embedded fonts as `.fntdata` parts that wrap OpenType payloads
in the EOT container defined by ECMA‑376 §21.1.7.6. This module converts the
subsetted OpenType bytes produced by FontForge into spec-compliant EOT
streams and exposes a thin metadata wrapper that downstream packaging code can
use when emitting `<p:embeddedFontLst>` entries. Optional GUID/root-string
support and obfuscation hooks mirror the ODTTF algorithm in case we need to
target WordprocessingML in the future.

The layout, field names, and obfuscation behaviour are based on Mozilla’s
public `eottool.py` reference implementation (Bugzilla attachment 361505),
adapted to fit svg2ooxml’s coding style.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
import uuid
from typing import Final, Iterable

from svg2ooxml.services.fonts.fontforge_utils import (
    FONTFORGE_AVAILABLE,
    get_table_data,
    open_font,
)
from svg2ooxml.services.fonts.opentype_utils import parse_head_checksum, parse_os2_table


EOT_VERSION: Final[int] = 0x00020001
EOT_MAGIC: Final[int] = 0x504C
HEADER_SCHEMA: Final[tuple[tuple[str, str], ...]] = (
    ("u32", "EOTSize"),
    ("u32", "FontDataSize"),
    ("u32", "Version"),
    ("u32", "Flags"),
    ("panose", "FontPANOSE"),
    ("u8", "Charset"),
    ("u8", "Italic"),
    ("u32", "Weight"),
    ("u16", "fsType"),
    ("u16", "MagicNumber"),
    ("u32", "UnicodeRange1"),
    ("u32", "UnicodeRange2"),
    ("u32", "UnicodeRange3"),
    ("u32", "UnicodeRange4"),
    ("u32", "CodePageRange1"),
    ("u32", "CodePageRange2"),
    ("u32", "ChecksumAdjustment"),
    ("u32", "Reserved1"),
    ("u32", "Reserved2"),
    ("u32", "Reserved3"),
    ("u32", "Reserved4"),
    ("u32", "Padding1"),
    ("u32", "FamilyNameSize"),
    ("u32", "FamilyNameOffset"),
    ("u32", "StyleNameSize"),
    ("u32", "StyleNameOffset"),
    ("u32", "VersionNameSize"),
    ("u32", "VersionNameOffset"),
    ("u32", "FullNameSize"),
    ("u32", "FullNameOffset"),
    ("u32", "RootStringSize"),
    ("u32", "RootStringOffset"),
    ("u32", "SignatureSize"),
    ("u32", "SignatureOffset"),
    ("u32", "EUDCCodePage"),
    ("u32", "EUDCSize"),
    ("u32", "EUDCOffset"),
)

FIELD_LENGTH: Final[dict[str, int]] = {"u32": 4, "u16": 2, "u8": 1, "panose": 10}
HEADER_SIZE: Final[int] = sum(FIELD_LENGTH[field] for field, _ in HEADER_SCHEMA)
STRING_FIELDS: Final[tuple[str, ...]] = (
    "FamilyName",
    "StyleName",
    "VersionName",
    "FullName",
    "RootString",
)


class EOTConversionError(RuntimeError):
    """Raised when an Embedded OpenType payload cannot be produced."""


@dataclass(frozen=True)
class EOTResult:
    """Encapsulate the converted EOT payload plus derived metadata."""

    data: bytes
    family_name: str
    style_name: str
    full_name: str
    version_name: str
    weight: int
    italic: bool
    charset: int
    panose: bytes
    fs_type: int
    unicode_ranges: tuple[int, int, int, int]
    codepage_ranges: tuple[int, int]
    root_string: str
    guid: uuid.UUID | None


@dataclass(frozen=True)
class _FontNames:
    family: str
    style: str
    full: str
    version: str


@dataclass(frozen=True)
class _FontMetrics:
    panose: bytes
    charset: int
    italic: bool
    weight: int
    fs_type: int
    unicode_ranges: tuple[int, int, int, int]
    codepage_ranges: tuple[int, int]
    checksum_adjustment: int


@dataclass(frozen=True)
class _StringTable:
    blob: bytes
    sizes: dict[str, int]
    offsets: dict[str, int]


def build_eot(
    font_bytes: bytes,
    *,
    resolved_family: str | None = None,
    resolved_style: str | None = None,
    root_string: str | None = None,
    guid: uuid.UUID | str | None = None,
    obfuscate: bool = False,
) -> EOTResult:
    """
    Convert subsetted OpenType bytes into an EOT payload suitable for PPTX packaging.

    Parameters
    ----------
    font_bytes:
        Raw TTF/OTF stream (typically produced by FontForge subsetting).
    resolved_family / resolved_style:
        Optional overrides from the font resolver; fall back to name table entries.
    root_string:
        Optional root string (ECMA terminology) used when Office records the font
        origin. If omitted and ``guid`` is supplied, we default to the GUID string.
    guid:
        Font GUID recorded elsewhere in the PPTX/OOXML package. When provided it is
        returned alongside the payload and can optionally drive obfuscation.
    obfuscate:
        Apply ECMA's GUID-based XOR obfuscation to the font bytes (mirrors ODTTF).
        PowerPoint does not need this, but DOCX embedding does.
    """

    if not isinstance(font_bytes, (bytes, bytearray)):
        raise EOTConversionError("font_bytes must be a byte buffer")
    if not FONTFORGE_AVAILABLE:  # pragma: no cover - environments without FontForge
        raise EOTConversionError("FontForge is required for EOT conversion")

    normalized_root = _normalize_root_string(root_string, guid)
    normalized_guid = _normalize_guid(guid)

    try:
        with open_font(font_bytes, suffix=".ttf") as font:
            names = _extract_font_names(font, resolved_family, resolved_style)
            metrics = _extract_font_metrics(font)
    except Exception as exc:
        raise EOTConversionError(f"failed to parse font: {exc}") from exc

    string_table = _build_string_table(names, normalized_root)
    header = _assemble_header(metrics, string_table, len(font_bytes))

    payload = bytearray(header + string_table.blob + bytes(font_bytes))
    if obfuscate:
        if normalized_guid is None:
            raise EOTConversionError("obfuscation requested but no GUID supplied")
        _apply_guid_obfuscation(payload, normalized_guid, len(header) + len(string_table.blob))

    final_bytes = bytes(payload)
    return EOTResult(
        data=final_bytes,
        family_name=names.family,
        style_name=names.style,
        full_name=names.full,
        version_name=names.version,
        weight=metrics.weight,
        italic=metrics.italic,
        charset=metrics.charset,
        panose=metrics.panose,
        fs_type=metrics.fs_type,
        unicode_ranges=metrics.unicode_ranges,
        codepage_ranges=metrics.codepage_ranges,
        root_string=normalized_root,
        guid=normalized_guid,
    )

def _extract_font_names(font: object, resolved_family: str | None, resolved_style: str | None) -> _FontNames:
    family = resolved_family or _get_sfnt_name(font, 1) or _get_attr(font, "familyname") or "EmbeddedFont"
    style = resolved_style or _get_sfnt_name(font, 2) or _get_attr(font, "weight") or "Regular"
    version = _get_sfnt_name(font, 5) or _get_attr(font, "version") or "1.0"
    full = _get_sfnt_name(font, 4) or _get_attr(font, "fullname") or f"{family} {style}".strip()
    return _FontNames(family=family, style=style, full=full, version=version)


def _extract_font_metrics(font: object) -> _FontMetrics:
    os2 = parse_os2_table(get_table_data(font, "OS/2"))
    checksum_adjustment = parse_head_checksum(get_table_data(font, "head"))

    panose = os2.panose
    charset = _guess_charset(os2.codepage_ranges[0])
    italic = _is_italic(os2, font)
    weight = int(os2.weight or 400)
    fs_type = int(os2.fs_type or 0) & 0xFFFF

    return _FontMetrics(
        panose=panose,
        charset=charset,
        italic=italic,
        weight=weight,
        fs_type=fs_type,
        unicode_ranges=os2.unicode_ranges,
        codepage_ranges=os2.codepage_ranges,
        checksum_adjustment=checksum_adjustment,
    )


def _build_string_table(names: _FontNames, root_string: str) -> _StringTable:
    blobs = {
        "FamilyName": _encode_utf16le(names.family),
        "StyleName": _encode_utf16le(names.style),
        "VersionName": _encode_utf16le(names.version),
        "FullName": _encode_utf16le(names.full),
        "RootString": _encode_utf16le(root_string),
    }

    offsets: dict[str, int] = {}
    sizes: dict[str, int] = {}
    blob = bytearray()
    cursor = HEADER_SIZE

    for label in STRING_FIELDS:
        data = blobs[label]
        sizes[label] = len(data)
        if data:
            offsets[label] = cursor
            blob.extend(data)
            cursor += len(data)
        else:
            offsets[label] = 0

    padding = (4 - ((HEADER_SIZE + len(blob)) % 4)) % 4
    if padding:
        blob.extend(b"\x00" * padding)

    return _StringTable(blob=bytes(blob), sizes=sizes, offsets=offsets)


def _assemble_header(metrics: _FontMetrics, strings: _StringTable, font_length: int) -> bytes:
    font_data_size = font_length
    eot_size = HEADER_SIZE + len(strings.blob) + font_data_size

    header_values = {
        "EOTSize": eot_size,
        "FontDataSize": font_data_size,
        "Version": EOT_VERSION,
        "Flags": 0,
        "FontPANOSE": metrics.panose,
        "Charset": metrics.charset,
        "Italic": 1 if metrics.italic else 0,
        "Weight": metrics.weight,
        "fsType": metrics.fs_type,
        "MagicNumber": EOT_MAGIC,
        "UnicodeRange1": metrics.unicode_ranges[0],
        "UnicodeRange2": metrics.unicode_ranges[1],
        "UnicodeRange3": metrics.unicode_ranges[2],
        "UnicodeRange4": metrics.unicode_ranges[3],
        "CodePageRange1": metrics.codepage_ranges[0],
        "CodePageRange2": metrics.codepage_ranges[1],
        "ChecksumAdjustment": metrics.checksum_adjustment,
        "Reserved1": 0,
        "Reserved2": 0,
        "Reserved3": 0,
        "Reserved4": 0,
        "Padding1": 0,
        "SignatureSize": 0,
        "SignatureOffset": 0,
        "EUDCCodePage": 0,
        "EUDCSize": 0,
        "EUDCOffset": 0,
    }

    for label in STRING_FIELDS:
        header_values[f"{label}Size"] = strings.sizes[label]
        header_values[f"{label}Offset"] = strings.offsets[label]

    return bytes(_serialize_header(header_values))


def _serialize_header(values: dict[str, int | bytes]) -> bytearray:
    buffer = bytearray()
    for field_type, field_name in HEADER_SCHEMA:
        value = values.get(field_name, 0)
        if field_type == "u32":
            buffer.extend(struct.pack("<L", int(value) & 0xFFFFFFFF))
        elif field_type == "u16":
            buffer.extend(struct.pack("<H", int(value) & 0xFFFF))
        elif field_type == "u8":
            buffer.extend(struct.pack("<B", int(value) & 0xFF))
        elif field_type == "panose":
            chunk = bytes(value or b"")
            if len(chunk) < 10:
                chunk = chunk + b"\x00" * (10 - len(chunk))
            buffer.extend(chunk[:10])
        else:  # pragma: no cover - schema guard
            raise ValueError(f"unsupported field type: {field_type}")
    return buffer


def _encode_utf16le(value: str | None) -> bytes:
    if not value:
        return b""
    encoded = value.encode("utf-16le")
    if not encoded.endswith(b"\x00\x00"):
        encoded += b"\x00\x00"
    return encoded


def _get_attr(font: object, name: str) -> str:
    value = getattr(font, name, None)
    if isinstance(value, str):
        return value.strip()
    return ""


def _get_sfnt_name(font: object, name_id: int) -> str:
    names = getattr(font, "sfnt_names", None)
    if not names:
        return ""
    for record in _iter_sfnt_names(names):
        try:
            record_id = int(record[3])
        except Exception:
            continue
        if record_id != name_id:
            continue
        return _decode_sfnt_value(record[4])
    return ""


def _iter_sfnt_names(records: Iterable[tuple]) -> Iterable[tuple]:
    for record in records:
        if len(record) < 5:
            continue
        yield record


def _decode_sfnt_value(value: object) -> str:
    if isinstance(value, bytes):
        for encoding in ("utf-16-be", "utf-16le", "utf-8"):
            try:
                return value.decode(encoding).strip()
            except Exception:
                continue
        return value.decode("latin-1", errors="ignore").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _guess_charset(code_page_range1: int) -> int:
    if code_page_range1 & 0x20000000:
        return 2  # SYMBOL_CHARSET
    return 1  # DEFAULT_CHARSET


def _is_italic(os2, font: object) -> bool:
    if getattr(os2, "fs_selection", 0) & 0x01:
        return True
    italic_angle = getattr(font, "italicangle", 0)
    return bool(italic_angle)


def _normalize_root_string(value: str | None, guid: uuid.UUID | str | None) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(guid, uuid.UUID):
        return str(guid)
    if isinstance(guid, str) and guid:
        try:
            return str(uuid.UUID(guid))
        except Exception:
            return guid
    return ""


def _normalize_guid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str) and value:
        try:
            return uuid.UUID(value)
        except Exception:
            return None
    return None


def _apply_guid_obfuscation(payload: bytearray, guid: uuid.UUID, font_offset: int) -> None:
    """XOR the first 32 bytes of the font data with the GUID (ODTTF-style)."""

    key = guid.bytes_le
    limit = min(32, len(payload) - font_offset)
    for idx in range(limit):
        payload[font_offset + idx] ^= key[idx % 16]


__all__ = ["EOTConversionError", "EOTResult", "build_eot"]
