"""Bounds and descriptor helpers for raster filter fallbacks."""

from __future__ import annotations

from typing import Any

from lxml import etree

from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.drawingml.paint_converter import _coerce_positive, _is_number


def source_graphic_descriptor_from_context(context) -> dict[str, Any] | None:
    options = getattr(context, "options", None)
    if not isinstance(options, dict):
        return None
    filter_inputs = options.get("filter_inputs")
    if not isinstance(filter_inputs, dict):
        return None
    source_graphic = filter_inputs.get("SourceGraphic")
    if isinstance(source_graphic, dict):
        return dict(source_graphic)
    return None


def derive_dimensions(
    context,
    defaults: tuple[int, int],
    descriptor: dict[str, Any] | None,
    bounds: dict[str, float | Any] | None,
) -> tuple[int, int]:
    width, height = defaults
    if context is not None:
        options = getattr(context, "options", None)
        if isinstance(options, dict):
            bbox = options.get("ir_bbox")
            if isinstance(bbox, dict):
                try:
                    width = max(1.0, float(bbox.get("width", width)))
                    height = max(1.0, float(bbox.get("height", height)))
                except (TypeError, ValueError):
                    pass
    if bounds:
        width = max(width, _coerce_positive(bounds.get("width"), width))
        height = max(height, _coerce_positive(bounds.get("height"), height))
    width *= viewport_scale(descriptor)
    height *= viewport_scale(descriptor)
    return int(min(width, 1024)), int(min(height, 1024))


def resolved_filter_bounds(
    *,
    descriptor: dict[str, Any] | None,
    bounds: dict[str, float | Any] | None,
    default_width: float,
    default_height: float,
) -> dict[str, float] | None:
    if isinstance(bounds, dict):
        try:
            x = float(bounds.get("x", 0.0))
            y = float(bounds.get("y", 0.0))
            width = max(1.0, float(bounds.get("width", default_width)))
            height = max(1.0, float(bounds.get("height", default_height)))
        except (TypeError, ValueError):
            x = 0.0
            y = 0.0
            width = max(1.0, float(default_width))
            height = max(1.0, float(default_height))
    else:
        x = 0.0
        y = 0.0
        width = max(1.0, float(default_width))
        height = max(1.0, float(default_height))

    region = (descriptor or {}).get("filter_region") if descriptor else None
    units = (descriptor or {}).get("filter_units") if descriptor else None
    if isinstance(region, dict):
        base_width = width
        base_height = height
        if units == "objectBoundingBox":
            rx = parse_object_bbox_region_value(region.get("x"), reference=base_width)
            ry = parse_object_bbox_region_value(region.get("y"), reference=base_height)
            rw = parse_object_bbox_region_value(region.get("width"), reference=base_width)
            rh = parse_object_bbox_region_value(region.get("height"), reference=base_height)
            if rx is not None:
                x += rx
            if ry is not None:
                y += ry
            if rw is not None and rw > 0:
                width = rw
            if rh is not None and rh > 0:
                height = rh
        else:
            rx = parse_region_value(region.get("x"), reference=base_width)
            ry = parse_region_value(region.get("y"), reference=base_height)
            rw = parse_region_value(region.get("width"), reference=base_width)
            rh = parse_region_value(region.get("height"), reference=base_height)
            if rx is not None:
                x = rx
            if ry is not None:
                y = ry
            if rw is not None and rw > 0:
                width = rw
            if rh is not None and rh > 0:
                height = rh

    return {"x": x, "y": y, "width": width, "height": height}


def parse_region_value(value: object, *, reference: float) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        token = value.strip()
        if token.endswith("%"):
            try:
                return (float(token[:-1]) / 100.0) * reference
            except ValueError:
                return None
    if _is_number(value):
        return float(value)
    return None


def parse_object_bbox_region_value(
    value: object,
    *,
    reference: float,
) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        token = value.strip()
        if token.endswith("%"):
            try:
                return (float(token[:-1]) / 100.0) * reference
            except ValueError:
                return None
    if _is_number(value):
        return float(value) * reference
    return None


def descriptor_payload(
    context,
) -> tuple[dict[str, Any] | None, dict[str, float | Any] | None]:
    if context is None:
        return None, None
    options = getattr(context, "options", None)
    if not isinstance(options, dict):
        return None, None
    descriptor = options.get("resvg_descriptor")
    if isinstance(descriptor, dict):
        descriptor = dict(descriptor)
    else:
        descriptor = None
    bounds = options.get("ir_bbox")
    if isinstance(bounds, dict):
        bounds = {
            key: float(bounds[key])
            for key in ("x", "y", "width", "height")
            if key in bounds and _is_number(bounds[key])
        }
    else:
        bounds = None
    return descriptor, bounds


def descriptor_from_filter_element(
    filter_element: etree._Element | None,
    filter_id: str,
) -> dict[str, Any] | None:
    if not isinstance(filter_element, etree._Element):
        return None
    region = {
        key: filter_element.get(key)
        for key in ("x", "y", "width", "height")
        if filter_element.get(key) is not None
    }
    primitive_tags: list[str] = []
    for child in filter_element:
        if not isinstance(child.tag, str):
            continue
        primitive_tags.append(local_name(child.tag))
    if not region and not primitive_tags and not filter_element.attrib:
        return None
    return {
        "filter_id": filter_id,
        "filter_units": filter_element.get("filterUnits", "objectBoundingBox"),
        "primitive_units": filter_element.get("primitiveUnits", "userSpaceOnUse"),
        "primitive_tags": primitive_tags,
        "filter_region": region,
    }


def viewport_scale(descriptor: dict[str, Any] | None) -> float:
    if not descriptor:
        return 1.0
    units = descriptor.get("filter_units")
    if units == "objectBoundingBox":
        return 1.1
    return 1.0


def pass_count(descriptor: dict[str, Any] | None, complexity: int) -> int:
    if not descriptor:
        return min(3, max(1, complexity))
    passes = descriptor.get("render_passes")
    if isinstance(passes, int) and passes > 0:
        return min(6, passes)
    return min(6, max(1, complexity))


def scale_factor(
    descriptor: dict[str, Any] | None,
    bounds: dict[str, float | Any] | None,
    complexity: int,
) -> float:
    scale = 1.0
    if descriptor:
        region = descriptor.get("filter_region")
        if isinstance(region, dict):
            width = _coerce_positive(region.get("width"))
            height = _coerce_positive(region.get("height"))
            if width and height:
                base = max(width, height)
                if base > 1.5:
                    scale = min(2.5, 1.0 + base * 0.15)
    if bounds:
        max_dim = max(
            _coerce_positive(bounds.get("width"), 1.0),
            _coerce_positive(bounds.get("height"), 1.0),
        )
        scale = max(scale, min(3.0, 1.0 + max_dim / 320.0))
    scale = max(scale, 1.0 + min(complexity, 6) * 0.08)
    return float(scale)


__all__ = [
    "derive_dimensions",
    "descriptor_from_filter_element",
    "descriptor_payload",
    "parse_object_bbox_region_value",
    "parse_region_value",
    "pass_count",
    "resolved_filter_bounds",
    "scale_factor",
    "source_graphic_descriptor_from_context",
    "viewport_scale",
]
