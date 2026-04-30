"""Transform-aware stroke width policy helpers."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.core.styling.style_helpers import parse_style_attr


def apply_transform_stroke_width_policy(
    style: StyleResult,
    *,
    element: etree._Element | None,
    matrix: Any,
    metadata: dict[str, Any] | None = None,
    tolerance: float = 1e-6,
) -> StyleResult:
    """Scale normal SVG strokes when geometry has already been transformed.

    Native DrawingML line width does not scale with transformed geometry. Most
    shape converters bake SVG transforms into coordinates, so normal SVG stroke
    widths must be multiplied by the effective CTM scale. SVG
    ``vector-effect: non-scaling-stroke`` deliberately opts out.
    """

    stroke = style.stroke
    if stroke is None or stroke.width <= 0.0:
        _record_vector_effect(style, element, metadata)
        return style

    vector_effect = _vector_effect(style, element)
    if metadata is not None and vector_effect != "none":
        metadata["vector_effect"] = vector_effect
    if vector_effect == "non-scaling-stroke":
        _record_stroke_policy(
            metadata,
            policy="non-scaling-stroke",
            original_width=stroke.width,
            scale=1.0,
            adjusted_width=stroke.width,
        )
        return style

    scale = effective_stroke_scale(matrix, tolerance=tolerance)
    if abs(scale - 1.0) <= tolerance:
        return style

    adjusted_width = max(0.0, stroke.width * scale)
    _record_stroke_policy(
        metadata,
        policy="scaled-with-transform",
        original_width=stroke.width,
        scale=scale,
        adjusted_width=adjusted_width,
    )
    return replace(style, stroke=replace(stroke, width=adjusted_width))


def effective_stroke_scale(matrix: Any, *, tolerance: float = 1e-6) -> float:
    """Return a scalar stroke approximation for a 2D transform matrix."""

    if matrix is None:
        return 1.0
    try:
        a = float(matrix.a)
        b = float(matrix.b)
        c = float(matrix.c)
        d = float(matrix.d)
    except (AttributeError, TypeError, ValueError):
        return 1.0

    scale_x = math.hypot(a, b)
    scale_y = math.hypot(c, d)
    if scale_x <= tolerance and scale_y <= tolerance:
        return 1.0
    if scale_x <= tolerance:
        return scale_y
    if scale_y <= tolerance:
        return scale_x

    determinant = abs(a * d - b * c)
    if determinant > tolerance:
        return math.sqrt(determinant)
    return (scale_x + scale_y) / 2.0


def _vector_effect(style: StyleResult, element: etree._Element | None) -> str:
    metadata = style.metadata if isinstance(style.metadata, dict) else {}
    token = metadata.get("vector_effect")
    if isinstance(token, str) and token.strip():
        return token.strip()

    if element is not None:
        attr = element.get("vector-effect")
        if isinstance(attr, str) and attr.strip():
            return attr.strip()
        style_attr = element.get("style")
        if isinstance(style_attr, str) and "vector-effect" in style_attr:
            parsed = parse_style_attr(style_attr)
            parsed_value = parsed.get("vector-effect")
            if isinstance(parsed_value, str) and parsed_value.strip():
                return parsed_value.strip()

    return "none"


def _record_vector_effect(
    style: StyleResult,
    element: etree._Element | None,
    metadata: dict[str, Any] | None,
) -> None:
    if metadata is None:
        return
    vector_effect = _vector_effect(style, element)
    if vector_effect != "none":
        metadata["vector_effect"] = vector_effect


def _record_stroke_policy(
    metadata: dict[str, Any] | None,
    *,
    policy: str,
    original_width: float,
    scale: float,
    adjusted_width: float,
) -> None:
    if metadata is None:
        return
    stroke_meta = metadata.setdefault("stroke_width", {})
    if not isinstance(stroke_meta, dict):
        stroke_meta = {}
        metadata["stroke_width"] = stroke_meta
    stroke_meta.update(
        {
            "policy": policy,
            "original_width": original_width,
            "transform_scale": scale,
            "adjusted_width": adjusted_width,
        }
    )


__all__ = [
    "apply_transform_stroke_width_policy",
    "effective_stroke_scale",
]
