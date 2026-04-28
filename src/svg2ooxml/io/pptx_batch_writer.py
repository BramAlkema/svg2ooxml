"""Batch PPTX package writer."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from svg2ooxml.drawingml.assets import FontAsset
from svg2ooxml.io.pptx_fonts import build_font_parts
from svg2ooxml.io.pptx_package_model import (
    MaskAsset,
    PackagedFont,
    PackagedMedia,
    SlideAssembly,
)
from svg2ooxml.io.pptx_package_parts import (
    apply_required_presentation_parts,
    build_content_types_xml,
    ensure_theme_extension_xml,
    inject_slide_layout_dimensions_parts,
    zip_package_parts,
)
from svg2ooxml.io.pptx_part_names import sanitize_slide_filename
from svg2ooxml.io.pptx_presentation import build_presentation_parts
from svg2ooxml.io.pptx_template_cache import load_template_entries
from svg2ooxml.io.pptx_writer_base import PackageWriterBase

if TYPE_CHECKING:  # pragma: no cover - typing only
    from svg2ooxml.core.tracing import ConversionTracer


class PackageWriter(PackageWriterBase):
    """Write PPTX packages using prepared slide assemblies."""

    def write_package(
        self,
        slides: Sequence[SlideAssembly],
        output_path: str | Path,
        *,
        tracer: ConversionTracer | None = None,
        persist_trace: bool | None = None,
        slide_size_mode: str | None = None,
    ) -> Path:
        prev_tracer = self._tracer
        self._tracer = tracer
        should_persist_trace = (tracer is not None) if persist_trace is None else (
            bool(persist_trace) and tracer is not None
        )

        if not slides:
            raise ValueError("At least one slide assembly is required to build a PPTX package.")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        try:
            parts = self._load_base_parts()
            self._trace_packaging(
                "packaging_start",
                metadata={"slide_count": len(slides)},
            )

            all_media: list[PackagedMedia] = []
            font_assets: list[FontAsset] = []
            all_masks: list[MaskAsset] = []
            packaged_fonts: list[PackagedFont] = []

            for slide in slides:
                self._write_slide(parts, slide)
                all_media.extend(slide.media)
                font_assets.extend(slide.font_assets)
                all_masks.extend(slide.masks)

            self._write_media_payloads(parts, all_media)
            self._write_mask_payloads(parts, all_masks)
            packaged_fonts = self._write_font_payloads(parts, font_assets)

            presentation_slide_size = self._select_slide_size(
                slides,
                slide_size_mode=slide_size_mode,
            )
            self._update_presentation_payloads(
                parts,
                slides,
                packaged_fonts,
                presentation_slide_size,
            )
            apply_required_presentation_parts(
                parts,
                trace_packaging=self._trace_packaging,
            )
            inject_slide_layout_dimensions_parts(parts, presentation_slide_size)
            parts["[Content_Types].xml"] = build_content_types_xml(
                self._content_types_template,
                slides,
                all_media,
                packaged_fonts,
                all_masks,
            )
            self._trace_packaging(
                "content_types_updated",
                metadata={
                    "slide_count": len(slides),
                    "media_count": len(all_media),
                    "font_count": len(packaged_fonts),
                    "mask_count": len(all_masks),
                },
            )

            zip_package_parts(parts, output)
            self._trace_packaging("pptx_written", metadata={"path": str(output)})

            if should_persist_trace and tracer is not None:
                trace_path = output.with_suffix(".trace.json")
                trace_payload = tracer.report().to_dict()
                trace_path.write_text(
                    json.dumps(trace_payload, indent=2),
                    encoding="utf-8",
                )
                self._trace_packaging(
                    "trace_persisted",
                    metadata={"path": str(trace_path)},
                )

            self._trace_packaging(
                "packaging_complete",
                metadata={"path": str(output)},
            )
            return output
        finally:
            self._tracer = prev_tracer

    def _write_slide(
        self,
        parts: dict[str, bytes],
        slide: SlideAssembly,
    ) -> None:
        slide_part = _package_part_name(
            Path("ppt") / "slides" / slide.filename,
            required_prefix=Path("ppt") / "slides",
        )
        parts[slide_part] = slide.slide_xml.encode("utf-8")
        self._trace_packaging(
            "slide_xml_written",
            metadata={"filename": slide.filename, "index": slide.index},
        )

        for part in slide.media:
            self._trace_packaging(
                "media_enqueued",
                metadata={
                    "relationship_id": part.relationship_id,
                    "filename": part.filename,
                    "content_type": part.content_type,
                },
            )
        for mask in slide.masks:
            self._trace_packaging(
                "mask_enqueued",
                metadata={
                    "relationship_id": mask.relationship_id,
                    "part_name": mask.part_name,
                },
            )

        safe_slide_filename = sanitize_slide_filename(slide.filename)
        rels_part = _package_part_name(
            Path("ppt") / "slides" / "_rels" / f"{safe_slide_filename}.rels",
            required_prefix=Path("ppt") / "slides" / "_rels",
        )
        parts[rels_part] = self._build_slide_relationships_xml(
            slide.filename,
            slide.media,
            slide.navigation,
            slide.masks,
        )
        self._trace_packaging(
            "slide_relationships_updated",
            metadata={
                "index": slide.index,
                "media_count": len(slide.media),
                "mask_count": len(slide.masks),
            },
        )

    def _load_base_parts(self) -> dict[str, bytes]:
        parts = dict(load_template_entries(self._base_template))
        parts.pop("ppt/slides/_rels/slide.xml.rels", None)
        theme_xml = parts.get("ppt/theme/theme1.xml")
        if theme_xml is not None:
            parts["ppt/theme/theme1.xml"] = ensure_theme_extension_xml(theme_xml)
        return parts

    def _write_media_payloads(
        self,
        parts: dict[str, bytes],
        media_parts: Sequence[PackagedMedia],
    ) -> None:
        for part in self._unique_media_parts(media_parts):
            part_name = _package_part_name(
                part.package_path,
                required_prefix=Path("ppt") / "media",
            )
            parts[part_name] = part.data
            self._trace_packaging(
                "media_part_written",
                metadata={
                    "filename": part.filename,
                    "content_type": part.content_type,
                },
                subject=part.relationship_id,
            )

    def _write_mask_payloads(
        self,
        parts: dict[str, bytes],
        mask_parts: Sequence[MaskAsset],
    ) -> None:
        for part in self._unique_mask_parts(mask_parts):
            part_name = _package_part_name(
                part.package_path,
                required_prefix=Path("ppt") / "masks",
            )
            parts[part_name] = part.data
            self._trace_packaging(
                "mask_part_written",
                metadata={"path": str(part.package_path)},
                subject=part.relationship_id,
            )

    def _write_font_payloads(
        self,
        parts: dict[str, bytes],
        font_assets: Sequence[FontAsset],
    ) -> list[PackagedFont]:
        reserved_filenames = {
            Path(part_name).name
            for part_name in parts
            if part_name.startswith("ppt/fonts/")
        }
        packaged_fonts, payloads = build_font_parts(
            font_assets,
            trace_packaging=self._trace_packaging,
            reserved_filenames=reserved_filenames,
        )
        for filename, font_bytes in payloads:
            parts[f"ppt/fonts/{filename}"] = font_bytes
        return packaged_fonts

    def _update_presentation_payloads(
        self,
        parts: dict[str, bytes],
        slides: Sequence[SlideAssembly],
        fonts: Sequence[PackagedFont],
        slide_size: tuple[int, int] | None,
    ) -> None:
        presentation_xml = parts.get("ppt/presentation.xml")
        rels_xml = parts.get("ppt/_rels/presentation.xml.rels")
        if presentation_xml is None or rels_xml is None:
            raise FileNotFoundError("PPTX scaffold is missing presentation parts.")
        parts["ppt/presentation.xml"], parts["ppt/_rels/presentation.xml.rels"] = (
            build_presentation_parts(
                presentation_xml,
                rels_xml,
                slides=slides,
                fonts=fonts,
                slide_size=slide_size,
                trace_packaging=self._trace_packaging,
            )
        )


def _package_part_name(package_path: Path, *, required_prefix: Path) -> str:
    parts = package_path.parts
    prefix_parts = required_prefix.parts
    if (
        package_path.is_absolute()
        or any(part in {"", ".", ".."} for part in parts)
        or parts[: len(prefix_parts)] != prefix_parts
    ):
        raise ValueError(f"Unsafe package part path {package_path!s}.")
    return "/".join(parts)


__all__ = ["PackageWriter"]
