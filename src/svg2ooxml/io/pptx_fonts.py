"""Embedded font packaging helpers for PPTX output."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

from svg2ooxml.common.boundaries import is_safe_relationship_id
from svg2ooxml.drawingml.assets import FontAsset
from svg2ooxml.io.pptx_package_model import PackagedFont
from svg2ooxml.io.pptx_part_names import (
    content_type_for_extension,
    normalize_style_kind,
    safe_int,
)
from svg2ooxml.ir.text import EmbeddedFontPlan


def write_font_parts(
    package_root: Path,
    font_assets: Sequence[FontAsset],
    *,
    trace_packaging: Callable[..., None],
) -> list[PackagedFont]:
    if not font_assets:
        return []

    entries: list[tuple[EmbeddedFontPlan, dict[str, object], bytes]] = []
    seen_keys: set[tuple[object, ...]] = set()
    for asset in font_assets:
        plan = asset.plan
        if not plan.requires_embedding:
            continue
        metadata = plan.metadata or {}
        font_data = metadata.get("eot_bytes") or metadata.get("font_data")
        if not isinstance(font_data, (bytes, bytearray)):
            continue
        font_bytes = bytes(font_data)
        digest = hashlib.md5(font_bytes, usedforsecurity=False).hexdigest()
        key = (
            metadata.get("resolved_family") or plan.font_family,
            plan.font_family,
            plan.subset_strategy,
            plan.glyph_count,
            plan.relationship_hint,
            digest,
            metadata.get("font_style_kind"),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        entries.append((plan, metadata, font_bytes))

    if not entries:
        return []

    fonts_dir = package_root / "ppt" / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)

    packaged_fonts: list[PackagedFont] = []
    used_relationships: set[str] = set()
    rel_seed = 1
    font_index = 1

    for plan, metadata, font_bytes in entries:
        font_family = (
            metadata.get("resolved_family")
            or plan.font_family
            or metadata.get("font_family")
            or "EmbeddedFont"
        )
        style_kind = normalize_style_kind(metadata.get("font_style_kind"))
        style_flags = metadata.get("font_style_flags")
        if not isinstance(style_flags, dict):
            style_flags = {"style_kind": style_kind}
        extension = "fntdata"

        rel_id = (
            plan.relationship_hint.strip()
            if isinstance(plan.relationship_hint, str)
            and is_safe_relationship_id(plan.relationship_hint.strip())
            else None
        )
        if rel_id and rel_id in used_relationships:
            rel_id = None
        if rel_id is None:
            while True:
                candidate = f"rIdFont{rel_seed}"
                rel_seed += 1
                if candidate not in used_relationships:
                    rel_id = candidate
                    break
        used_relationships.add(rel_id)

        filename = f"font{font_index}.{extension}"
        font_index += 1
        while (fonts_dir / filename).exists():
            filename = f"font{font_index}.{extension}"
            font_index += 1
        target_path = fonts_dir / filename
        with target_path.open("wb") as handle:
            handle.write(font_bytes)
        guid_value = metadata.get("font_guid")
        if isinstance(guid_value, uuid.UUID):
            guid_str = str(guid_value)
        elif isinstance(guid_value, str) and guid_value:
            guid_str = guid_value
        else:
            guid_str = None
        trace_packaging(
            "font_part_written",
            stage="font",
            metadata={
                "filename": filename,
                "relationship_id": rel_id,
                "font_family": font_family,
                "style_kind": style_kind,
                "guid": guid_str,
            },
        )

        packaged_fonts.append(
            PackagedFont(
                filename=filename,
                relationship_id=rel_id,
                font_family=font_family,
                subsetted=bool(plan.glyph_count),
                content_type=content_type_for_extension(extension),
                style_kind=style_kind,
                style_flags=style_flags,
                guid=guid_str,
                root_string=metadata.get("font_root_string"),
                subset_prefix=metadata.get("subset_prefix"),
                pitch_family=safe_int(metadata.get("font_pitch_family")),
                charset=safe_int(metadata.get("font_charset")),
            )
        )

    return packaged_fonts


__all__ = ["write_font_parts"]
