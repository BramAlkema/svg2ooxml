"""Batch PPTX package writer."""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from svg2ooxml.common.boundaries import resolve_package_child
from svg2ooxml.common.tempfiles import temporary_directory
from svg2ooxml.drawingml.assets import FontAsset
from svg2ooxml.io.pptx_package_model import (
    MaskAsset,
    PackagedFont,
    PackagedMedia,
    SlideAssembly,
)
from svg2ooxml.io.pptx_package_parts import (
    ensure_theme_extension,
    inject_slide_layout_dimensions,
    write_content_types,
    write_required_presentation_parts,
    zip_package,
)
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
            with temporary_directory(prefix="svg2ooxml_pptx_") as temp_path:
                shutil.copytree(self._base_template, temp_path, dirs_exist_ok=True)
                ensure_theme_extension(temp_path)
                self._trace_packaging(
                    "packaging_start",
                    metadata={"slide_count": len(slides)},
                )

                slides_dir = temp_path / "ppt" / "slides"
                slides_dir.mkdir(parents=True, exist_ok=True)
                (slides_dir / "_rels").mkdir(exist_ok=True)
                template_slide_rels = slides_dir / "_rels" / "slide.xml.rels"
                if template_slide_rels.exists():
                    template_slide_rels.unlink()

                all_media: list[PackagedMedia] = []
                font_assets: list[FontAsset] = []
                all_masks: list[MaskAsset] = []
                packaged_fonts: list[PackagedFont] = []

                for slide in slides:
                    self._write_slide(temp_path, slides_dir, slide)
                    all_media.extend(slide.media)
                    font_assets.extend(slide.font_assets)
                    all_masks.extend(slide.masks)

                self._write_media_parts(temp_path, all_media)
                self._write_mask_parts(temp_path, all_masks)
                packaged_fonts = self._write_font_parts(temp_path, font_assets)

                presentation_slide_size = self._select_slide_size(
                    slides,
                    slide_size_mode=slide_size_mode,
                )
                self._update_presentation_parts(
                    temp_path,
                    slides,
                    packaged_fonts,
                    presentation_slide_size,
                )
                write_required_presentation_parts(
                    temp_path,
                    trace_packaging=self._trace_packaging,
                )
                inject_slide_layout_dimensions(temp_path, presentation_slide_size)
                write_content_types(
                    self._content_types_template,
                    temp_path,
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

                zip_package(temp_path, output)
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
        temp_path: Path,
        slides_dir: Path,
        slide: SlideAssembly,
    ) -> None:
        slide_path = resolve_package_child(
            temp_path,
            Path("ppt") / "slides" / slide.filename,
            required_prefix=Path("ppt") / "slides",
        )
        slide_path.write_text(slide.slide_xml, encoding="utf-8")
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

        self._write_slide_relationships(
            slides_dir,
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


__all__ = ["PackageWriter"]
