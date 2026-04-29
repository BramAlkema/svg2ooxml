"""Page result assembly helpers for PPTX export."""

from __future__ import annotations

from typing import Any

from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.core.metadata import ensure_scene_variant_type, read_page_render_metadata
from svg2ooxml.core.pptx_exporter_types import SvgPageResult, SvgPageSource


def page_variant_type(page: SvgPageSource, default: str = "variant") -> str:
    """Return the variant type stored on a page source."""

    return read_page_render_metadata(
        page.metadata,
        default_variant_type=default,
    ).variant_type


def resolve_page_title(page: SvgPageSource, scene: IRScene, fallback: str) -> str:
    """Resolve the slide title from explicit page data, scene metadata, or fallback."""

    scene_title = (
        scene.metadata.get("page_title") if isinstance(scene.metadata, dict) else None
    )
    return page.title or scene_title or page.name or fallback


def attach_page_metadata(
    scene: IRScene,
    page: SvgPageSource,
    *,
    title: str,
    trace_report: dict[str, Any],
    variant_type: Any,
    include_page_metadata: bool = False,
) -> dict[str, Any] | None:
    """Store page trace and variant metadata on the rendered scene."""

    if not isinstance(scene.metadata, dict):
        return None

    scene.metadata.setdefault("page_title", title)
    scene.metadata.setdefault("trace_report", trace_report)
    if include_page_metadata and page.metadata:
        scene.metadata.setdefault("page_metadata", {}).update(page.metadata)
    ensure_scene_variant_type(scene.metadata, variant_type)
    return scene.metadata


def build_page_result(
    page: SvgPageSource,
    scene: IRScene,
    trace_report: dict[str, Any],
    *,
    fallback_title: str,
    variant_type: Any,
    include_page_metadata: bool = False,
) -> SvgPageResult:
    """Create the externally reported page result and update scene metadata."""

    title = resolve_page_title(page, scene, fallback_title)
    metadata = attach_page_metadata(
        scene,
        page,
        title=title,
        trace_report=trace_report,
        variant_type=variant_type,
        include_page_metadata=include_page_metadata,
    )
    return SvgPageResult(title=title, trace_report=trace_report, metadata=metadata)


__all__ = [
    "attach_page_metadata",
    "build_page_result",
    "page_variant_type",
    "resolve_page_title",
]
