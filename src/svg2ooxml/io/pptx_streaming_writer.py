"""Streaming PPTX package writer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from svg2ooxml.common.boundaries import resolve_package_child
from svg2ooxml.common.tempfiles import temporary_directory
from svg2ooxml.drawingml.assets import FontAsset
from svg2ooxml.io.pptx_package_model import (
    MaskMeta,
    MediaMeta,
    PackagedFont,
    SlideEntry,
)
from svg2ooxml.io.pptx_package_parts import (
    ensure_theme_extension,
    inject_slide_layout_dimensions,
    write_content_types,
    write_required_presentation_parts,
    zip_package,
)
from svg2ooxml.io.pptx_slide_assembly import PackagingContext, SlideAssembler
from svg2ooxml.io.pptx_template_cache import copy_template_tree
from svg2ooxml.io.pptx_writer_base import PackageWriterBase

if TYPE_CHECKING:  # pragma: no cover - typing only
    from svg2ooxml.core.tracing import ConversionTracer
    from svg2ooxml.drawingml.result import DrawingMLRenderResult


class StreamingPackageWriter(PackageWriterBase):
    """Write PPTX packages one slide at a time with O(1) memory."""

    def __init__(
        self,
        *,
        tracer: ConversionTracer | None = None,
        base_template: Path,
        content_types_template: str,
        slide_rels_template: str,
        slide_size_mode: str | None = None,
    ) -> None:
        super().__init__(
            base_template=base_template,
            content_types_template=content_types_template,
            slide_rels_template=slide_rels_template,
            slide_size_mode=slide_size_mode,
        )
        self._tracer = tracer
        self._temp_path: Path | None = None
        self._temp_dir_ctx: object | None = None
        self._slides_dir: Path | None = None
        self._context: PackagingContext | None = None
        self._assembler: SlideAssembler | None = None
        self._slide_entries: list[SlideEntry] = []
        self._media_meta: list[MediaMeta] = []
        self._mask_meta: list[MaskMeta] = []
        self._font_assets: list[FontAsset] = []
        self._packaged_fonts: list[PackagedFont] = []
        self._slide_index = 0
        self._begun = False
        self._finalized = False

    def begin(self) -> None:
        if self._begun:
            raise RuntimeError("begin() already called")

        self._context = PackagingContext()
        self._assembler = SlideAssembler(
            self._context,
            slide_rels_template=self._slide_rels_template,
        )
        self._temp_dir_ctx = temporary_directory(prefix="svg2ooxml_pptx_")
        self._temp_path = self._temp_dir_ctx.__enter__()
        copy_template_tree(self._base_template, self._temp_path)
        ensure_theme_extension(self._temp_path)

        self._slides_dir = self._temp_path / "ppt" / "slides"
        self._slides_dir.mkdir(parents=True, exist_ok=True)
        (self._slides_dir / "_rels").mkdir(exist_ok=True)
        template_rels = self._slides_dir / "_rels" / "slide.xml.rels"
        if template_rels.exists():
            template_rels.unlink()

        self._begun = True
        self._trace_packaging("packaging_start", metadata={"streaming": True})

    def add_slide(self, result: DrawingMLRenderResult) -> None:
        if not self._begun:
            raise RuntimeError("begin() must be called before add_slide()")
        if self._finalized:
            raise RuntimeError("Cannot add slides after finalize()")
        if self._assembler is None or self._temp_path is None or self._slides_dir is None:
            raise RuntimeError("Streaming writer was not initialized")

        self._slide_index += 1
        assembly = self._assembler.assemble_one(result, self._slide_index)

        slide_path = resolve_package_child(
            self._temp_path,
            Path("ppt") / "slides" / assembly.filename,
            required_prefix=Path("ppt") / "slides",
        )
        slide_path.write_text(assembly.slide_xml, encoding="utf-8")
        self._trace_packaging(
            "slide_xml_written",
            metadata={"filename": assembly.filename, "index": assembly.index},
        )

        self._write_slide_relationships(
            self._slides_dir,
            assembly.filename,
            assembly.media,
            assembly.navigation,
            assembly.masks,
        )

        if assembly.media:
            self._write_media_parts(self._temp_path, assembly.media)
            self._media_meta.extend(
                MediaMeta(filename=part.filename, content_type=part.content_type)
                for part in assembly.media
            )

        if assembly.masks:
            self._write_mask_parts(self._temp_path, assembly.masks)
            self._mask_meta.extend(
                MaskMeta(part_name=mask.part_name, content_type=mask.content_type)
                for mask in assembly.masks
            )

        self._font_assets.extend(assembly.font_assets)
        self._slide_entries.append(
            SlideEntry(
                index=assembly.index,
                filename=assembly.filename,
                rel_id=assembly.rel_id,
                slide_id=assembly.slide_id,
                slide_size=assembly.slide_size,
            )
        )

    def finalize(self, output_path: str | Path) -> Path:
        if not self._begun:
            raise RuntimeError("begin() must be called before finalize()")
        if self._finalized:
            raise RuntimeError("finalize() already called")
        if not self._slide_entries:
            raise ValueError("At least one slide must be added before finalize()")
        if self._temp_path is None:
            raise RuntimeError("Streaming writer temp package is missing")

        self._finalized = True
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        try:
            presentation_slide_size = self._select_slide_size(
                self._slide_entries,
                slide_size_mode=None,
            )
            self._packaged_fonts = self._write_font_parts(
                self._temp_path,
                self._font_assets,
            )
            self._update_presentation_parts(
                self._temp_path,
                self._slide_entries,
                self._packaged_fonts,
                presentation_slide_size,
            )
            write_required_presentation_parts(
                self._temp_path,
                trace_packaging=self._trace_packaging,
            )
            inject_slide_layout_dimensions(self._temp_path, presentation_slide_size)
            write_content_types(
                self._content_types_template,
                self._temp_path,
                self._slide_entries,
                self._media_meta,
                self._packaged_fonts,
                self._mask_meta,
            )
            zip_package(self._temp_path, output)
            self._trace_packaging("pptx_written", metadata={"path": str(output)})
            return output
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        if self._temp_dir_ctx is not None:
            self._temp_dir_ctx.__exit__(None, None, None)
            self._temp_dir_ctx = None
            self._temp_path = None

    def __enter__(self) -> StreamingPackageWriter:
        self.begin()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._cleanup()


__all__ = ["StreamingPackageWriter"]
