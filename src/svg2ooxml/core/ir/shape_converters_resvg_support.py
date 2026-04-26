"""Support helpers for resvg-backed shape conversion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.core.ir.shape_converters_utils import _uniform_scale
from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.core.styling.style_helpers import (
    apply_stroke_opacity as _apply_paint_opacity,
)
from svg2ooxml.core.styling.style_helpers import parse_style_attr
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.core.traversal.geometry_utils import (
    is_axis_aligned,
    scaled_corner_radius,
    transform_axis_aligned_rect,
)
from svg2ooxml.ir.geometry import Point
from svg2ooxml.ir.paint import (
    LinearGradientPaint,
    PatternPaint,
    RadialGradientPaint,
    SolidPaint,
    Stroke,
    StrokeCap,
    StrokeJoin,
)
from svg2ooxml.ir.scene import ClipRef, MaskInstance, MaskRef
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle


class ResvgSupportMixin:
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
    def _append_metadata_element_id(
        metadata: dict[str, Any],
        element_id: str | None,
    ) -> None:
        if not isinstance(element_id, str) or not element_id:
            return
        element_ids = metadata.setdefault("element_ids", [])
        if not isinstance(element_ids, list):
            element_ids = []
            metadata["element_ids"] = element_ids
        if element_id not in element_ids:
            element_ids.append(element_id)

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
            opacity = float(paint_style.get("opacity", 1.0))
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

    @staticmethod
    def _merge_pattern_paint(
        runtime_paint: PatternPaint, analyzed_paint: PatternPaint
    ) -> PatternPaint:
        return replace(
            runtime_paint,
            preset=analyzed_paint.preset or runtime_paint.preset,
            foreground=analyzed_paint.foreground or runtime_paint.foreground,
            background=analyzed_paint.background or runtime_paint.background,
            background_opacity=analyzed_paint.background_opacity,
            foreground_theme_color=analyzed_paint.foreground_theme_color
            or runtime_paint.foreground_theme_color,
            background_theme_color=analyzed_paint.background_theme_color
            or runtime_paint.background_theme_color,
            tile_image=analyzed_paint.tile_image or runtime_paint.tile_image,
            tile_width_px=analyzed_paint.tile_width_px or runtime_paint.tile_width_px,
            tile_height_px=analyzed_paint.tile_height_px
            or runtime_paint.tile_height_px,
        )

    def _resvg_miss_reason(self, element: etree._Element) -> str:
        if getattr(self, "_resvg_tree", None) is None:
            return "resvg_tree_missing"
        resvg_lookup = getattr(self, "_resvg_element_lookup", {})
        if element not in resvg_lookup:
            return "resvg_node_missing"
        return "resvg_conversion_failed"

    def _trace_resvg_only_miss(self, element: etree._Element, reason: str) -> None:
        self._trace_geometry_decision(
            element,
            "resvg_only_skip",
            {"reason": reason, "geometry_mode": "resvg-only"},
        )

    def _can_use_resvg(self, element: etree._Element) -> bool:
        """Check if resvg mode is available and enabled for this element.

        Returns:
            True if:
            - resvg tree exists on converter
            - element has corresponding resvg node in lookup table
        """
        # Check resvg tree exists
        if getattr(self, "_resvg_tree", None) is None:
            return False

        # Check element has resvg node
        resvg_lookup = getattr(self, "_resvg_element_lookup", {})
        if element not in resvg_lookup:
            return False

        return True

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
        return max(0.0, min(1.0, value))

    @staticmethod
    def _style_opacity(style: Mapping[str, Any] | None, key: str) -> float:
        if not isinstance(style, Mapping):
            return 1.0
        return ResvgSupportMixin._clamp_opacity(
            ResvgSupportMixin._coerce_float(style.get(key), 1.0)
        )

    @staticmethod
    def _matrix2d_from_resvg(matrix: Matrix2D | None) -> Matrix2D:
        if matrix is None:
            return Matrix2D.identity()
        if isinstance(matrix, Matrix2D):
            return matrix
        # Fallback: assume resvg Matrix signature (a, b, c, d, e, f)
        return Matrix2D.from_values(
            ResvgSupportMixin._coerce_float(getattr(matrix, "a", None), 1.0),
            ResvgSupportMixin._coerce_float(getattr(matrix, "b", None), 0.0),
            ResvgSupportMixin._coerce_float(getattr(matrix, "c", None), 0.0),
            ResvgSupportMixin._coerce_float(getattr(matrix, "d", None), 1.0),
            ResvgSupportMixin._coerce_float(getattr(matrix, "e", None), 0.0),
            ResvgSupportMixin._coerce_float(getattr(matrix, "f", None), 0.0),
        )

    @staticmethod
    def _geometry_fallback_flags(policy: Mapping[str, Any] | None) -> tuple[bool, bool]:
        if not policy:
            return True, True
        allow_emf = bool(policy.get("allow_emf_fallback", True)) or bool(
            policy.get("force_emf")
        )
        allow_bitmap = bool(policy.get("allow_bitmap_fallback", True)) or bool(
            policy.get("force_bitmap")
        )
        return allow_emf, allow_bitmap

    def _resvg_rect_to_rectangle(
        self,
        *,
        element: etree._Element,
        resvg_node: Any,
        style: StyleResult,
        metadata: dict[str, Any],
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
    ) -> Rectangle | None:
        if clip_ref is not None or mask_ref is not None or mask_instance is not None:
            return None
        if style.effects:
            return None

        transform_matrix = self._matrix2d_from_resvg(
            getattr(resvg_node, "transform", None)
        )
        if not is_axis_aligned(transform_matrix, DEFAULT_TOLERANCE):
            return None

        x = ResvgSupportMixin._coerce_float(getattr(resvg_node, "x", None), 0.0)
        y = ResvgSupportMixin._coerce_float(getattr(resvg_node, "y", None), 0.0)
        width = ResvgSupportMixin._coerce_float(getattr(resvg_node, "width", None), 0.0)
        height = ResvgSupportMixin._coerce_float(getattr(resvg_node, "height", None), 0.0)

        bounds = transform_axis_aligned_rect(
            transform_matrix,
            x,
            y,
            width,
            height,
            DEFAULT_TOLERANCE,
        )
        if bounds is None:
            return None

        rx = ResvgSupportMixin._coerce_float(getattr(resvg_node, "rx", None), 0.0)
        ry = ResvgSupportMixin._coerce_float(getattr(resvg_node, "ry", None), 0.0)
        if rx <= 0.0 and ry > 0.0:
            rx = ry
        if ry <= 0.0 and rx > 0.0:
            ry = rx

        max_rx = getattr(resvg_node, "width", 0.0) / 2.0
        max_ry = getattr(resvg_node, "height", 0.0) / 2.0
        rx = max(0.0, min(rx, max_rx))
        ry = max(0.0, min(ry, max_ry))

        if rx > DEFAULT_TOLERANCE and ry > DEFAULT_TOLERANCE:
            if abs(rx - ry) > DEFAULT_TOLERANCE:
                return None
            corner_radius = scaled_corner_radius(
                rx, transform_matrix, DEFAULT_TOLERANCE
            )
        else:
            corner_radius = 0.0

        rectangle = Rectangle(
            bounds=bounds,
            corner_radius=corner_radius,
            fill=style.fill,
            stroke=style.stroke,
            opacity=style.opacity,
            effects=list(style.effects),
            metadata=metadata,
            element_id=element.get("id"),
        )
        return rectangle

    def _resvg_circle_to_circle(
        self,
        *,
        element: etree._Element,
        resvg_node: Any,
        style: StyleResult,
        metadata: dict[str, Any],
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
    ) -> Circle | None:
        if clip_ref is not None or mask_ref is not None or mask_instance is not None:
            return None
        if style.effects:
            return None

        transform_matrix = self._matrix2d_from_resvg(
            getattr(resvg_node, "transform", None)
        )
        cx = ResvgSupportMixin._coerce_float(getattr(resvg_node, "cx", None), 0.0)
        cy = ResvgSupportMixin._coerce_float(getattr(resvg_node, "cy", None), 0.0)
        raw_radius = ResvgSupportMixin._coerce_float(getattr(resvg_node, "r", None), 0.0)
        if transform_matrix.is_identity(tolerance=DEFAULT_TOLERANCE):
            center = Point(cx, cy)
            scale = 1.0
        else:
            scale = _uniform_scale(transform_matrix, DEFAULT_TOLERANCE)
            if scale is None:
                return None
            center = transform_matrix.transform_point(Point(cx, cy))

        radius = raw_radius * scale
        if radius <= DEFAULT_TOLERANCE:
            return None

        circle = Circle(
            center=center,
            radius=radius,
            fill=style.fill,
            stroke=style.stroke,
            opacity=style.opacity,
            effects=list(style.effects),
            metadata=metadata,
            element_id=element.get("id"),
        )
        return circle

    def _resvg_ellipse_to_ellipse(
        self,
        *,
        element: etree._Element,
        resvg_node: Any,
        style: StyleResult,
        metadata: dict[str, Any],
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
    ) -> Ellipse | None:
        if clip_ref is not None or mask_ref is not None or mask_instance is not None:
            return None
        if style.effects:
            return None

        transform_matrix = self._matrix2d_from_resvg(
            getattr(resvg_node, "transform", None)
        )
        has_rotation = (
            abs(transform_matrix.b) > DEFAULT_TOLERANCE
            or abs(transform_matrix.c) > DEFAULT_TOLERANCE
        )
        if has_rotation:
            return None

        scale_x = float(transform_matrix.a)
        scale_y = float(transform_matrix.d)
        translate_x = float(transform_matrix.e)
        translate_y = float(transform_matrix.f)

        cx = ResvgSupportMixin._coerce_float(getattr(resvg_node, "cx", None), 0.0)
        cy = ResvgSupportMixin._coerce_float(getattr(resvg_node, "cy", None), 0.0)
        raw_rx = ResvgSupportMixin._coerce_float(getattr(resvg_node, "rx", None), 0.0)
        raw_ry = ResvgSupportMixin._coerce_float(getattr(resvg_node, "ry", None), 0.0)

        if transform_matrix.is_identity(tolerance=DEFAULT_TOLERANCE):
            center = Point(cx, cy)
            radius_x = raw_rx
            radius_y = raw_ry
        else:
            if abs(scale_x) <= DEFAULT_TOLERANCE or abs(scale_y) <= DEFAULT_TOLERANCE:
                return None
            center = Point(cx * scale_x + translate_x, cy * scale_y + translate_y)
            radius_x = abs(raw_rx * scale_x)
            radius_y = abs(raw_ry * scale_y)

        if radius_x <= DEFAULT_TOLERANCE or radius_y <= DEFAULT_TOLERANCE:
            return None

        ellipse = Ellipse(
            center=center,
            radius_x=radius_x,
            radius_y=radius_y,
            fill=style.fill,
            stroke=style.stroke,
            opacity=style.opacity,
            effects=list(style.effects),
            metadata=metadata,
            element_id=element.get("id"),
        )
        return ellipse

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

    @staticmethod
    def _paint_with_opacity(paint, opacity: float):
        opacity = ResvgSupportMixin._clamp_opacity(opacity)
        if paint is None or opacity >= 0.999:
            return paint
        return _apply_paint_opacity(paint, opacity)

    @staticmethod
    def _stroke_with_opacity(stroke: Stroke | None, opacity: float) -> Stroke | None:
        if stroke is None:
            return None
        opacity = ResvgSupportMixin._clamp_opacity(opacity)
        if opacity >= 0.999:
            return stroke
        return replace(
            stroke,
            opacity=ResvgSupportMixin._clamp_opacity(stroke.opacity * opacity),
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
            opacity=float(paint_style.get("fill_opacity", 1.0)),
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
        opacity = float(paint_style.get("opacity", 1.0))
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
        if source_has_fill:
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
