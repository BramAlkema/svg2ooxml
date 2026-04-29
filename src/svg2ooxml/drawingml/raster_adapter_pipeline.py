"""Filter pipeline and source-surface rendering for raster fallbacks."""

from __future__ import annotations

from copy import deepcopy

from lxml import etree

from svg2ooxml.drawingml.raster_adapter_optional import (
    _DEFAULT_PLACEHOLDER_SIZE,
    adapter_skia,
)
from svg2ooxml.drawingml.skia_bridge import (
    NUMPY_AVAILABLE,
    render_surface_from_descriptor,
)


class RasterAdapterPipelineMixin:
    """Render full resvg filter pipelines and source graphics."""

    def _render_surface_with_filter_pipeline(
        self,
        *,
        filter_element: etree._Element,
        context,
    ):
        skia = adapter_skia()
        if skia is None or not NUMPY_AVAILABLE:
            return None
        try:
            from svg2ooxml.filters.planner import FilterPlanner
            from svg2ooxml.filters.resvg_bridge import resolve_filter_element
            from svg2ooxml.render.filters import apply_filter
        except Exception:  # pragma: no cover - optional render path
            return None

        try:
            resolved_filter = resolve_filter_element(filter_element)
        except Exception:
            return None

        planner = FilterPlanner()
        options = getattr(context, "options", None)
        if not isinstance(options, dict):
            options = {}

        plan = planner.build_resvg_plan(resolved_filter, options=options)
        if plan is None:
            return None

        try:
            bounds = planner.resvg_bounds(options, resolved_filter)
            viewport = planner.resvg_viewport(bounds)
        except Exception:
            return None
        if self._safe_raster_size(
            (viewport.width, viewport.height),
            default=_DEFAULT_PLACEHOLDER_SIZE,
        ) != (viewport.width, viewport.height):
            return None

        source_surface = self.render_source_surface(
            width_px=viewport.width,
            height_px=viewport.height,
            context=context,
        )
        if source_surface is None:
            return None

        try:
            return apply_filter(source_surface, plan, bounds, viewport)
        except Exception:
            return None

    def render_source_surface(
        self,
        *,
        width_px: int,
        height_px: int,
        context,
    ):
        """Render the unfiltered source element subtree into a surface."""

        skia = adapter_skia()
        if skia is None or not NUMPY_AVAILABLE:
            return None
        width_px, height_px = self._safe_raster_size(
            (width_px, height_px),
            default=_DEFAULT_PLACEHOLDER_SIZE,
        )
        source_descriptor = self._source_graphic_descriptor_from_context(context)
        descriptor, bounds = self._descriptor_payload(context)
        if isinstance(source_descriptor, dict):
            surface = render_surface_from_descriptor(
                descriptor=source_descriptor,
                bounds=bounds,
                width_px=width_px,
                height_px=height_px,
            )
            if surface is not None:
                return surface
        try:
            from svg2ooxml.core.resvg.normalizer import normalize_svg_string
            from svg2ooxml.core.resvg.parser.options import build_default_options
            from svg2ooxml.render.pipeline import render
        except Exception:  # pragma: no cover - renderer dependencies missing
            return None

        source_element = self._source_element_from_context(context)
        if source_element is None:
            return None

        source_root = None
        try:
            source_root = source_element.getroottree().getroot()
        except Exception:
            source_root = None

        svg_markup = self._build_source_svg_markup(
            source_element=source_element,
            source_root=source_root,
            descriptor=descriptor,
            bounds=bounds,
            width_px=width_px,
            height_px=height_px,
        )
        if svg_markup is None:
            return None

        resources_dir, asset_root = self._resource_roots_from_context(context)

        try:
            options = build_default_options(
                resources_dir=resources_dir,
                asset_root=asset_root,
            )
            normalized = normalize_svg_string(svg_markup, options=options)
            return render(normalized.tree)
        except Exception:  # pragma: no cover - renderer failure
            return None

    def _render_preview_with_resvg(
        self,
        filter_element,
        filter_id: str,
        width_px: int,
        height_px: int,
        context=None,
    ):
        skia = adapter_skia()
        if skia is None or not NUMPY_AVAILABLE:
            return None
        width_px, height_px = self._safe_raster_size(
            (width_px, height_px),
            default=_DEFAULT_PLACEHOLDER_SIZE,
        )
        try:
            from svg2ooxml.core.resvg.normalizer import normalize_svg_string
            from svg2ooxml.core.resvg.parser.options import build_default_options
            from svg2ooxml.render.pipeline import render
        except Exception:  # pragma: no cover - renderer dependencies missing
            return None

        try:
            filter_clone = deepcopy(filter_element)
        except Exception:
            return None

        svg_ns = "http://www.w3.org/2000/svg"
        if not isinstance(filter_clone.tag, str) or "}" not in filter_clone.tag:
            filter_clone.tag = f"{{{svg_ns}}}filter"

        preview_filter_id = f"svg2ooxml_filter_{self._counter + 1}"
        filter_clone.set("id", preview_filter_id)

        svg_markup = self._build_preview_svg_markup(
            filter_clone=filter_clone,
            preview_filter_id=preview_filter_id,
            width_px=width_px,
            height_px=height_px,
            context=context,
        )

        resources_dir, asset_root = self._resource_roots_from_context(context)

        try:
            options = build_default_options(
                resources_dir=resources_dir,
                asset_root=asset_root,
            )
            normalized = normalize_svg_string(svg_markup, options=options)
            return render(normalized.tree)
        except Exception:  # pragma: no cover - renderer failure
            return None



__all__ = ["RasterAdapterPipelineMixin"]
