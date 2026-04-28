"""Package part naming and small metadata normalization helpers."""

from __future__ import annotations

from pathlib import Path

from svg2ooxml.common.boundaries import sanitize_package_filename
from svg2ooxml.io.pptx_package_constants import FONT_STYLE_TAGS, MASK_CONTENT_TYPE

_CONTENT_TYPE_SUFFIXES: dict[str, tuple[str, ...]] = {
    "image/png": (".png",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/gif": (".gif",),
    "image/svg+xml": (".svg",),
    "image/x-emf": (".emf",),
    MASK_CONTENT_TYPE: (".xml",),
}


def normalized_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def suffixes_for_content_type(content_type: str | None) -> tuple[str, ...]:
    return _CONTENT_TYPE_SUFFIXES.get(normalized_content_type(content_type), (".bin",))


def _sanitize_filename_for_content_type(
    filename: str | None,
    content_type: str | None,
    *,
    fallback_stem: str,
) -> str:
    suffixes = suffixes_for_content_type(content_type)
    fallback_suffix = suffixes[0]
    candidate = sanitize_package_filename(
        filename,
        fallback_stem=fallback_stem,
        fallback_suffix=fallback_suffix,
    )
    path = Path(candidate)
    suffix = path.suffix.lower()
    if suffix not in suffixes:
        suffix = fallback_suffix
    stem = path.stem or fallback_stem
    return f"{stem}{suffix}"


def sanitize_media_filename(filename: str | None, content_type: str | None) -> str:
    """Return a safe package filename for media parts."""

    return _sanitize_filename_for_content_type(
        filename,
        content_type,
        fallback_stem="media",
    )


def sanitize_mask_part_name(part_name: str | None, content_type: str | None) -> str:
    """Return a safe absolute OPC part name for DrawingML mask assets."""

    filename = sanitize_package_filename(part_name, fallback_stem="mask")
    safe_filename = _sanitize_filename_for_content_type(
        filename,
        content_type,
        fallback_stem="mask",
    )
    return f"/ppt/masks/{safe_filename}"


def sanitize_slide_filename(filename: str | None, *, fallback_index: object = None) -> str:
    """Return a safe slide XML filename with no directory components."""

    index = positive_int(fallback_index)
    fallback_stem = f"slide{index}" if index is not None else "slide"
    candidate = sanitize_package_filename(
        filename,
        fallback_stem=fallback_stem,
        fallback_suffix=".xml",
    )
    stem = Path(candidate).stem or fallback_stem
    return f"{stem}.xml"


def positive_int(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if parsed < 1:
        return None
    return parsed


def suffix_for_content_type(content_type: str) -> str:
    """Map image MIME type to file extension."""
    return suffixes_for_content_type(content_type)[0]


def content_type_for_extension(extension: str) -> str:
    mapping = {
        "ttf": "application/x-fontdata",
        "otf": "application/x-fontdata",
        "woff": "application/font-woff",
        "woff2": "application/font-woff2",
        "odttf": "application/vnd.openxmlformats-officedocument.obfuscatedFont",
        "fntdata": "application/x-fontdata",
    }
    return mapping.get(extension.lower(), "application/octet-stream")


def normalize_style_kind(value: object) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "bolditalic":
            return "boldItalic"
        if lowered in FONT_STYLE_TAGS:
            return lowered
    return "regular"


def safe_int(value: object | None) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return None
    return None


__all__ = [
    "content_type_for_extension",
    "normalize_style_kind",
    "normalized_content_type",
    "positive_int",
    "safe_int",
    "sanitize_mask_part_name",
    "sanitize_media_filename",
    "sanitize_package_filename",
    "sanitize_slide_filename",
    "suffix_for_content_type",
    "suffixes_for_content_type",
]
