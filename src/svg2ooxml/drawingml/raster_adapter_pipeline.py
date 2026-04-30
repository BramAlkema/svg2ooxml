"""Filter pipeline and source-surface rendering for raster fallbacks."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.drawingml.raster_adapter_optional import (
    _DEFAULT_PLACEHOLDER_SIZE,
    adapter_skia,
)
from svg2ooxml.drawingml.raster_filter_transform import (
    matrix_from_options,
    scale_plan_user_space_primitives,
    transform_user_space_bounds,
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
        else:
            options = dict(options)

        background_inputs = _filter_background_inputs(resolved_filter)
        if background_inputs:
            available = set(_iter_available_filter_inputs(options))
            available.update(background_inputs)
            options["available_filter_inputs"] = sorted(available)

        plan = planner.build_resvg_plan(resolved_filter, options=options)
        if plan is None:
            return None

        try:
            filter_bounds = planner.resvg_bounds(options, resolved_filter)
            ctm = matrix_from_options(options)
            if resolved_filter.filter_units == "userSpaceOnUse":
                filter_bounds = transform_user_space_bounds(filter_bounds, ctm)
            if resolved_filter.primitive_units == "userSpaceOnUse":
                scale_plan_user_space_primitives(plan, ctm)
            options["resvg_descriptor"] = _descriptor_payload_from_resolved_filter(
                resolved_filter,
                bounds=filter_bounds,
            )
            render_context = _context_with_options(context, options)
            source_bounds = _source_bounds_from_options(options, filter_bounds)
            viewport = planner.resvg_viewport(filter_bounds)
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
            context=render_context,
        )
        if source_surface is None:
            return None

        input_surfaces = {}
        if background_inputs:
            background_surface = self.render_background_surface(
                width_px=viewport.width,
                height_px=viewport.height,
                context=render_context,
            )
            if background_surface is None:
                return None
            if "BackgroundImage" in background_inputs:
                input_surfaces["BackgroundImage"] = background_surface
            if "BackgroundAlpha" in background_inputs:
                try:
                    from svg2ooxml.render import filters_ops as _ops
                except Exception:
                    return None
                input_surfaces["BackgroundAlpha"] = _ops.extract_alpha(
                    background_surface
                )

        try:
            return apply_filter(
                source_surface,
                plan,
                source_bounds,
                viewport,
                input_surfaces=input_surfaces,
            )
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
        resolved_bounds = self._resolved_filter_bounds(
            descriptor=descriptor,
            bounds=bounds,
            default_width=width_px,
            default_height=height_px,
        )
        if isinstance(source_descriptor, dict):
            surface = render_surface_from_descriptor(
                descriptor=source_descriptor,
                bounds=resolved_bounds,
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

    def render_background_surface(
        self,
        *,
        width_px: int,
        height_px: int,
        context,
    ):
        """Render previously painted siblings for SVG BackgroundImage inputs."""

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

        source_element = self._source_element_from_context(context)
        if source_element is None:
            return None

        source_root = None
        try:
            source_root = source_element.getroottree().getroot()
        except Exception:
            source_root = None

        descriptor, bounds = self._descriptor_payload(context)
        svg_markup = self._build_background_svg_markup(
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


class _ContextOptionsProxy:
    """Expose adjusted options while delegating other context attributes."""

    def __init__(self, base: Any, options: dict[str, Any]) -> None:
        self._base = base
        self.options = options

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)


def _context_with_options(context: Any, options: dict[str, Any]) -> Any:
    if context is None:
        return None
    try:
        return replace(context, options=options)
    except TypeError:
        return _ContextOptionsProxy(context, options)
    except Exception:
        return _ContextOptionsProxy(context, options)


def _descriptor_payload_from_resolved_filter(
    resolved_filter: Any,
    *,
    bounds: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    primitives = list(getattr(resolved_filter, "primitives", ()) or ())
    if bounds is None:
        region = dict(getattr(resolved_filter, "region", None) or {})
    else:
        x0, y0, x1, y1 = bounds
        region = {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}
    return {
        "filter_id": getattr(resolved_filter, "filter_id", None),
        "filter_units": getattr(resolved_filter, "filter_units", None),
        "primitive_units": getattr(resolved_filter, "primitive_units", None),
        "primitive_count": len(primitives),
        "primitive_tags": [getattr(primitive, "tag", "") for primitive in primitives],
        "filter_region": region,
    }


def _filter_background_inputs(resolved_filter: Any) -> set[str]:
    inputs: set[str] = set()
    for primitive in getattr(resolved_filter, "primitives", ()):
        _collect_background_inputs(primitive, inputs)
    return inputs


def _collect_background_inputs(primitive: Any, inputs: set[str]) -> None:
    attributes = getattr(primitive, "attributes", None)
    if isinstance(attributes, dict):
        for key in ("in", "in2"):
            value = attributes.get(key)
            if value in {"BackgroundImage", "BackgroundAlpha"}:
                inputs.add(value)
    children = getattr(primitive, "children", ())
    if isinstance(children, Iterable):
        for child in children:
            _collect_background_inputs(child, inputs)


def _iter_available_filter_inputs(options: dict[str, Any]) -> set[str]:
    raw = options.get("available_filter_inputs")
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return set()
    return {value.strip() for value in raw if isinstance(value, str) and value.strip()}


def _source_bounds_from_options(
    options: dict[str, Any],
    fallback: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    bbox = options.get("ir_bbox")
    if not isinstance(bbox, dict):
        return fallback
    try:
        x = float(bbox.get("x", fallback[0]))
        y = float(bbox.get("y", fallback[1]))
        width = float(bbox.get("width", fallback[2] - fallback[0]))
        height = float(bbox.get("height", fallback[3] - fallback[1]))
    except (TypeError, ValueError):
        return fallback
    if width <= 0 or height <= 0:
        return fallback
    return (x, y, x + width, y + height)
