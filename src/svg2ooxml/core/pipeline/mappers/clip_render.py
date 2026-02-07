"""Utilities for translating clip results into mapper outputs."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from svg2ooxml.ir.scene import ClipRef


def clip_result_to_xml(
    result: Any | None,
    clip_ref: ClipRef | None = None,
) -> tuple[str, dict[str, Any] | None, list[dict[str, Any]] | None]:
    """Translate a clip computation result into XML and metadata."""

    clip_id = getattr(clip_ref, "clip_id", None)

    if result is None:
        placeholder = f"<!-- Clip unavailable: {clip_id or 'unknown'} -->"
        return placeholder, {"strategy": "unavailable", "clip_id": clip_id}, None

    metadata = dict(getattr(result, "metadata", {}) or {})
    strategy = getattr(result, "strategy", None)
    if strategy is not None:
        metadata.setdefault("strategy", getattr(strategy, "value", strategy))
    metadata.setdefault("clip_id", clip_id)
    metadata.setdefault("clip_strategy", metadata.get("strategy"))

    used_bbox = getattr(result, "used_bbox_rect", False)
    metadata["used_bbox_rect"] = bool(used_bbox)

    xml_snippet = _resolve_clip_xml(result) or f"<!-- Clip placeholder: {clip_id or 'unknown'} -->"

    media = getattr(result, "media", None)
    media_files = _normalize_media(media)
    if media_files:
        metadata["media_files"] = media_files

    return xml_snippet, metadata, media_files


def _resolve_clip_xml(result: Any) -> str | None:
    custgeom = getattr(result, "custgeom", None)
    if custgeom and getattr(custgeom, "path_xml", None):
        return custgeom.path_xml
    placeholder = getattr(result, "xml_placeholder", None)
    return str(placeholder) if placeholder else None


def _normalize_media(media: Any) -> list[dict[str, Any]] | None:
    if media is None:
        return None

    if isinstance(media, Iterable) and not isinstance(media, (bytes, str)):
        items = []
        for item in media:
            normalized = _media_entry(item)
            if normalized:
                items.append(normalized)
        return items or None

    entry = _media_entry(media)
    return [entry] if entry else None


def _media_entry(media: Any) -> dict[str, Any] | None:
    content_type = getattr(media, "content_type", None)
    entry = {
        "type": _infer_media_type(content_type),
        "content_type": content_type,
        "relationship_id": getattr(media, "rel_id", None),
        "part_name": getattr(media, "part_name", None),
        "data": getattr(media, "data", None),
        "bbox_emu": getattr(media, "bbox_emu", None),
        "width_emu": None,
        "height_emu": None,
        "description": getattr(media, "description", None),
    }
    bbox = entry["bbox_emu"]
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        entry["width_emu"] = bbox[2]
        entry["height_emu"] = bbox[3]
    return entry


def _infer_media_type(content_type: str | None) -> str:
    if not content_type:
        return "media"
    lower = content_type.lower()
    if "emf" in lower:
        return "emf"
    if "image" in lower:
        return "image"
    return "media"


__all__ = ["clip_result_to_xml"]
