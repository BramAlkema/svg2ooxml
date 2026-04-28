"""Rendering helpers mixed into :mod:`svg2ooxml.drawingml.raster_adapter`."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lxml import etree

from svg2ooxml.drawingml.raster_bounds import resolved_filter_bounds
from svg2ooxml.drawingml.skia_bridge import (
    NUMPY_AVAILABLE,
    draw_bounds,
    palette_for_primitives,
    render_caption,
    render_gradient_passes,
    render_surface_from_descriptor,
)

_DEFAULT_PLACEHOLDER_SIZE = (64, 64)


def _adapter_skia():
    from svg2ooxml.drawingml import raster_adapter

    return raster_adapter.skia


class RasterAdapterRenderingMixin:
    """Optional skia/resvg render paths for ``RasterAdapter``."""

    def _render_surface_with_filter_pipeline(
        self,
        *,
        filter_element: etree._Element,
        context,
    ):
        skia = _adapter_skia()
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

        skia = _adapter_skia()
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
        skia = _adapter_skia()
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

    def _build_preview_svg_markup(
        self,
        *,
        filter_clone: etree._Element,
        preview_filter_id: str,
        width_px: int,
        height_px: int,
        context,
    ) -> str:
        width_px, height_px = self._safe_raster_size(
            (width_px, height_px),
            default=_DEFAULT_PLACEHOLDER_SIZE,
        )
        descriptor, bounds = self._descriptor_payload(context)
        resolved_bounds = self._resolved_filter_bounds(
            descriptor=descriptor,
            bounds=bounds,
            default_width=width_px,
            default_height=height_px,
        )
        return self._preview_builder.build_preview_svg_markup(
            filter_clone=filter_clone,
            preview_filter_id=preview_filter_id,
            width_px=width_px,
            height_px=height_px,
            context=context,
            resolved_bounds=resolved_bounds,
        )

    def _build_source_svg_markup(
        self,
        *,
        source_element: etree._Element,
        source_root: etree._Element | None,
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
        width_px: int,
        height_px: int,
    ) -> str | None:
        width_px, height_px = self._safe_raster_size(
            (width_px, height_px),
            default=_DEFAULT_PLACEHOLDER_SIZE,
        )
        resolved_bounds = self._resolved_filter_bounds(
            descriptor=descriptor,
            bounds=bounds,
            default_width=width_px,
            default_height=height_px,
        )
        return self._preview_builder.build_source_svg_markup(
            source_element=source_element,
            source_root=source_root,
            resolved_bounds=resolved_bounds,
            width_px=width_px,
            height_px=height_px,
        )

    def _source_element_from_context(self, context) -> etree._Element | None:
        return self._preview_builder.source_element_from_context(context)

    def _iter_defs_children(self, source_root: etree._Element) -> list[etree._Element]:
        return self._preview_builder.iter_defs_children(source_root)

    def _build_source_subtree(
        self,
        *,
        source_element: etree._Element | None,
        source_root: etree._Element | None,
        preview_filter_id: str | None,
        svg_ns: str,
    ) -> etree._Element | None:
        return self._preview_builder.build_source_subtree(
            source_element=source_element,
            source_root=source_root,
            preview_filter_id=preview_filter_id,
            svg_ns=svg_ns,
        )

    def _rewrite_filter_reference(
        self, element: etree._Element, preview_filter_id: str | None
    ) -> None:
        self._preview_builder.rewrite_filter_reference(element, preview_filter_id)

    def _preview_viewbox(
        self,
        *,
        bounds: dict[str, float | Any] | None,
        width_px: int,
        height_px: int,
        preserve_user_space: bool = False,
    ) -> str:
        return self._preview_builder.preview_viewbox(
            bounds=bounds,
            width_px=width_px,
            height_px=height_px,
            preserve_user_space=preserve_user_space,
        )

    def _localize_source_subtree(
        self,
        source_subtree: etree._Element,
        bounds: dict[str, float | Any] | None,
        svg_ns: str,
        *,
        preserve_user_space: bool = False,
    ) -> etree._Element:
        del svg_ns
        return self._preview_builder.localize_source_subtree(
            source_subtree,
            bounds,
            preserve_user_space=preserve_user_space,
        )

    def _flatten_transforms_in_place(
        self,
        element: etree._Element,
        inherited_transform: str = "",
    ) -> None:
        self._preview_builder.flatten_transforms_in_place(element, inherited_transform)

    def _requires_original_user_space(
        self,
        source_subtree: etree._Element,
        source_root: etree._Element | None,
    ) -> bool:
        return self._preview_builder.requires_original_user_space(
            source_subtree,
            source_root,
        )

    def _render_placeholder_preview(
        self,
        *,
        filter_id: str,
        filter_element,
        primitive_tags: tuple[str, ...],
        filter_units,
        primitive_units,
        complexity: int,
        width_px: int,
        height_px: int,
        passes: int,
        scale: float,
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
        default_size: tuple[int, int],
    ):
        skia = _adapter_skia()
        default_size = self._safe_raster_size(
            default_size,
            default=_DEFAULT_PLACEHOLDER_SIZE,
        )
        width_px, height_px = self._safe_raster_size(
            (width_px, height_px),
            default=default_size,
        )
        if skia is None:
            return self._generate_filter_placeholder(
                filter_id=filter_id,
                primitive_tags=primitive_tags,
                filter_units=filter_units,
                primitive_units=primitive_units,
                complexity=complexity,
                default_size=default_size,
            )

        try:
            surface = skia.Surface(int(max(1, width_px)), int(max(1, height_px)))
        except Exception:  # pragma: no cover - defensive
            return self._generate_filter_placeholder(
                filter_id=filter_id,
                primitive_tags=primitive_tags,
                filter_units=filter_units,
                primitive_units=primitive_units,
                complexity=complexity,
                default_size=default_size,
            )

        canvas = surface.getCanvas()
        canvas.clear(skia.Color4f(0.0, 0.0, 0.0, 0.0))

        palette = palette_for_primitives(
            primitive_tags,
            seed=self._stable_seed(filter_id),
        )
        render_gradient_passes(
            canvas,
            width_px,
            height_px,
            palette,
            passes=passes,
            scale=scale,
            descriptor=descriptor,
            bounds=bounds,
        )

        if bounds:
            draw_bounds(canvas, bounds, width_px, height_px, palette)

        filter_tag = getattr(filter_element, "tag", "")
        filter_name = (
            filter_tag.split("}")[-1] if isinstance(filter_tag, str) else "filter"
        )
        render_caption(canvas, width_px, height_px, filter_name, primitive_tags, passes)

        image = surface.makeImageSnapshot()
        if image is None:
            return self._generate_filter_placeholder(
                filter_id=filter_id,
                primitive_tags=primitive_tags,
                filter_units=filter_units,
                primitive_units=primitive_units,
                complexity=complexity,
                default_size=default_size,
            )

        encoded = image.encodeToData()
        if encoded is None:
            return self._generate_filter_placeholder(
                filter_id=filter_id,
                primitive_tags=primitive_tags,
                filter_units=filter_units,
                primitive_units=primitive_units,
                complexity=complexity,
                default_size=default_size,
            )

        self._counter += 1
        relationship_id = f"rIdRaster{self._counter}"
        metadata = {
            "filter_id": filter_id,
            "renderer": "skia",
            "filter_tag": filter_name,
            "width_px": width_px,
            "height_px": height_px,
            "primitives": primitive_tags,
            "filter_units": filter_units,
            "primitive_units": primitive_units,
            "render_passes": passes,
            "scale_factor": scale,
            "complexity": complexity,
        }
        if descriptor:
            metadata["descriptor"] = descriptor
        if bounds:
            metadata["bounds"] = bounds
        return self._raster_result(
            image_bytes=bytes(encoded),
            relationship_id=relationship_id,
            width_px=width_px,
            height_px=height_px,
            metadata=metadata,
        )

    def _resolved_filter_bounds(
        self,
        *,
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
        default_width: float,
        default_height: float,
    ) -> dict[str, float] | None:
        return resolved_filter_bounds(
            descriptor=descriptor,
            bounds=bounds,
            default_width=default_width,
            default_height=default_height,
        )
