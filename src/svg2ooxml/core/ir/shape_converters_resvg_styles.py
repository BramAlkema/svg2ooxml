"""Style materialization and <use> style merging for resvg conversion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.common.conversions.opacity import parse_opacity
from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.ir.paint import Stroke, StrokeCap, StrokeJoin


class ResvgStyleSupportMixin:
    def _style_with_local_opacity(
        self,
        element: etree._Element | None,
        style: StyleResult,
    ) -> StyleResult:
        """Keep SVG ``opacity`` local instead of inheriting ancestor opacity."""
        if element is None:
            return style
        try:
            paint_style = self._style_resolver.compute_paint_style(
                element,
                context=self._css_context,
            )
            inherited_paint_style = (
                self._style_extractor._compute_paint_style_with_inheritance(
                    element,
                    context=self._css_context,
                )
            )
            inherited_style = self._materialize_style(element, inherited_paint_style)
            opacity = parse_opacity(paint_style.get("opacity"), default=1.0)
        except Exception:
            opacity = (
                style.opacity
                if self._source_has_property(element, "opacity")
                else 1.0
            )
            inherited_style = None

        fill = style.fill
        if inherited_style is not None:
            fill = self._paint_with_base_opacity(fill, inherited_style.fill)

        stroke = style.stroke
        if (
            inherited_style is not None
            and stroke is not None
            and inherited_style.stroke is not None
        ):
            stroke_paint = self._paint_with_base_opacity(
                stroke.paint,
                inherited_style.stroke.paint,
            )
            stroke = replace(
                stroke,
                paint=stroke_paint,
                opacity=inherited_style.stroke.opacity,
            )

        opacity = max(0.0, min(1.0, opacity))
        try:
            return replace(style, fill=fill, stroke=stroke, opacity=opacity)
        except TypeError:
            style.fill = fill
            style.stroke = stroke
            style.opacity = opacity
            return style

    def _combine_strokes(
        self,
        override: Stroke | None,
        base: Stroke | None,
        *,
        override_element: etree._Element | None = None,
    ) -> Stroke | None:
        if base is None and override is None:
            return None
        if base is None:
            return override
        if override is None:
            return base

        paint = base.paint if base.paint is not None else override.paint
        width = override.width if override.width is not None else base.width
        join = (
            override.join
            if override.join != StrokeJoin.MITER or base.join == StrokeJoin.MITER
            else base.join
        )
        cap = (
            override.cap
            if override.cap != StrokeCap.BUTT or base.cap == StrokeCap.BUTT
            else base.cap
        )
        miter_limit = (
            override.miter_limit
            if override.miter_limit != 4.0 or base.miter_limit == 4.0
            else base.miter_limit
        )
        dash_array = base.dash_array
        if override.dash_array is not None or self._source_has_property(
            override_element, "stroke-dasharray"
        ):
            dash_array = override.dash_array

        dash_offset = base.dash_offset
        if self._source_has_property(override_element, "stroke-dashoffset"):
            dash_offset = override.dash_offset
        elif override.dash_offset not in (None, 0.0):
            dash_offset = override.dash_offset
        opacity = override.opacity if override.opacity != 1.0 else base.opacity

        return Stroke(
            paint=paint,
            width=width,
            join=join,
            cap=cap,
            miter_limit=miter_limit,
            dash_array=dash_array,
            dash_offset=dash_offset,
            opacity=opacity,
        )

    def _materialize_style(
        self,
        element: etree._Element,
        paint_style: dict[str, Any],
    ) -> StyleResult:
        metadata: dict[str, Any] = {}
        fill = self._style_extractor._resolve_paint(
            element,
            paint_style.get("fill"),
            opacity=parse_opacity(paint_style.get("fill_opacity"), default=1.0),
            services=self._services,
            context=self._css_context,
            metadata=metadata,
            role="fill",
        )
        stroke = self._style_extractor._resolve_stroke(
            element,
            paint_style,
            services=self._services,
            context=self._css_context,
            metadata=metadata,
        )
        opacity = parse_opacity(paint_style.get("opacity"), default=1.0)
        effects = self._style_extractor._resolve_effects(
            element,
            services=self._services,
            metadata=metadata,
            context=self._css_context,
        )
        return StyleResult(
            fill=fill,
            stroke=stroke,
            opacity=opacity,
            effects=effects,
            metadata=metadata,
        )

    def _merge_use_styles(
        self,
        use_style: StyleResult,
        source_style: StyleResult | None,
        *,
        use_element: etree._Element | None = None,
        source_element: etree._Element | None = None,
        use_paint_style: Mapping[str, Any] | None = None,
        multiply_opacity: bool = True,
    ) -> StyleResult:
        if source_style is None:
            return use_style

        source_has_fill = self._source_has_property(source_element, "fill")
        source_has_fill_opacity = self._source_has_property(
            source_element, "fill-opacity"
        )
        source_has_authored_fill = source_has_fill or not self._is_default_fill_paint(
            source_style.fill
        )
        if source_has_authored_fill:
            fill = source_style.fill
            if fill is not None and not source_has_fill_opacity:
                fill = self._paint_with_opacity(
                    fill,
                    self._style_opacity(use_paint_style, "fill_opacity"),
                )
        else:
            fill = use_style.fill

        stroke = self._combine_strokes(
            use_style.stroke,
            source_style.stroke,
            override_element=use_element,
        )
        if (
            stroke is not None
            and use_style.stroke is None
            and not self._source_has_property(source_element, "stroke-opacity")
        ):
            stroke = self._stroke_with_opacity(
                stroke,
                self._style_opacity(use_paint_style, "stroke_opacity"),
            )

        opacity = (
            max(0.0, min(1.0, source_style.opacity * use_style.opacity))
            if multiply_opacity
            else source_style.opacity
        )

        effects: list[Any] = []
        effects.extend(source_style.effects)
        for effect in use_style.effects:
            if effect not in effects:
                effects.append(effect)

        metadata: dict[str, Any] = {}
        if isinstance(source_style.metadata, dict):
            metadata.update(source_style.metadata)
        if isinstance(use_style.metadata, dict):
            metadata.update(use_style.metadata)

        return StyleResult(
            fill=fill,
            stroke=stroke,
            opacity=opacity,
            effects=effects,
            metadata=metadata,
        )


__all__ = ["ResvgStyleSupportMixin"]
