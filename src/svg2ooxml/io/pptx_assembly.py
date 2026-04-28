"""PPTX assembly facade and high-level building helpers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from svg2ooxml.common.boundaries import resolve_package_child, sanitize_package_filename
from svg2ooxml.drawingml.result import DrawingMLRenderResult
from svg2ooxml.io.pptx_package_constants import (
    ALLOWED_SLIDE_SIZE_MODES,
    ASSETS_ROOT,
    CONTENT_NS,
    FONT_STYLE_ORDER,
    FONT_STYLE_TAGS,
    MASK_CONTENT_TYPE,
    MASK_REL_TYPE,
    P_NS,
    R_DOC_NS,
    REL_NS,
    THEME_FAMILY_NS,
    THEME_NS,
)
from svg2ooxml.io.pptx_package_model import (
    MaskAsset,
    MaskMeta,
    MediaMeta,
    PackagedFont,
    PackagedMedia,
    SlideAssembly,
    SlideEntry,
)
from svg2ooxml.io.pptx_part_names import (
    content_type_for_extension,
    normalize_style_kind,
    safe_int,
    sanitize_mask_part_name,
    sanitize_media_filename,
    sanitize_slide_filename,
    suffix_for_content_type,
)
from svg2ooxml.io.pptx_slide_assembly import PackagingContext, SlideAssembler

if TYPE_CHECKING:  # pragma: no cover - typing only
    from svg2ooxml.core.ir import IRScene
    from svg2ooxml.core.tracing import ConversionTracer


class PPTXPackageBuilder:
    """Create PPTX packages using the clean-slate template library."""

    def __init__(self, *, assets_root: Path | None = None, slide_size_mode: str | None = None) -> None:
        self._assets_root = assets_root or ASSETS_ROOT
        self._base_template = self._assets_root / "clean_slate"
        self._content_types_template = (self._assets_root / "content_types.xml").read_text(encoding="utf-8")
        self._slide_rels_template = (
            self._base_template / "ppt" / "slides" / "_rels" / "slide.xml.rels"
        ).read_text(encoding="utf-8")
        from svg2ooxml.drawingml.writer import DrawingMLWriter

        self._writer = DrawingMLWriter(template_dir=self._assets_root)
        self._slide_size_mode = slide_size_mode

    def build(
        self,
        scene: IRScene,
        output_path: str | Path,
        *,
        tracer: ConversionTracer | None = None,
        persist_trace: bool | None = None,
    ) -> Path:
        """Materialise a PPTX file for the supplied IR scene."""
        return self.build_scenes([scene], output_path, tracer=tracer, persist_trace=persist_trace)

    def build_scenes(
        self,
        scenes: Sequence[IRScene],
        output_path: str | Path,
        *,
        tracer: ConversionTracer | None = None,
        persist_trace: bool | None = None,
    ) -> Path:
        """Materialise a PPTX file for a sequence of IR scenes."""
        render_results = []
        for scene in scenes:
            animation_payload = None
            if isinstance(scene.metadata, dict):
                animation_payload = scene.metadata.get("animation_raw")
            render_results.append(
                self._writer.render_scene_from_ir(
                    scene,
                    tracer=tracer,
                    animation_payload=animation_payload,
                )
            )
        return self.build_from_results(render_results, output_path, tracer=tracer, persist_trace=persist_trace)

    def build_from_results(
        self,
        render_results: Sequence[DrawingMLRenderResult],
        output_path: str | Path,
        *,
        tracer: ConversionTracer | None = None,
        persist_trace: bool | None = None,
        slide_size_mode: str | None = None,
    ) -> Path:
        """Package pre-rendered slides returned by DrawingMLWriter."""
        if not render_results:
            raise ValueError("At least one render result is required to build a PPTX package.")

        from svg2ooxml.io.pptx_writer import PackageWriter

        context = PackagingContext()
        slide_assemblies = SlideAssembler(
            context,
            slide_rels_template=self._slide_rels_template,
        ).assemble(render_results)
        package_writer = PackageWriter(
            base_template=self._base_template,
            content_types_template=self._content_types_template,
            slide_rels_template=self._slide_rels_template,
            slide_size_mode=self._slide_size_mode,
        )
        return package_writer.write_package(
            slide_assemblies,
            output_path,
            tracer=tracer,
            persist_trace=persist_trace,
            slide_size_mode=slide_size_mode,
        )

    def begin_streaming(
        self,
        *,
        tracer: ConversionTracer | None = None,
    ):
        """Create a streaming writer for incremental slide addition."""
        from svg2ooxml.io.pptx_writer import StreamingPackageWriter

        return StreamingPackageWriter(
            base_template=self._base_template,
            content_types_template=self._content_types_template,
            slide_rels_template=self._slide_rels_template,
            slide_size_mode=self._slide_size_mode,
            tracer=tracer,
        )


def write_pptx(scene: IRScene, output_path: str | Path) -> Path:
    """Public helper mirroring the historical API."""
    builder = PPTXPackageBuilder()
    return builder.build(scene, output_path)


__all__ = [
    "ALLOWED_SLIDE_SIZE_MODES",
    "ASSETS_ROOT",
    "CONTENT_NS",
    "FONT_STYLE_ORDER",
    "FONT_STYLE_TAGS",
    "MASK_REL_TYPE",
    "MASK_CONTENT_TYPE",
    "MaskAsset",
    "MaskMeta",
    "MediaMeta",
    "P_NS",
    "PPTXPackageBuilder",
    "PackagedFont",
    "PackagedMedia",
    "PackagingContext",
    "R_DOC_NS",
    "REL_NS",
    "SlideAssembler",
    "SlideAssembly",
    "SlideEntry",
    "THEME_FAMILY_NS",
    "THEME_NS",
    "content_type_for_extension",
    "normalize_style_kind",
    "resolve_package_child",
    "safe_int",
    "sanitize_mask_part_name",
    "sanitize_media_filename",
    "sanitize_package_filename",
    "sanitize_slide_filename",
    "suffix_for_content_type",
    "write_pptx",
]
