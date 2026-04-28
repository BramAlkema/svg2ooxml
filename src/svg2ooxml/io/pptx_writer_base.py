"""Shared infrastructure for PPTX package writers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree as ET

from svg2ooxml.common.boundaries import is_safe_relationship_id, resolve_package_child
from svg2ooxml.drawingml.assets import FontAsset, NavigationAsset
from svg2ooxml.drawingml.navigation import navigation_relationship_attributes
from svg2ooxml.drawingml.writer import DEFAULT_SLIDE_SIZE
from svg2ooxml.io.pptx_fonts import write_font_parts
from svg2ooxml.io.pptx_package_constants import (
    ALLOWED_SLIDE_SIZE_MODES,
    MASK_REL_TYPE,
    REL_NS,
)
from svg2ooxml.io.pptx_package_model import (
    MaskAsset,
    PackagedFont,
    PackagedMedia,
    SlideAssembly,
)
from svg2ooxml.io.pptx_part_names import sanitize_slide_filename
from svg2ooxml.io.pptx_presentation import update_presentation_parts

if TYPE_CHECKING:  # pragma: no cover - typing only
    from svg2ooxml.core.tracing import ConversionTracer


class PackageWriterBase:
    def __init__(
        self,
        *,
        base_template: Path,
        content_types_template: str,
        slide_rels_template: str,
        slide_size_mode: str | None = None,
    ) -> None:
        self._base_template = base_template
        self._content_types_template = content_types_template
        self._slide_rels_template = slide_rels_template
        self._slide_size_mode = slide_size_mode
        self._tracer: ConversionTracer | None = None

    def _trace_packaging(
        self,
        action: str,
        *,
        metadata: dict[str, object] | None = None,
        subject: str | None = None,
        stage: str = "packaging",
    ) -> None:
        tracer = self._tracer
        if tracer is not None:
            tracer.record_stage_event(
                stage=stage,
                action=action,
                metadata=metadata,
                subject=subject,
            )

    def _write_media_parts(
        self,
        package_root: Path,
        media_parts: Sequence[PackagedMedia],
    ) -> None:
        if not media_parts:
            return
        media_dir = package_root / "ppt" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        unique_media: dict[str, PackagedMedia] = {}
        for part in media_parts:
            existing = unique_media.get(part.filename)
            if existing is None:
                unique_media[part.filename] = part
            elif existing.data != part.data or existing.content_type != part.content_type:
                raise ValueError(
                    f"Conflicting media payloads target ppt/media/{part.filename!r}."
                )
        for part in unique_media.values():
            target = resolve_package_child(
                package_root,
                part.package_path,
                required_prefix=Path("ppt") / "media",
            )
            target.write_bytes(part.data)
            self._trace_packaging(
                "media_part_written",
                metadata={
                    "filename": part.filename,
                    "content_type": part.content_type,
                },
                subject=part.relationship_id,
            )

    def _write_mask_parts(
        self,
        package_root: Path,
        mask_parts: Sequence[MaskAsset],
    ) -> None:
        if not mask_parts:
            return
        written: dict[Path, MaskAsset] = {}
        for part in mask_parts:
            path = resolve_package_child(
                package_root,
                part.package_path,
                required_prefix=Path("ppt") / "masks",
            )
            existing = written.get(path)
            if existing is not None:
                if existing.data != part.data or existing.content_type != part.content_type:
                    raise ValueError(
                        f"Conflicting mask payloads target {part.part_name!r}."
                    )
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(part.data)
            written[path] = part
            self._trace_packaging(
                "mask_part_written",
                metadata={"path": str(part.package_path)},
                subject=part.relationship_id,
            )

    def _write_slide_relationships(
        self,
        slides_dir: Path,
        slide_filename: str,
        media_parts: Sequence[PackagedMedia],
        navigation_assets: Sequence[NavigationAsset],
        mask_parts: Sequence[MaskAsset],
    ) -> None:
        safe_slide_filename = sanitize_slide_filename(slide_filename)
        rels_path = slides_dir / "_rels" / f"{safe_slide_filename}.rels"
        rels_root = ET.fromstring(self._slide_rels_template.encode("utf-8"))
        existing_ids = {
            rel.get("Id") for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")
        }

        for kind, parts in (("media", media_parts), ("mask", mask_parts)):
            for part in parts:
                self._validate_asset_relationship_id(
                    part.relationship_id,
                    existing_ids,
                    kind=kind,
                )
                ET.SubElement(
                    rels_root,
                    f"{{{REL_NS}}}Relationship",
                    {
                        "Id": part.relationship_id,
                        "Type": MASK_REL_TYPE,
                        "Target": part.relationship_target,
                    },
                )
                existing_ids.add(part.relationship_id)

        for asset in navigation_assets:
            attributes = navigation_relationship_attributes(
                asset,
                existing_ids=existing_ids,
            )
            if attributes is None:
                continue
            ET.SubElement(rels_root, f"{{{REL_NS}}}Relationship", attributes)
            existing_ids.add(attributes["Id"])

        ET.ElementTree(rels_root).write(
            rels_path,
            encoding="utf-8",
            xml_declaration=True,
        )

    @staticmethod
    def _validate_asset_relationship_id(
        relationship_id: str,
        existing_ids: set[str | None],
        *,
        kind: str,
    ) -> None:
        if not is_safe_relationship_id(relationship_id):
            raise ValueError(f"Unsafe {kind} relationship ID {relationship_id!r}.")
        if relationship_id in existing_ids:
            raise ValueError(f"Duplicate {kind} relationship ID {relationship_id!r}.")

    def _write_font_parts(
        self,
        package_root: Path,
        font_assets: Sequence[FontAsset],
    ) -> list[PackagedFont]:
        return write_font_parts(
            package_root,
            font_assets,
            trace_packaging=self._trace_packaging,
        )

    def _update_presentation_parts(
        self,
        package_root: Path,
        slides: Sequence[SlideAssembly],
        fonts: Sequence[PackagedFont],
        slide_size: tuple[int, int] | None = None,
    ) -> None:
        update_presentation_parts(
            package_root=package_root,
            slides=slides,
            fonts=fonts,
            slide_size=slide_size,
            trace_packaging=self._trace_packaging,
        )

    def _resolve_slide_size_mode(self, override: str | None) -> str:
        resolved = override or self._slide_size_mode or "multipage"
        if resolved not in ALLOWED_SLIDE_SIZE_MODES:
            raise ValueError(
                f"Unsupported slide_size_mode {resolved!r}. "
                f"Expected one of {sorted(ALLOWED_SLIDE_SIZE_MODES)}."
            )
        return resolved

    def _select_slide_size(
        self,
        slides: Sequence[SlideAssembly],
        *,
        slide_size_mode: str | None,
    ) -> tuple[int, int] | None:
        if not slides:
            return None

        mode = self._resolve_slide_size_mode(slide_size_mode)
        if mode == "same":
            selected = slides[0].slide_size
        else:
            widths = [slide.slide_size[0] for slide in slides]
            heights = [slide.slide_size[1] for slide in slides]
            selected = (
                max([DEFAULT_SLIDE_SIZE[0], *widths]),
                max([DEFAULT_SLIDE_SIZE[1], *heights]),
            )

        self._trace_packaging(
            "slide_size_mode_resolved",
            metadata={
                "mode": mode,
                "width_emu": selected[0],
                "height_emu": selected[1],
                "slide_count": len(slides),
            },
        )
        return selected


_PackageWriterBase = PackageWriterBase

__all__ = ["PackageWriterBase", "_PackageWriterBase"]
