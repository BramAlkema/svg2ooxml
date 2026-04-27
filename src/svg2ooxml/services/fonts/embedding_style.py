"""Style metadata helpers for embedded font payloads."""

from __future__ import annotations

from collections.abc import Mapping


def style_kind_from_metadata(metadata: Mapping[str, object]) -> str:
    value = str(metadata.get("font_style_kind") or "").lower()
    if value == "bolditalic":
        return "boldItalic"
    if value in {"regular", "bold", "italic", "boldItalic"}:
        return "regular" if value == "regular" else value
    bold = bool(metadata.get("bold"))
    italic = bool(metadata.get("italic"))
    if bold and italic:
        return "boldItalic"
    if bold:
        return "bold"
    if italic:
        return "italic"
    return "regular"


def style_name_from_kind(style_kind: str) -> str:
    mapping = {
        "regular": "Regular",
        "bold": "Bold",
        "italic": "Italic",
        "boldItalic": "Bold Italic",
    }
    return mapping.get(style_kind, "Regular")


def style_flags_from_metadata(metadata: Mapping[str, object], style_kind: str) -> dict[str, bool]:
    bold = bool(metadata.get("bold"))
    italic = bool(metadata.get("italic"))
    if style_kind == "boldItalic":
        bold = True
        italic = True
    elif style_kind == "bold":
        bold = True
    elif style_kind == "italic":
        italic = True
    return {
        "bold": bold,
        "italic": italic,
        "style_kind": style_kind,
    }


def derive_pitch_family(panose: bytes, style_flags: Mapping[str, object]) -> int:
    if not panose:
        return 0x32  # variable pitch, swiss
    family_type = panose[0]
    serif_style = panose[1] if len(panose) > 1 else 0

    family_nibble = 0x20  # default to SWISS
    if family_type == 2:  # Latin text
        if serif_style in {11, 12, 13, 14, 15, 16, 17, 18}:  # sans serif styles
            family_nibble = 0x20
        else:
            family_nibble = 0x10  # Roman
    elif family_type == 3:
        family_nibble = 0x40  # Script
    elif family_type == 4:
        family_nibble = 0x50  # Decorative
    elif family_type == 5:
        family_nibble = 0x30  # Symbol/modern

    pitch_bits = 0x2  # Variable pitch
    if style_flags.get("monospace"):
        pitch_bits = 0x1

    return (family_nibble & 0xF0) | (pitch_bits & 0x0F)
