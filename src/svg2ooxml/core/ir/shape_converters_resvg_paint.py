"""Paint and scalar helpers for resvg-backed shape conversion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.common.conversions.opacity import clamp_opacity
from svg2ooxml.core.styling.pattern_merge import merge_pattern_paint
from svg2ooxml.core.styling.style_helpers import (
    apply_stroke_opacity as _apply_paint_opacity,
)
from svg2ooxml.core.styling.style_helpers import parse_style_attr
from svg2ooxml.ir.paint import (
    LinearGradientPaint,
    PatternPaint,
    RadialGradientPaint,
    SolidPaint,
    Stroke,
)


class ResvgPaintSupportMixin:
    @staticmethod
    def _paint_with_base_opacity(paint, base_paint):
        if (
            isinstance(paint, SolidPaint)
            and isinstance(base_paint, SolidPaint)
            and paint.rgb == base_paint.rgb
        ):
            return replace(paint, opacity=base_paint.opacity)
        if (
            isinstance(paint, (LinearGradientPaint, RadialGradientPaint))
            and isinstance(base_paint, type(paint))
            and len(paint.stops) == len(base_paint.stops)
        ):
            return replace(
                paint,
                stops=[
                    replace(paint_stop, opacity=base_stop.opacity)
                    for paint_stop, base_stop in zip(
                        paint.stops,
                        base_paint.stops,
                        strict=True,
                    )
                ],
            )
        return paint

    @staticmethod
    def _source_explicitly_disables_paint(
        source_element: etree._Element | None,
        attribute: str,
    ) -> bool:
        if source_element is None:
            return False
        attr_value = source_element.get(attribute)
        if isinstance(attr_value, str) and attr_value.strip().lower() == "none":
            return True
        style_attr = source_element.get("style")
        if not isinstance(style_attr, str) or attribute not in style_attr:
            return False
        parsed = parse_style_attr(style_attr)
        value = parsed.get(attribute)
        return isinstance(value, str) and value.strip().lower() == "none"

    @staticmethod
    def _source_has_property(
        source_element: etree._Element | None,
        attribute: str,
    ) -> bool:
        if source_element is None:
            return False
        if source_element.get(attribute) is not None:
            return True
        style_attr = source_element.get("style")
        if not isinstance(style_attr, str) or attribute not in style_attr:
            return False
        return attribute in parse_style_attr(style_attr)

    @staticmethod
    def _coerce_float(value: float | None, default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clamp_opacity(value: float) -> float:
        return clamp_opacity(value)

    @staticmethod
    def _style_opacity(style: Mapping[str, Any] | None, key: str) -> float:
        if not isinstance(style, Mapping):
            return 1.0
        return ResvgPaintSupportMixin._clamp_opacity(
            ResvgPaintSupportMixin._coerce_float(style.get(key), 1.0)
        )

    @staticmethod
    def _merge_pattern_paint(
        runtime_paint: PatternPaint,
        analyzed_paint: PatternPaint,
    ) -> PatternPaint:
        return merge_pattern_paint(runtime_paint, analyzed_paint)

    @staticmethod
    def _paint_with_opacity(paint, opacity: float):
        opacity = ResvgPaintSupportMixin._clamp_opacity(opacity)
        if paint is None or opacity >= 0.999:
            return paint
        return _apply_paint_opacity(paint, opacity)

    @staticmethod
    def _stroke_with_opacity(stroke: Stroke | None, opacity: float) -> Stroke | None:
        if stroke is None:
            return None
        opacity = ResvgPaintSupportMixin._clamp_opacity(opacity)
        if opacity >= 0.999:
            return stroke
        return replace(
            stroke,
            opacity=ResvgPaintSupportMixin._clamp_opacity(stroke.opacity * opacity),
        )

    @staticmethod
    def _is_default_fill_paint(paint) -> bool:
        return (
            isinstance(paint, SolidPaint)
            and paint.rgb.upper() == "000000"
            and paint.theme_color is None
            and paint.opacity >= 0.999
        )


__all__ = ["ResvgPaintSupportMixin"]
