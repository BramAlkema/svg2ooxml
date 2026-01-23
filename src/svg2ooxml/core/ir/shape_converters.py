"""Shape conversion helpers for the IR converter."""



from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Iterable, Mapping, Sequence

from lxml import etree

from svg2ooxml.common.geometry.paths import PathParseError, normalize_path_to_segments, parse_path_data
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect, SegmentType
from svg2ooxml.ir.paint import SolidPaint, Stroke, StrokeCap, StrokeJoin
from svg2ooxml.ir.scene import ClipRef, Group, Image, MaskInstance, MaskRef, Path
from svg2ooxml.ir.shapes import Circle, Ellipse, Line, Polygon, Polyline, Rectangle
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame
from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_EMF
from svg2ooxml.policy.geometry import apply_geometry_policy

from svg2ooxml.core.ir import fallbacks
from svg2ooxml.core.traversal import marker_runtime
from svg2ooxml.core.styling import style_runtime as styles_runtime
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.core.traversal.geometry_utils import (
    is_axis_aligned,
    scaled_corner_radius,
    transform_axis_aligned_rect,
)
from svg2ooxml.core.ir.rectangles import convert_rect as convert_rectangle
from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.core.masks.baker import try_bake_mask


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value

class ShapeConversionMixin:
    """Mixin that houses individual SVG element conversion helpers."""

    _logger = None  # populated by IRConverter

    def _trace_geometry_decision(
        self,
        element: etree._Element,
        decision: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        tracer = getattr(self, "_tracer", None)
        if tracer is None:
            return
        tag = ""
        if isinstance(element.tag, str):
            tag = element.tag.split("}", 1)[-1]
        element_id = element.get("id") if hasattr(element, "get") else None
        tracer.record_geometry_decision(
            tag=tag,
            decision=decision,
            metadata=dict(metadata) if isinstance(metadata, dict) else metadata,
            element_id=element_id,
        )

    # ------------------------------------------------------------------ #
    # Resvg routing infrastructure                                       #
    # ------------------------------------------------------------------ #

    def _can_use_resvg(self, element: etree._Element) -> bool:
        """Check if resvg mode is available and enabled for this element.

        Returns:
            True if:
            - geometry_mode policy is "resvg"
            - resvg tree exists on converter
            - element has corresponding resvg node in lookup table
        """
        # Check policy
        geometry_options = self._policy_options("geometry")
        if not geometry_options or geometry_options.get("geometry_mode") != "resvg":
            return False

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
    def _matrix2d_from_resvg(matrix: Matrix2D | None) -> Matrix2D:
        if matrix is None:
            return Matrix2D.identity()
        if isinstance(matrix, Matrix2D):
            return matrix
        # Fallback: assume resvg Matrix signature (a, b, c, d, e, f)
        return Matrix2D.from_values(
            ShapeConversionMixin._coerce_float(getattr(matrix, "a", None), 1.0),
            ShapeConversionMixin._coerce_float(getattr(matrix, "b", None), 0.0),
            ShapeConversionMixin._coerce_float(getattr(matrix, "c", None), 0.0),
            ShapeConversionMixin._coerce_float(getattr(matrix, "d", None), 1.0),
            ShapeConversionMixin._coerce_float(getattr(matrix, "e", None), 0.0),
            ShapeConversionMixin._coerce_float(getattr(matrix, "f", None), 0.0),
        )

    @staticmethod
    def _geometry_fallback_flags(policy: Mapping[str, Any] | None) -> tuple[bool, bool]:
        if not policy:
            return True, True
        allow_emf = bool(policy.get("allow_emf_fallback", True)) or bool(policy.get("force_emf"))
        allow_bitmap = bool(policy.get("allow_bitmap_fallback", True)) or bool(policy.get("force_bitmap"))
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

        transform_matrix = self._matrix2d_from_resvg(getattr(resvg_node, "transform", None))
        if not is_axis_aligned(transform_matrix, DEFAULT_TOLERANCE):
            return None

        x = ShapeConversionMixin._coerce_float(getattr(resvg_node, "x", None), 0.0)
        y = ShapeConversionMixin._coerce_float(getattr(resvg_node, "y", None), 0.0)
        width = ShapeConversionMixin._coerce_float(getattr(resvg_node, "width", None), 0.0)
        height = ShapeConversionMixin._coerce_float(getattr(resvg_node, "height", None), 0.0)

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

        rx = ShapeConversionMixin._coerce_float(getattr(resvg_node, "rx", None), 0.0)
        ry = ShapeConversionMixin._coerce_float(getattr(resvg_node, "ry", None), 0.0)
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
            corner_radius = scaled_corner_radius(rx, transform_matrix, DEFAULT_TOLERANCE)
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

        transform_matrix = self._matrix2d_from_resvg(getattr(resvg_node, "transform", None))
        cx = ShapeConversionMixin._coerce_float(getattr(resvg_node, "cx", None), 0.0)
        cy = ShapeConversionMixin._coerce_float(getattr(resvg_node, "cy", None), 0.0)
        raw_radius = ShapeConversionMixin._coerce_float(getattr(resvg_node, "r", None), 0.0)
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

        transform_matrix = self._matrix2d_from_resvg(getattr(resvg_node, "transform", None))
        has_rotation = abs(transform_matrix.b) > DEFAULT_TOLERANCE or abs(transform_matrix.c) > DEFAULT_TOLERANCE
        if has_rotation:
            return None

        scale_x = float(transform_matrix.a)
        scale_y = float(transform_matrix.d)
        translate_x = float(transform_matrix.e)
        translate_y = float(transform_matrix.f)

        cx = ShapeConversionMixin._coerce_float(getattr(resvg_node, "cx", None), 0.0)
        cy = ShapeConversionMixin._coerce_float(getattr(resvg_node, "cy", None), 0.0)
        raw_rx = ShapeConversionMixin._coerce_float(getattr(resvg_node, "rx", None), 0.0)
        raw_ry = ShapeConversionMixin._coerce_float(getattr(resvg_node, "ry", None), 0.0)

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

    @staticmethod
    def _combine_strokes(override: Stroke | None, base: Stroke | None) -> Stroke | None:
        if base is None and override is None:
            return None
        if base is None:
            return override
        if override is None:
            return base

        paint = base.paint if base.paint is not None else override.paint
        width = override.width if override.width is not None else base.width
        join = override.join if override.join != StrokeJoin.MITER or base.join == StrokeJoin.MITER else base.join
        cap = override.cap if override.cap != StrokeCap.BUTT or base.cap == StrokeCap.BUTT else base.cap
        miter_limit = override.miter_limit if override.miter_limit != 4.0 or base.miter_limit == 4.0 else base.miter_limit
        dash_array = override.dash_array if override.dash_array else base.dash_array
        dash_offset = override.dash_offset if override.dash_offset else base.dash_offset
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

    def _merge_use_styles(self, use_style: StyleResult, source_style: StyleResult | None) -> StyleResult:
        if source_style is None:
            return use_style

        fill = source_style.fill if source_style.fill is not None else use_style.fill
        stroke = self._combine_strokes(use_style.stroke, source_style.stroke)

        opacity = use_style.opacity if use_style.opacity != 1.0 else source_style.opacity

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

    def _convert_via_resvg(self, element: etree._Element, coord_space: CoordinateSpace):
        """Convert element using resvg adapters.

        This method handles:
        - Looking up the resvg node
        - Routing to appropriate adapter based on node type
        - Extracting style from element
        - Creating IR objects with style and metadata

        Args:
            element: SVG element to convert
            coord_space: Current coordinate space (used for style extraction)

        Returns:
            IR object (Path, Circle, etc.) or None if conversion fails
        """
        from svg2ooxml.drawingml.bridges.resvg_shape_adapter import ResvgShapeAdapter

        # Look up resvg node
        resvg_lookup = getattr(self, "_resvg_element_lookup", {})
        resvg_node = resvg_lookup.get(element)
        if resvg_node is None:
            return None

        # Extract style (same as legacy path)
        style = styles_runtime.extract_style(self, element)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")

        use_source = getattr(resvg_node, "use_source", None)
        source_element = None
        if isinstance(use_source, etree._Element):
            href_attr = use_source.get("{http://www.w3.org/1999/xlink}href") or use_source.get("href")
            reference_id = self._normalize_href_reference(href_attr)
            if reference_id:
                source_element = self._element_index.get(reference_id)
        if source_element is None:
            source_element = getattr(resvg_node, "source", None)
        source_style: StyleResult | None = None
        if isinstance(source_element, etree._Element):
            paint_dict = self._style_resolver.compute_paint_style(source_element, context=self._css_context)
            source_style = self._materialize_style(source_element, paint_dict)
            style = self._merge_use_styles(style, source_style)
            metadata.update(source_style.metadata or {})

        # Override stroke/fill from resvg_node if available
        # This preserves attributes from <use> elements that override referenced content
        if hasattr(resvg_node, 'stroke') and resvg_node.stroke is not None:
            from svg2ooxml.paint.resvg_bridge import resolve_stroke_style
            tree = getattr(self, "_resvg_tree", None)
            if tree is not None:
                resvg_stroke = resolve_stroke_style(resvg_node.stroke, tree)
                if resvg_stroke is not None and resvg_stroke.paint is not None:
                    style = replace(style, stroke=resvg_stroke)
        if hasattr(resvg_node, 'fill') and resvg_node.fill is not None:
            from svg2ooxml.paint.resvg_bridge import resolve_fill_paint
            tree = getattr(self, "_resvg_tree", None)
            if tree is not None:
                resvg_fill = resolve_fill_paint(resvg_node.fill, tree)
                if resvg_fill is not None:
                    style = replace(style, fill=resvg_fill)

        node_type = type(resvg_node).__name__
        # Get clip/mask refs (shared across shape types)
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)

        if node_type == "RectNode":
            rectangle = self._resvg_rect_to_rectangle(
                element=element,
                resvg_node=resvg_node,
                style=style,
                metadata=metadata,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
            )
            if rectangle is not None:
                self._trace_geometry_decision(element, "resvg", rectangle.metadata)
                return rectangle

        if node_type == "CircleNode":
            circle = self._resvg_circle_to_circle(
                element=element,
                resvg_node=resvg_node,
                style=style,
                metadata=metadata,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
            )
            if circle is not None:
                self._trace_geometry_decision(element, "resvg", circle.metadata)
                return circle

        if node_type == "EllipseNode":
            ellipse = self._resvg_ellipse_to_ellipse(
                element=element,
                resvg_node=resvg_node,
                style=style,
                metadata=metadata,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
            )
            if ellipse is not None:
                self._trace_geometry_decision(element, "resvg", ellipse.metadata)
                return ellipse

        # Convert using resvg adapter
        adapter = ResvgShapeAdapter()
        segments = None

        # Route to appropriate adapter method based on node type
        try:
            if node_type == "PathNode":
                segments = adapter.from_path_node(resvg_node)
            elif node_type == "RectNode":
                segments = adapter.from_rect_node(resvg_node)
            elif node_type == "CircleNode":
                segments = adapter.from_circle_node(resvg_node)
            elif node_type == "EllipseNode":
                segments = adapter.from_ellipse_node(resvg_node)
            else:
                # Unsupported node type, return None to trigger fallback
                return None
        except Exception as exc:
            self._logger.debug(
                "Resvg adapter failed for %s: %s",
                element.get("id") or f"<{node_type}>",
                exc,
            )
            return None

        if not segments:
            return None

        # Resvg segments already have transforms applied, so we don't apply coord_space
        # Create IR Path with segments
        path = Path(
            segments=segments,
            fill=style.fill,
            stroke=style.stroke,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            effects=style.effects,
            metadata=metadata,
        )
        self._process_mask_metadata(path)
        self._apply_marker_metadata(element, path.metadata)
        marker_shapes = self._build_marker_shapes(element, path)
        self._trace_geometry_decision(element, "resvg", path.metadata)
        if marker_shapes:
            return [path, *marker_shapes]
        return path

    def _convert_use(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        current_navigation,
        traverse_callback,
    ):
        """Convert <use> elements via resvg or fall back to legacy expansion."""
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result

        return self.expand_use(
            element=element,
            coord_space=coord_space,
            current_navigation=current_navigation,
            traverse_callback=traverse_callback,
        )

    def _convert_rect(self, *, element: etree._Element, coord_space: CoordinateSpace):
        # Try resvg path first if available
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            # If resvg failed, fall through to legacy

        # Legacy conversion path
        return convert_rectangle(self, element, coord_space, tolerance=DEFAULT_TOLERANCE)

    def _convert_circle(self, *, element: etree._Element, coord_space: CoordinateSpace):
        # Try resvg path first if available
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            # If resvg failed, fall through to legacy

        # Legacy conversion path
        return self._convert_circle_legacy(element=element, coord_space=coord_space)

    def _convert_circle_legacy(self, *, element: etree._Element, coord_space: CoordinateSpace):
        """Legacy circle conversion (manual coordinate extraction)."""
        cx = _parse_float(element.get("cx"), default=0.0) or 0.0
        cy = _parse_float(element.get("cy"), default=0.0) or 0.0
        radius = _parse_float(element.get("r"))
        if radius is None or radius <= 0:
            return None

        style = styles_runtime.extract_style(self, element)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)
        matrix = coord_space.current

        if not clip_ref and not mask_ref:
            scale = _uniform_scale(matrix, DEFAULT_TOLERANCE)
            if scale is not None:
                center = matrix.transform_point(Point(cx, cy))
                scaled_radius = radius * scale
                if scaled_radius > DEFAULT_TOLERANCE:
                    circle = Circle(
                        center=center,
                        radius=scaled_radius,
                        fill=style.fill,
                        stroke=style.stroke,
                        opacity=style.opacity,
                        effects=list(style.effects),
                        metadata=metadata,
                        element_id=element.get("id"),
                    )
                    self._trace_geometry_decision(element, "native", circle.metadata)
                    return circle

        segments = _ellipse_segments(cx, cy, radius, radius)
        transformed_segments = coord_space.apply_segments(segments)
        path = Path(
            segments=transformed_segments,
            fill=style.fill,
            stroke=style.stroke,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            effects=style.effects,
            metadata=metadata,
        )
        self._process_mask_metadata(path)
        self._trace_geometry_decision(element, "native", path.metadata)
        return path

    def _convert_ellipse(self, *, element: etree._Element, coord_space: CoordinateSpace):
        # Try resvg path first if available
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            # If resvg failed, fall through to legacy

        # Legacy conversion path
        return self._convert_ellipse_legacy(element=element, coord_space=coord_space)

    def _convert_ellipse_legacy(self, *, element: etree._Element, coord_space: CoordinateSpace):
        """Legacy ellipse conversion (manual coordinate extraction)."""
        cx = _parse_float(element.get("cx"), default=0.0) or 0.0
        cy = _parse_float(element.get("cy"), default=0.0) or 0.0
        rx = _parse_float(element.get("rx"))
        ry = _parse_float(element.get("ry"))
        if rx is None or ry is None or rx <= 0 or ry <= 0:
            return None

        style = styles_runtime.extract_style(self, element)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)
        matrix = coord_space.current

        if not clip_ref and not mask_ref and is_axis_aligned(matrix, DEFAULT_TOLERANCE):
            scale_x = abs(matrix.a)
            scale_y = abs(matrix.d)
            if scale_x > DEFAULT_TOLERANCE and scale_y > DEFAULT_TOLERANCE:
                center = matrix.transform_point(Point(cx, cy))
                scaled_rx = rx * scale_x
                scaled_ry = ry * scale_y
                if scaled_rx > DEFAULT_TOLERANCE and scaled_ry > DEFAULT_TOLERANCE:
                    ellipse = Ellipse(
                        center=center,
                        radius_x=scaled_rx,
                        radius_y=scaled_ry,
                        fill=style.fill,
                        stroke=style.stroke,
                        opacity=style.opacity,
                        effects=list(style.effects),
                        metadata=metadata,
                        element_id=element.get("id"),
                    )
                    self._trace_geometry_decision(element, "native", ellipse.metadata)
                    return ellipse

        segments = _ellipse_segments(cx, cy, rx, ry)
        transformed_segments = coord_space.apply_segments(segments)
        path = Path(
            segments=transformed_segments,
            fill=style.fill,
            stroke=style.stroke,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            effects=style.effects,
            metadata=metadata,
        )
        self._process_mask_metadata(path)
        self._trace_geometry_decision(element, "native", path.metadata)
        return path

    def _convert_line(self, *, element: etree._Element, coord_space: CoordinateSpace):
        x1 = _parse_float(element.get("x1"))
        y1 = _parse_float(element.get("y1"))
        x2 = _parse_float(element.get("x2"))
        y2 = _parse_float(element.get("y2"))
        if None in (x1, y1, x2, y2):
            return None

        style = styles_runtime.extract_style(self, element)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)

        if (
            clip_ref is None
            and mask_ref is None
            and mask_instance is None
            and not _has_markers(element)
        ):
            start_x, start_y = coord_space.apply_point(x1, y1)
            end_x, end_y = coord_space.apply_point(x2, y2)
            line = Line(
                start=Point(start_x, start_y),
                end=Point(end_x, end_y),
                stroke=style.stroke,
                opacity=style.opacity,
                effects=list(style.effects),
                metadata=metadata,
            )
            if not line.is_degenerate:
                self._trace_geometry_decision(element, "native", line.metadata)
                return line

        segments = [LineSegment(Point(x1, y1), Point(x2, y2))]
        transformed = coord_space.apply_segments(segments)
        path = Path(
            segments=transformed,
            fill=None,
            stroke=style.stroke,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            effects=style.effects,
            metadata=metadata,
        )
        self._trace_geometry_decision(element, "native", path.metadata)
        return path

    def _convert_path(self, *, element: etree._Element, coord_space: CoordinateSpace):
        data = element.get("d")
        if not data:
            return None

        # Try resvg path first if available AND geometry_mode is "resvg"
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            # If resvg failed, fall through to legacy

        # Legacy path conversion (with optional resvg normalization as best-effort)
        segments: list[SegmentType] | None = None

        resvg_node = (
            getattr(self, "_resvg_element_lookup", {}).get(element)
            if hasattr(self, "_resvg_element_lookup")
            else None
        )

        style = styles_runtime.extract_style(self, element)

        # Best-effort resvg normalization (even in legacy mode)
        if resvg_node is not None and getattr(resvg_node, "d", None):
            try:
                normalized = normalize_path_to_segments(
                    resvg_node.d,
                    stroke_width=style.stroke.width if style.stroke else None,
                    tolerance=DEFAULT_TOLERANCE,
                )
                segments = normalized.segments
            except Exception as exc:  # pragma: no cover - bridge is best-effort during porting
                self._logger.debug("resvg bridge failed for path %s: %s", resvg_node.id or "<unnamed>", exc)

        if segments is None:
            try:
                segments = list(parse_path_data(data))
            except PathParseError as exc:
                self._logger.debug("Failed to parse path data: %s", exc)
                return None

        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)

        policy = self._policy_options("geometry")
        allow_emf_fallback, allow_bitmap_fallback = self._geometry_fallback_flags(policy)
        segments, geom_meta, render_mode = apply_geometry_policy(list(segments), policy)
        bitmap_limits = self._bitmap_fallback_limits(policy)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")
        if geom_meta:
            policy_meta = metadata.setdefault("policy", {}).setdefault("geometry", {})
            policy_meta.update(geom_meta)
        if style.fill and not isinstance(style.fill, SolidPaint):
            if allow_bitmap_fallback:
                render_mode = FALLBACK_BITMAP
            elif allow_emf_fallback:
                render_mode = FALLBACK_EMF

        fallback_to_bitmap = False
        if render_mode == FALLBACK_EMF:
            emf_image = self._convert_path_to_emf(
                element=element,
                style=style,
                segments=segments,
                coord_space=coord_space,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
                metadata=metadata,
            )
            if emf_image is not None:
                self._process_mask_metadata(emf_image)
                self._trace_geometry_decision(element, "emf", emf_image.metadata if isinstance(emf_image.metadata, dict) else metadata)
                return emf_image
            if allow_bitmap_fallback:
                self._logger.warning("Failed to build EMF fallback; attempting bitmap fallback.")
                fallback_to_bitmap = True
            else:
                self._logger.warning("Failed to build EMF fallback; bitmap fallback disabled.")

        if (render_mode == FALLBACK_BITMAP or fallback_to_bitmap) and allow_bitmap_fallback:
            bitmap_image = self._convert_path_to_bitmap(
                element=element,
                style=style,
                segments=segments,
                coord_space=coord_space,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
                metadata=metadata,
                bitmap_limits=bitmap_limits,
            )
            if bitmap_image is not None:
                if fallback_to_bitmap:
                    geometry_policy = metadata.setdefault("policy", {}).setdefault("geometry", {})
                    geometry_policy["render_mode"] = FALLBACK_BITMAP
                self._process_mask_metadata(bitmap_image)
                self._trace_geometry_decision(
                    element,
                    "bitmap",
                    bitmap_image.metadata if isinstance(bitmap_image.metadata, dict) else metadata,
                )
                return bitmap_image
            self._logger.warning("Failed to rasterize path; falling back to native rendering.")
        elif render_mode == FALLBACK_BITMAP and not allow_bitmap_fallback:
            self._logger.warning("Bitmap fallback disabled; falling back to native rendering.")

        transformed = coord_space.apply_segments(segments)
        if not transformed:
            return None

        path_object = Path(
            segments=transformed,
            fill=style.fill,
            stroke=style.stroke,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            effects=style.effects,
            metadata=metadata,
        )
        self._process_mask_metadata(path_object)
        self._trace_geometry_decision(element, "native", path_object.metadata)
        self._apply_marker_metadata(element, path_object.metadata)
        marker_shapes = self._build_marker_shapes(element, path_object)
        if marker_shapes:
            return [path_object, *marker_shapes]
        return path_object

    def _convert_polygon(self, *, element: etree._Element, coord_space: CoordinateSpace):
        points = _parse_points(element.get("points"))
        if len(points) < 3:
            return None
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)
        if clip_ref is not None or mask_ref is not None or mask_instance is not None or _has_markers(element):
            segments = _points_to_segments(points, closed=True)
            return self._segments_to_path(element, segments, coord_space)

        style = styles_runtime.extract_style(self, element)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")

        policy = self._policy_options("geometry")
        allow_emf_fallback, allow_bitmap_fallback = self._geometry_fallback_flags(policy)
        segments = _points_to_segments(points, closed=True)
        segments, geom_meta, render_mode = apply_geometry_policy(list(segments), policy)
        bitmap_limits = self._bitmap_fallback_limits(policy)
        if geom_meta:
            policy_meta = metadata.setdefault("policy", {}).setdefault("geometry", {})
            policy_meta.update(geom_meta)

        if style.fill and not isinstance(style.fill, SolidPaint):
            if allow_bitmap_fallback:
                render_mode = FALLBACK_BITMAP
            elif allow_emf_fallback:
                render_mode = FALLBACK_EMF

        fallback_to_bitmap = False
        if render_mode == FALLBACK_EMF:
            emf_image = self._convert_path_to_emf(
                element=element,
                style=style,
                segments=segments,
                coord_space=coord_space,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
                metadata=metadata,
            )
            if emf_image is not None:
                self._trace_geometry_decision(element, "emf", emf_image.metadata if isinstance(emf_image.metadata, dict) else metadata)
                return emf_image
            if allow_bitmap_fallback:
                self._logger.warning("Failed to build EMF fallback; attempting bitmap fallback.")
                fallback_to_bitmap = True
            else:
                self._logger.warning("Failed to build EMF fallback; bitmap fallback disabled.")

        if (render_mode == FALLBACK_BITMAP or fallback_to_bitmap) and allow_bitmap_fallback:
            bitmap_image = self._convert_path_to_bitmap(
                element=element,
                style=style,
                segments=segments,
                coord_space=coord_space,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
                metadata=metadata,
                bitmap_limits=bitmap_limits,
            )
            if bitmap_image is not None:
                if fallback_to_bitmap:
                    geometry_policy = metadata.setdefault("policy", {}).setdefault("geometry", {})
                    geometry_policy["render_mode"] = FALLBACK_BITMAP
                self._trace_geometry_decision(
                    element,
                    "bitmap",
                    bitmap_image.metadata if isinstance(bitmap_image.metadata, dict) else metadata,
                )
                return bitmap_image
            self._logger.warning("Failed to rasterize polygon; falling back to native rendering.")
        elif render_mode == FALLBACK_BITMAP and not allow_bitmap_fallback:
            self._logger.warning("Bitmap fallback disabled; falling back to native rendering.")

        if any(not isinstance(segment, LineSegment) for segment in segments):
            transformed = coord_space.apply_segments(segments)
            path_object = Path(
                segments=transformed,
                fill=style.fill,
                stroke=style.stroke,
                clip=clip_ref,
                mask=mask_ref,
                mask_instance=mask_instance,
                opacity=style.opacity,
                effects=style.effects,
                metadata=metadata,
            )
            self._trace_geometry_decision(element, "native", path_object.metadata)
            return path_object

        transformed_segments = coord_space.apply_segments(segments)
        polygon_points = _segments_to_points(transformed_segments, closed=True)
        if len(polygon_points) < 3:
            # Degenerate after transforms; fall back to path for consistency
            path_object = Path(
                segments=transformed_segments,
                fill=style.fill,
                stroke=style.stroke,
                clip=clip_ref,
                mask=mask_ref,
                mask_instance=mask_instance,
                opacity=style.opacity,
                effects=style.effects,
                metadata=metadata,
            )
            self._trace_geometry_decision(element, "native", path_object.metadata)
            return path_object

        polygon = Polygon(
            points=polygon_points,
            fill=style.fill,
            stroke=style.stroke,
            opacity=style.opacity,
            effects=list(style.effects),
            metadata=metadata,
        )
        self._trace_geometry_decision(element, "native", polygon.metadata)
        return polygon

    def _convert_polyline(self, *, element: etree._Element, coord_space: CoordinateSpace):
        points = _parse_points(element.get("points"))
        if len(points) < 2:
            return None
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)
        if clip_ref is not None or mask_ref is not None or mask_instance is not None or _has_markers(element):
            segments = _points_to_segments(points, closed=False)
            return self._segments_to_path(element, segments, coord_space)

        style = styles_runtime.extract_style(self, element)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")

        policy = self._policy_options("geometry")
        allow_emf_fallback, allow_bitmap_fallback = self._geometry_fallback_flags(policy)
        segments = _points_to_segments(points, closed=False)
        segments, geom_meta, render_mode = apply_geometry_policy(list(segments), policy)
        bitmap_limits = self._bitmap_fallback_limits(policy)
        if geom_meta:
            policy_meta = metadata.setdefault("policy", {}).setdefault("geometry", {})
            policy_meta.update(geom_meta)

        if style.fill and not isinstance(style.fill, SolidPaint):
            if allow_bitmap_fallback:
                render_mode = FALLBACK_BITMAP
            elif allow_emf_fallback:
                render_mode = FALLBACK_EMF

        fallback_to_bitmap = False
        if render_mode == FALLBACK_EMF:
            emf_image = self._convert_path_to_emf(
                element=element,
                style=style,
                segments=segments,
                coord_space=coord_space,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
                metadata=metadata,
            )
            if emf_image is not None:
                self._trace_geometry_decision(element, "emf", emf_image.metadata if isinstance(emf_image.metadata, dict) else metadata)
                return emf_image
            if allow_bitmap_fallback:
                self._logger.warning("Failed to build EMF fallback; attempting bitmap fallback.")
                fallback_to_bitmap = True
            else:
                self._logger.warning("Failed to build EMF fallback; bitmap fallback disabled.")

        if (render_mode == FALLBACK_BITMAP or fallback_to_bitmap) and allow_bitmap_fallback:
            bitmap_image = self._convert_path_to_bitmap(
                element=element,
                style=style,
                segments=segments,
                coord_space=coord_space,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
                metadata=metadata,
                bitmap_limits=bitmap_limits,
            )
            if bitmap_image is not None:
                if fallback_to_bitmap:
                    geometry_policy = metadata.setdefault("policy", {}).setdefault("geometry", {})
                    geometry_policy["render_mode"] = FALLBACK_BITMAP
                self._trace_geometry_decision(
                    element,
                    "bitmap",
                    bitmap_image.metadata if isinstance(bitmap_image.metadata, dict) else metadata,
                )
                return bitmap_image
            self._logger.warning("Failed to rasterize polyline; falling back to native rendering.")
        elif render_mode == FALLBACK_BITMAP and not allow_bitmap_fallback:
            self._logger.warning("Bitmap fallback disabled; falling back to native rendering.")

        if any(not isinstance(segment, LineSegment) for segment in segments):
            transformed = coord_space.apply_segments(segments)
            path_object = Path(
                segments=transformed,
                fill=style.fill,
                stroke=style.stroke,
                clip=clip_ref,
                mask=mask_ref,
                mask_instance=mask_instance,
                opacity=style.opacity,
                effects=style.effects,
                metadata=metadata,
            )
            self._trace_geometry_decision(element, "native", path_object.metadata)
            return path_object

        transformed_segments = coord_space.apply_segments(segments)
        polyline_points = _segments_to_points(transformed_segments, closed=False)
        if len(polyline_points) < 2:
            path_object = Path(
                segments=transformed_segments,
                fill=style.fill,
                stroke=style.stroke,
                clip=clip_ref,
                mask=mask_ref,
                mask_instance=mask_instance,
                opacity=style.opacity,
                effects=style.effects,
                metadata=metadata,
            )
            self._trace_geometry_decision(element, "native", path_object.metadata)
            return path_object

        polyline = Polyline(
            points=polyline_points,
            fill=style.fill,
            stroke=style.stroke,
            opacity=style.opacity,
            effects=list(style.effects),
            metadata=metadata,
        )
        self._trace_geometry_decision(element, "native", polyline.metadata)
        return polyline

    def _segments_to_path(self, element: etree._Element, segments: list[SegmentType], coord_space: CoordinateSpace):
        style = styles_runtime.extract_style(self, element)
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)
        policy = self._policy_options("geometry")
        allow_emf_fallback, allow_bitmap_fallback = self._geometry_fallback_flags(policy)
        segments, geom_meta, render_mode = apply_geometry_policy(list(segments), policy)
        bitmap_limits = self._bitmap_fallback_limits(policy)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")
        if geom_meta:
            policy_meta = metadata.setdefault("policy", {}).setdefault("geometry", {})
            policy_meta.update(geom_meta)

        if style.fill and not isinstance(style.fill, SolidPaint):
            if allow_bitmap_fallback:
                render_mode = FALLBACK_BITMAP
            elif allow_emf_fallback:
                render_mode = FALLBACK_EMF

        if render_mode == FALLBACK_EMF:
            emf_image = self._convert_path_to_emf(
                element=element,
                style=style,
                segments=segments,
                coord_space=coord_space,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
                metadata=metadata,
            )
            if emf_image is not None:
                self._trace_geometry_decision(element, "emf", emf_image.metadata if isinstance(emf_image.metadata, dict) else metadata)
                return emf_image
            self._logger.warning("Failed to build EMF fallback; reverting to native path.")
        elif render_mode == FALLBACK_BITMAP:
            if not allow_bitmap_fallback:
                self._logger.warning("Bitmap fallback disabled; falling back to native rendering.")
            else:
                bitmap_image = self._convert_path_to_bitmap(
                    element=element,
                    style=style,
                    segments=segments,
                    coord_space=coord_space,
                    clip_ref=clip_ref,
                    mask_ref=mask_ref,
                    mask_instance=mask_instance,
                    metadata=metadata,
                    bitmap_limits=bitmap_limits,
                )
                if bitmap_image is not None:
                    self._trace_geometry_decision(
                        element,
                        "bitmap",
                        bitmap_image.metadata if isinstance(bitmap_image.metadata, dict) else metadata,
                    )
                    return bitmap_image
                self._logger.warning("Failed to rasterize path; falling back to native rendering.")

        transformed = coord_space.apply_segments(segments)
        if not transformed:
            return None

        path_object = Path(
            segments=transformed,
            fill=style.fill,
            stroke=style.stroke,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            effects=style.effects,
            metadata=metadata,
        )
        self._apply_marker_metadata(element, path_object.metadata)
        self._trace_geometry_decision(element, "native", path_object.metadata)
        marker_shapes = self._build_marker_shapes(element, path_object)
        if marker_shapes:
            return [path_object, *marker_shapes]
        return path_object

    def _convert_image(self, *, element: etree._Element, coord_space: CoordinateSpace):
        href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
        if not href:
            return None
        width = _parse_float(element.get("width"))
        height = _parse_float(element.get("height"))
        if width is None or height is None or width <= 0 or height <= 0:
            return None
        x = _parse_float(element.get("x"), default=0.0) or 0.0
        y = _parse_float(element.get("y"), default=0.0) or 0.0

        rect_points = [
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
        ]
        transformed_points = [coord_space.apply_point(px, py) for (px, py) in rect_points]
        bbox = _compute_bbox(transformed_points)

        image_policy = self._policy_options("image")
        style = styles_runtime.extract_style(self, element)

        image_service = self._services.image_service
        resource = None
        if href and image_service:
            resource = image_service.resolve(href)

        color_service = getattr(self._services, "color_space_service", None)
        color_result = None
        if resource and color_service and image_policy:
            normalization = image_policy.get("colorspace_normalization", "rgb")
            color_result = color_service.normalize_resource(resource, normalization=normalization)
            resource = color_result.resource

        format_hint = _guess_image_format(
            href,
            resource.data if resource else None,
            resource.mime_type if resource else None,
        )
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)
        metadata: dict[str, Any] = dict(style.metadata)
        if resource and resource.source:
            metadata["image_source"] = resource.source
        if href:
            metadata["href"] = href
        self._attach_policy_metadata(metadata, "image")
        if image_policy:
            self._attach_policy_metadata(metadata, "image", extra=image_policy)
        if color_result:
            policy_meta = metadata.setdefault("policy", {}).setdefault("image", {})
            if color_result.result.converted:
                policy_meta["colorspace_mode"] = color_result.result.mode
                if color_result.result.warnings:
                    policy_meta["colorspace_warnings"] = list(color_result.result.warnings)
            if color_result.result.metadata:
                policy_meta.setdefault("colorspace_metadata", color_result.result.metadata)

        image = Image(
            origin=Point(bbox.x, bbox.y),
            size=bbox,
            data=resource.data if resource else None,
            format=format_hint,
            href=href,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            transform=None,
            metadata=metadata,
        )
        self._process_mask_metadata(image)
        self._trace_geometry_decision(element, "native", image.metadata)
        self._trace_stage(
            "image_embedded",
            stage="image",
            metadata={
                "format": format_hint,
                "embedded_data": bool(resource and resource.data),
                "href": href if href else None,
            },
            subject=element.get("id"),
        )
        return image

    def _convert_foreign_object(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        traverse_callback: Callable[[etree._Element, Any | None], list],
        current_navigation,
    ):
        width = _parse_float(element.get("width"))
        height = _parse_float(element.get("height"))
        if width is None or height is None or width <= 0 or height <= 0:
            return None
        x = _parse_float(element.get("x"), default=0.0) or 0.0
        y = _parse_float(element.get("y"), default=0.0) or 0.0

        rect_points = [
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
        ]
        transformed_points = [coord_space.apply_point(px, py) for (px, py) in rect_points]
        bbox = _compute_bbox(transformed_points)

        payload = _first_foreign_child(element)
        payload_type = _classify_foreign_payload(payload) if payload is not None else "empty"
        style = styles_runtime.extract_style(self, element)

        metadata: dict[str, Any] = {
            "foreign_object": {
                "payload_type": payload_type,
                "source_tag": _local_name(payload.tag) if payload is not None else None,
            }
        }
        clip_ref = ClipRef(
            clip_id=_foreign_object_clip_id(element, bbox),
            bounding_box=bbox,
        )
        mask_ref, mask_instance = self._resolve_mask_ref(element)

        if payload is None:
            placeholder = self._foreign_object_placeholder(bbox, clip_ref, mask_ref, mask_instance, metadata)
            placeholder = replace(placeholder, opacity=style.opacity)
            self._trace_geometry_decision(element, "placeholder", placeholder.metadata)
            self._trace_stage(
                "foreign_object_placeholder",
                stage="foreign_object",
                metadata=metadata.get("foreign_object"),
                subject=element.get("id"),
            )
            return placeholder

        if payload_type == "nested_svg":
            translation = Matrix2D(e=x, f=y)
            coord_space.push(translation)
            try:
                children = traverse_callback(payload, current_navigation)
            finally:
                coord_space.pop()
            if not children:
                return None
            group = Group(
                children=children, 
                clip=clip_ref, 
                mask=mask_ref, 
                mask_instance=mask_instance, 
                opacity=style.opacity,
                metadata=metadata
            )
            self._process_mask_metadata(group)
            self._trace_geometry_decision(element, "native", group.metadata)
            self._trace_stage(
                "foreign_object_nested_svg",
                stage="foreign_object",
                metadata={"child_count": len(children)},
                subject=element.get("id"),
            )
            return group

        if payload_type == "image":
            href = _extract_image_href(payload)
            if not href:
                placeholder = self._foreign_object_placeholder(bbox, clip_ref, mask_ref, mask_instance, metadata)
                return replace(placeholder, opacity=style.opacity)

            image_metadata = dict(metadata)
            image_metadata.setdefault("foreign_object", {}).setdefault("href", href)
            format_hint = _guess_image_format(href, None, None)
            image = Image(
                origin=Point(bbox.x, bbox.y),
                size=bbox,
                data=None,
                format=format_hint,
                href=href,
                clip=clip_ref,
                mask=mask_ref,
                mask_instance=mask_instance,
                opacity=style.opacity,
                transform=None,
                metadata=image_metadata,
            )
            self._process_mask_metadata(image)
            self._trace_geometry_decision(element, "native", image.metadata)
            self._trace_stage(
                "foreign_object_image",
                stage="foreign_object",
                metadata={"href": href, "format": format_hint},
                subject=element.get("id"),
            )
            return image

        if payload_type == "xhtml":
            text_content = _collect_foreign_text(payload)
            if not text_content:
                placeholder = self._foreign_object_placeholder(bbox, clip_ref, mask_ref, mask_instance, metadata)
                placeholder = replace(placeholder, opacity=style.opacity)
                self._trace_geometry_decision(element, "placeholder", placeholder.metadata)
                self._trace_stage(
                    "foreign_object_placeholder",
                    stage="foreign_object",
                    metadata=metadata.get("foreign_object"),
                    subject=element.get("id"),
                )
                return placeholder
            run = Run(text=text_content, font_family="Arial", font_size_pt=12.0)
            frame = TextFrame(
                origin=Point(bbox.x, bbox.y),
                anchor=TextAnchor.START,
                bbox=bbox,
                runs=[run],
                metadata=metadata,
            )
            # TextFrame doesn't have an 'opacity' field, but it's in metadata and runs?
            # Actually DrawingMLWriter handles text opacity per run.
            self._trace_geometry_decision(element, "native", frame.metadata)
            self._trace_stage(
                "foreign_object_text",
                stage="foreign_object",
                metadata={"character_count": len(text_content)},
                subject=element.get("id"),
            )
            return frame

        placeholder = self._foreign_object_placeholder(bbox, clip_ref, mask_ref, mask_instance, metadata)
        placeholder = replace(placeholder, opacity=style.opacity)
        self._trace_geometry_decision(element, "placeholder", placeholder.metadata)
        self._trace_stage(
            "foreign_object_placeholder",
            stage="foreign_object",
            metadata=metadata.get("foreign_object"),
            subject=element.get("id"),
        )
        return placeholder

    def _foreign_object_placeholder(
        self,
        bbox: Rect,
        clip_ref: ClipRef,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        metadata: dict[str, Any],
    ) -> Path:
        segments = _rect_segments_from_bbox(bbox)
        fill = SolidPaint(rgb="F0F0F0", opacity=_clamp01(0.4))
        stroke = Stroke(paint=SolidPaint(rgb="999999", opacity=_clamp01(1.0)), width=1.0)
        placeholder_metadata = dict(metadata)
        path = Path(
            segments=segments,
            fill=fill,
            stroke=stroke,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=_clamp01(1.0),
            metadata=placeholder_metadata,
            effects=[],
        )
        self._process_mask_metadata(path)
        return path

    def _process_mask_metadata(self, ir_object: Any) -> None:
        if ir_object is None or not hasattr(ir_object, "mask"):
            return
        mask_ref = getattr(ir_object, "mask", None)
        if mask_ref is None:
            return
            
        # Attempt to bake the mask into the fill (Wild Idea!)
        if hasattr(ir_object, "fill") and isinstance(ir_object.fill, SolidPaint):
            new_fill, new_mask_ref = try_bake_mask(
                ir_object.fill, 
                mask_ref, 
                services=getattr(self, "_services", None),
                doc_root=getattr(self, "_svg_root", None)
            )
            if new_fill is not ir_object.fill:
                # We baked it! Update the object (bypassing frozen state)
                object.__setattr__(ir_object, "fill", new_fill)
                object.__setattr__(ir_object, "mask", new_mask_ref)
                
                # If we successfully updated and mask is now None, we are done!
                if ir_object.mask is None:
                    return

        processor = getattr(self, "_mask_processor", None)
        if processor is None:
            return
        policy_options = self._policy_options("mask")
        result = processor.process(ir_object, policy_options=policy_options)
        metadata = getattr(ir_object, "metadata", None)
        if isinstance(metadata, dict) and result.metadata:
            mask_meta = metadata.setdefault("mask", {})
            mask_meta.update(result.metadata)
            if result.xml_fragment:
                mask_meta.setdefault("geometry_xml", result.xml_fragment)
        if isinstance(metadata, dict) and result.requires_emf:
            policy_meta = metadata.setdefault("policy", {}).setdefault("geometry", {})
            policy_meta.setdefault("suggest_fallback", "emf")
        if isinstance(metadata, dict):
            self._attach_policy_metadata(metadata, "mask")

    def _convert_path_to_emf(
        self,
        *,
        element: etree._Element,
        style: StyleResult,
        segments: list[SegmentType],
        coord_space: CoordinateSpace,
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        metadata: dict[str, Any],
    ) -> Image | None:
        adapter = self._get_emf_adapter()
        return fallbacks.render_emf_fallback(
            element=element,
            style=style,
            segments=segments,
            coord_space=coord_space,
            clip_ref=clip_ref,
            mask_ref=mask_ref,
            mask_instance=mask_instance,
            metadata=metadata,
            unit_converter=self._unit_converter,
            conversion_context=self._conversion_context,
            adapter=adapter,
        )

    def _convert_path_to_bitmap(
        self,
        *,
        element: etree._Element,
        style: StyleResult,
        segments: list[SegmentType],
        coord_space: CoordinateSpace,
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        metadata: dict[str, Any],
        bitmap_limits: tuple[int | None, int | None] | None,
    ) -> Image | None:
        max_area_px, max_side_px = bitmap_limits if bitmap_limits is not None else (None, None)
        return fallbacks.render_bitmap_fallback(
            element=element,
            style=style,
            segments=segments,
            coord_space=coord_space,
            clip_ref=clip_ref,
            mask_ref=mask_ref,
            mask_instance=mask_instance,
            metadata=metadata,
            flatten_segments=self._flatten_segments,
            hex_to_rgba=self._hex_to_rgba,
            max_area_px=max_area_px,
            max_side_px=max_side_px,
            logger=self._logger,
        )

    def _flatten_segments(self, segments: Iterable[SegmentType], samples: int = 12) -> list[Point]:
        points: list[Point] = []
        for segment in segments:
            if isinstance(segment, LineSegment):
                if not points:
                    points.append((segment.start.x, segment.start.y))
                points.append((segment.end.x, segment.end.y))
            elif isinstance(segment, BezierSegment):
                if not points:
                    points.append((segment.start.x, segment.start.y))
                for i in range(1, samples + 1):
                    t = i / samples
                    x, y = _bezier_point(segment, t)
                    points.append((x, y))
            else:
                start = getattr(segment, "start", None)
                if start is not None:
                    points.append((start.x, start.y))
        return points

    @staticmethod
    def _hex_to_rgba(rgb: str, opacity: float) -> tuple[int, int, int, int]:
        rgb = rgb.lstrip("#")
        r = int(rgb[0:2], 16)
        g = int(rgb[2:4], 16)
        b = int(rgb[4:6], 16)
        a = max(0, min(255, int(round(opacity * 255))))
        return (r, g, b, a)

    def _apply_marker_metadata(
        self,
        element: etree._Element,
        metadata: dict[str, Any],
    ) -> None:
        marker_runtime.apply_marker_metadata(self, element, metadata)

    def _build_marker_shapes(
        self,
        element: etree._Element,
        path: Path,
    ) -> list[Path]:
        return marker_runtime.build_marker_shapes(
            self,
            element,
            path,
            tolerance=DEFAULT_TOLERANCE,
        )

    def _transform_segments(
        self,
        segments: list[SegmentType],
        matrix: Matrix2D,
    ) -> list[SegmentType]:
        transformed: list[SegmentType] = []
        for segment in segments:
            if isinstance(segment, LineSegment):
                start = matrix.transform_point(segment.start)
                end = matrix.transform_point(segment.end)
                transformed.append(LineSegment(start=start, end=end))
            elif isinstance(segment, BezierSegment):
                transformed.append(
                    BezierSegment(
                        start=matrix.transform_point(segment.start),
                        control1=matrix.transform_point(segment.control1),
                        control2=matrix.transform_point(segment.control2),
                        end=matrix.transform_point(segment.end),
                    )
                )
            else:
                transformed.append(segment)
        return transformed

    def _get_emf_adapter(self):
        adapter = getattr(self, "_emf_adapter", None)
        if adapter is not None:
            return adapter
        services = getattr(self, "_services", None)
        if services is None:
            return None
        adapter = getattr(services, "emf_path_adapter", None)
        if adapter is None and hasattr(services, "resolve"):
            adapter = services.resolve("emf_path_adapter")
        if adapter is not None:
            self._emf_adapter = adapter
        return adapter

    def _resolve_dimension_preference(
        self,
        primary: str | None,
        fallback: str | None,
        context,
        *,
        axis: str,
    ) -> float | None:
        value = self._resolve_length(primary, context, axis=axis)
        if value not in (None, 0.0):
            return value
        value = self._resolve_length(fallback, context, axis=axis)
        if value in (None, 0.0):
            return None
        return value

    def _resolve_length(
        self,
        value: str | None,
        context,
        *,
        axis: str,
    ) -> float:
        if value in (None, "", "0"):
            return 0.0
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            try:
                return self._unit_converter.to_px(value, context, axis=axis)
            except Exception:
                return 0.0

def _parse_float(value: str | None, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        if value.endswith("%"):
            return float(value[:-1]) / 100.0
        return float(value)
    except ValueError:
        return default


def _ellipse_segments(cx: float, cy: float, rx: float, ry: float) -> list[SegmentType]:
    if rx <= 0 or ry <= 0:
        return []
    kappa = 0.5522847498307936
    top = Point(cx, cy - ry)
    right = Point(cx + rx, cy)
    bottom = Point(cx, cy + ry)
    left = Point(cx - rx, cy)

    return [
        BezierSegment(
            start=right,
            control1=Point(cx + rx, cy + kappa * ry),
            control2=Point(cx + kappa * rx, cy + ry),
            end=bottom,
        ),
        BezierSegment(
            start=bottom,
            control1=Point(cx - kappa * rx, cy + ry),
            control2=Point(cx - rx, cy + kappa * ry),
            end=left,
        ),
        BezierSegment(
            start=left,
            control1=Point(cx - rx, cy - kappa * ry),
            control2=Point(cx - kappa * rx, cy - ry),
            end=top,
        ),
        BezierSegment(
            start=top,
            control1=Point(cx + kappa * rx, cy - ry),
            control2=Point(cx + rx, cy - kappa * ry),
            end=right,
        ),
    ]


def _points_to_segments(points: Sequence[Point], *, closed: bool) -> list[SegmentType]:
    segments: list[SegmentType] = []
    for start, end in zip(points, points[1:]):
        segments.append(LineSegment(start, end))
    if closed and points:
        segments.append(LineSegment(points[-1], points[0]))
    return segments


def _segments_to_points(segments: Sequence[SegmentType], *, closed: bool) -> list[Point]:
    if not segments:
        return []
    points: list[Point] = []
    first = getattr(segments[0], "start", None)
    if isinstance(first, Point):
        points.append(first)
    for segment in segments:
        end = getattr(segment, "end", None)
        if isinstance(end, Point):
            points.append(end)
    if closed and len(points) > 1:
        if _points_close(points[0], points[-1]):
            points.pop()
    return points


def _parse_points(value: str | None) -> list[Point]:
    if not value:
        return []
    cleaned = value.replace(",", " ")
    parts = cleaned.split()
    if len(parts) % 2 != 0:
        parts = parts[:-1]
    points: list[Point] = []
    it = iter(parts)
    for x_str, y_str in zip(it, it):
        x = _parse_float(x_str)
        y = _parse_float(y_str)
        if x is None or y is None:
            continue
        points.append(Point(x, y))
    return points


def _has_markers(element: etree._Element) -> bool:
    for attr in ("marker-start", "marker-mid", "marker-end"):
        if element.get(attr):
            return True
    style_attr = element.get("style")
    if not style_attr:
        return False
    for chunk in style_attr.split(";"):
        if ":" not in chunk:
            continue
        name, value = chunk.split(":", 1)
        name = name.strip()
        value = value.strip()
        if name in {"marker-start", "marker-mid", "marker-end"} and value:
            return True
    return False


def _points_close(a: Point, b: Point, tolerance: float = DEFAULT_TOLERANCE) -> bool:
    return abs(a.x - b.x) <= tolerance and abs(a.y - b.y) <= tolerance


def _compute_bbox(points: Iterable[tuple[float, float]]) -> Rect:
    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return Rect(min_x, min_y, max_x - min_x, max_y - min_y)


def _guess_image_format(href: str | None, data: bytes | None, mime: str | None) -> str:
    if mime:
        if "png" in mime:
            return "png"
        if "jpeg" in mime or "jpg" in mime:
            return "jpg"
        if "gif" in mime:
            return "gif"
        if "svg" in mime:
            return "svg"
    if href:
        lower = href.lower()
        for suffix in (".png", ".jpg", ".jpeg", ".gif", ".svg"):
            if lower.endswith(suffix):
                return suffix.strip(".")
    return "png"


def _local_name(tag: str | None) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _foreign_object_clip_id(element: etree._Element, bbox: Rect) -> str:
    element_id = element.get("id")
    if element_id:
        return f"foreignObject:{element_id}"
    return f"foreignObject:{bbox.x:.4f},{bbox.y:.4f},{bbox.width:.4f},{bbox.height:.4f}"


def _first_foreign_child(element: etree._Element) -> etree._Element | None:
    for child in element:
        if isinstance(child.tag, str):
            return child
    return None


def _classify_foreign_payload(payload: etree._Element | None) -> str:
    if payload is None:
        return "empty"
    tag = _local_name(payload.tag).lower()
    namespace = ""
    if isinstance(payload.tag, str) and "}" in payload.tag:
        namespace = payload.tag.split("}", 1)[0][1:]

    if tag == "svg":
        return "nested_svg"

    if tag in {"img", "image", "object", "picture"}:
        if _extract_image_href(payload):
            return "image"

    xhtml_tags = {
        "p",
        "div",
        "span",
        "table",
        "tbody",
        "tr",
        "td",
        "th",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        "a",
        "em",
        "strong",
        "b",
        "i",
        "u",
        "br",
        "hr",
        "pre",
        "code",
        "blockquote",
    }
    if tag in xhtml_tags or "xhtml" in namespace.lower() or "html" in namespace.lower():
        return "xhtml"

    return "unknown"


def _extract_image_href(element: etree._Element) -> str | None:
    return (
        element.get("src")
        or element.get("href")
        or element.get("xlink:href")
        or element.get("{http://www.w3.org/1999/xlink}href")
    )


def _collect_foreign_text(element: etree._Element) -> str:
    parts: list[str] = []
    if element.text:
        parts.append(element.text.strip())
    for child in element:
        child_text = _collect_foreign_text(child)
        if child_text:
            parts.append(child_text)
        if child.tail:
            parts.append(child.tail.strip())
    return " ".join(part for part in parts if part)


def _rect_segments_from_bbox(bbox: Rect) -> list[SegmentType]:
    points = [
        Point(bbox.x, bbox.y),
        Point(bbox.x + bbox.width, bbox.y),
        Point(bbox.x + bbox.width, bbox.y + bbox.height),
        Point(bbox.x, bbox.y + bbox.height),
    ]
    return _points_to_segments(points, closed=True)


def _uniform_scale(matrix: Matrix2D, tolerance: float) -> float | None:
    scale_x = (matrix.a**2 + matrix.b**2) ** 0.5
    scale_y = (matrix.c**2 + matrix.d**2) ** 0.5
    if scale_x <= tolerance or scale_y <= tolerance:
        return None
    if abs(scale_x - scale_y) > tolerance:
        return None
    if abs(matrix.a * matrix.c + matrix.b * matrix.d) > tolerance:
        return None
    return scale_x


def _bezier_point(segment: BezierSegment, t: float) -> Point:
    inv_t = 1 - t
    x = (
        inv_t ** 3 * segment.start.x
        + 3 * inv_t ** 2 * t * segment.control1.x
        + 3 * inv_t * t ** 2 * segment.control2.x
        + t ** 3 * segment.end.x
    )
    y = (
        inv_t ** 3 * segment.start.y
        + 3 * inv_t ** 2 * t * segment.control1.y
        + 3 * inv_t * t ** 2 * segment.control2.y
        + t ** 3 * segment.end.y
    )
    return x, y


__all__ = ["ShapeConversionMixin"]
