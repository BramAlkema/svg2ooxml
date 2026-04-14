"""Resvg-backed shape conversion mixin."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.core.ir.shape_converters_utils import (
    _uniform_scale,
)
from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.core.styling.style_helpers import parse_style_attr
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.core.traversal.geometry_utils import (
    is_axis_aligned,
    scaled_corner_radius,
    transform_axis_aligned_rect,
)
from svg2ooxml.ir.geometry import Point
from svg2ooxml.ir.paint import PatternPaint, Stroke, StrokeCap, StrokeJoin
from svg2ooxml.ir.scene import ClipRef, Group, MaskInstance, MaskRef
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle


class ShapeResvgMixin:
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
    def _matrix2d_from_resvg(matrix: Matrix2D | None) -> Matrix2D:
        if matrix is None:
            return Matrix2D.identity()
        if isinstance(matrix, Matrix2D):
            return matrix
        # Fallback: assume resvg Matrix signature (a, b, c, d, e, f)
        return Matrix2D.from_values(
            ShapeResvgMixin._coerce_float(getattr(matrix, "a", None), 1.0),
            ShapeResvgMixin._coerce_float(getattr(matrix, "b", None), 0.0),
            ShapeResvgMixin._coerce_float(getattr(matrix, "c", None), 0.0),
            ShapeResvgMixin._coerce_float(getattr(matrix, "d", None), 1.0),
            ShapeResvgMixin._coerce_float(getattr(matrix, "e", None), 0.0),
            ShapeResvgMixin._coerce_float(getattr(matrix, "f", None), 0.0),
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

        x = ShapeResvgMixin._coerce_float(getattr(resvg_node, "x", None), 0.0)
        y = ShapeResvgMixin._coerce_float(getattr(resvg_node, "y", None), 0.0)
        width = ShapeResvgMixin._coerce_float(getattr(resvg_node, "width", None), 0.0)
        height = ShapeResvgMixin._coerce_float(getattr(resvg_node, "height", None), 0.0)

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

        rx = ShapeResvgMixin._coerce_float(getattr(resvg_node, "rx", None), 0.0)
        ry = ShapeResvgMixin._coerce_float(getattr(resvg_node, "ry", None), 0.0)
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
        cx = ShapeResvgMixin._coerce_float(getattr(resvg_node, "cx", None), 0.0)
        cy = ShapeResvgMixin._coerce_float(getattr(resvg_node, "cy", None), 0.0)
        raw_radius = ShapeResvgMixin._coerce_float(getattr(resvg_node, "r", None), 0.0)
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

        cx = ShapeResvgMixin._coerce_float(getattr(resvg_node, "cx", None), 0.0)
        cy = ShapeResvgMixin._coerce_float(getattr(resvg_node, "cy", None), 0.0)
        raw_rx = ShapeResvgMixin._coerce_float(getattr(resvg_node, "rx", None), 0.0)
        raw_ry = ShapeResvgMixin._coerce_float(getattr(resvg_node, "ry", None), 0.0)

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

    def _merge_use_styles(
        self, use_style: StyleResult, source_style: StyleResult | None
    ) -> StyleResult:
        if source_style is None:
            return use_style

        fill = source_style.fill if source_style.fill is not None else use_style.fill
        stroke = self._combine_strokes(use_style.stroke, source_style.stroke)

        opacity = (
            use_style.opacity if use_style.opacity != 1.0 else source_style.opacity
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

    def _convert_via_resvg(self, element: etree._Element, coord_space: CoordinateSpace):
        """Convert element using resvg adapters."""
        from svg2ooxml.drawingml.bridges.resvg_shape_adapter import ResvgShapeAdapter

        # Look up resvg node
        resvg_lookup = getattr(self, "_resvg_element_lookup", {})
        resvg_node = resvg_lookup.get(element)
        if resvg_node is None:
            return None

        # Retrieve the world-space global transform computed during ResvgBridge build.
        # This includes all inherited group transforms (translate, scale, etc.)
        # We use the structural signature path as a stable key.
        from svg2ooxml.core.ir.resvg_bridge import ResvgBridge

        sig = ResvgBridge._element_signature(element)
        global_transform_lookup = getattr(self, "_resvg_global_transform_lookup", {})
        global_transform = global_transform_lookup.get(sig)

        if global_transform is None:
            node_transform_lookup = getattr(self, "_resvg_node_transform_lookup", {})
            global_transform = node_transform_lookup.get(id(resvg_node))
            if global_transform is None:
                self._logger.warning("No global transform found for signature: %s", sig)

        # We replace the node's local transform with the global one before passing it
        # to the converters/adapters. This is safe because we're not modifying the
        # original tree, just how we interpret this specific node.
        # Note: We must be careful not to actually 'set' it on the frozen dataclass
        # if it's frozen, but we can pass it explicitly or use a proxy.
        # For now, let's just use it in the specialized converters.

        # Extract style (same as legacy path)
        # Keep runtime-style lookup patchable via the legacy module path.
        from svg2ooxml.core.ir import shape_converters as shape_converters_module

        style = shape_converters_module.styles_runtime.extract_style(self, element)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")

        use_source = getattr(resvg_node, "use_source", None)
        source_element = None
        if isinstance(use_source, etree._Element):
            href_attr = use_source.get(
                "{http://www.w3.org/1999/xlink}href"
            ) or use_source.get("href")
            reference_id = self._normalize_href_reference(href_attr)
            if reference_id:
                source_element = self._element_index.get(reference_id)
        if source_element is None:
            source_element = getattr(resvg_node, "source", None)
        source_style: StyleResult | None = None
        if isinstance(source_element, etree._Element):
            self._append_metadata_element_id(metadata, source_element.get("id"))
            paint_dict = self._style_resolver.compute_paint_style(
                source_element, context=self._css_context
            )
            source_style = self._materialize_style(source_element, paint_dict)
            style = self._merge_use_styles(style, source_style)
            metadata.update(source_style.metadata or {})

        # For <use> elements, resvg expansion does not apply viewBox scaling or
        # the <use> element's own transform. Rebuild the local transform to keep
        # parity with legacy behavior.
        use_global_override: Matrix2D | None = None
        original_global_transform = global_transform
        if hasattr(self, "_local_name"):
            element_local = self._local_name(element.tag).lower()
        else:
            element_local = (
                element.tag.split("}")[-1].lower()
                if isinstance(element.tag, str)
                else ""
            )
        if element_local == "use" and isinstance(source_element, etree._Element):
            from svg2ooxml.core.styling.use_expander import (
                compose_use_transform,
                compute_use_transform,
            )

            use_matrix = compute_use_transform(
                self, element, source_element, tolerance=DEFAULT_TOLERANCE
            )
            if use_matrix is not None and not use_matrix.is_identity(
                tolerance=DEFAULT_TOLERANCE
            ):
                combined = compose_use_transform(
                    self,
                    element,
                    source_element,
                    tolerance=DEFAULT_TOLERANCE,
                )
                if global_transform is None:
                    use_global_override = combined
                else:
                    local_transform = self._matrix2d_from_resvg(
                        getattr(resvg_node, "transform", None)
                    )
                    try:
                        parent_transform = self._matrix2d_from_resvg(
                            global_transform
                        ).multiply(local_transform.inverse())
                    except Exception:
                        parent_transform = self._matrix2d_from_resvg(global_transform)
                    use_global_override = parent_transform.multiply(combined)
                if use_global_override is not None:
                    global_transform = use_global_override

        def _apply_resvg_paint_overrides(node, base_style: StyleResult) -> StyleResult:
            updated = base_style
            tree = getattr(self, "_resvg_tree", None)
            if tree is None:
                return updated
            source_element = getattr(node, "source", None)
            if not isinstance(source_element, etree._Element):
                source_element = None
            if hasattr(node, "stroke") and node.stroke is not None:
                from svg2ooxml.paint.resvg_bridge import resolve_stroke_style

                resvg_stroke = resolve_stroke_style(node.stroke, tree)
                if resvg_stroke is not None and resvg_stroke.paint is not None:
                    if (
                        isinstance(resvg_stroke.paint, PatternPaint)
                        and updated.stroke is not None
                        and isinstance(updated.stroke.paint, PatternPaint)
                    ):
                        resvg_stroke = replace(
                            resvg_stroke,
                            paint=self._merge_pattern_paint(
                            resvg_stroke.paint, updated.stroke.paint
                        ),
                    )
                updated = replace(updated, stroke=resvg_stroke)
            elif self._source_explicitly_disables_paint(source_element, "stroke"):
                updated = replace(updated, stroke=None)
            if hasattr(node, "fill") and node.fill is not None:
                from svg2ooxml.paint.resvg_bridge import resolve_fill_paint

                resvg_fill = resolve_fill_paint(node.fill, tree)
                if resvg_fill is not None:
                    if isinstance(resvg_fill, PatternPaint) and isinstance(
                        updated.fill, PatternPaint
                    ):
                        resvg_fill = self._merge_pattern_paint(resvg_fill, updated.fill)
                    updated = replace(updated, fill=resvg_fill)
                elif self._source_explicitly_disables_paint(source_element, "fill"):
                    updated = replace(updated, fill=None)
            elif self._source_explicitly_disables_paint(source_element, "fill"):
                updated = replace(updated, fill=None)
            return updated

        style = _apply_resvg_paint_overrides(resvg_node, style)

        node_type = type(resvg_node).__name__
        # Get clip/mask refs
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)

        # Create a modified proxy of the node that carries the GLOBAL transform
        # for the native converters and adapters.
        class GlobalTransformProxy:
            def __init__(self, target, g_transform):
                self._target = target
                self.transform = g_transform

            def __getattr__(self, name):
                return getattr(self._target, name)

        proxy_node = GlobalTransformProxy(resvg_node, global_transform)

        if node_type == "RectNode":
            rectangle = self._resvg_rect_to_rectangle(
                element=element,
                resvg_node=proxy_node,
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
                resvg_node=proxy_node,
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
                resvg_node=proxy_node,
                style=style,
                metadata=metadata,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
            )
            if ellipse is not None:
                self._trace_geometry_decision(element, "resvg", ellipse.metadata)
                return ellipse

        if node_type in ("GenericNode", "GroupNode"):
            children = getattr(resvg_node, "children", []) or []
            if children:
                node_transform_lookup = getattr(
                    self, "_resvg_node_transform_lookup", {}
                )

                def _convert_resvg_children(nodes, parent_style, parent_global=None):
                    """Recursively convert resvg child nodes, flattening nested groups."""
                    result_shapes: list[Any] = []
                    for child in nodes:
                        # Lookup pre-computed global transform (works for nodes present
                        # during ResvgBridge.build). For deep-copied <use> clones,
                        # compute from parent + local.
                        looked_up = node_transform_lookup.get(id(child))
                        if looked_up is not None:
                            child_global = self._matrix2d_from_resvg(looked_up)
                            # Re-base when <use> viewBox override changes the parent
                            if (
                                use_global_override is not None
                                and original_global_transform is not None
                            ):
                                try:
                                    relative = (
                                        self._matrix2d_from_resvg(
                                            original_global_transform,
                                        )
                                        .inverse()
                                        .multiply(child_global)
                                    )
                                    child_global = use_global_override.multiply(
                                        relative
                                    )
                                except Exception:
                                    pass
                        else:
                            # Clone nodes (from <use> expansion): the adapter will
                            # apply the node's own local transform, so the proxy
                            # only needs the parent's global.
                            child_global = parent_global
                        child_proxy = GlobalTransformProxy(child, child_global)
                        child_style = _apply_resvg_paint_overrides(child, parent_style)
                        child_metadata = dict(metadata)
                        child_node_type = type(child).__name__

                        # Recurse into nested groups
                        if child_node_type in ("GenericNode", "GroupNode"):
                            nested = getattr(child, "children", []) or []
                            if nested:
                                nested_shapes = _convert_resvg_children(
                                    nested, child_style, child_global
                                )
                                if nested_shapes:
                                    sub_group = Group(
                                        children=nested_shapes,
                                        opacity=(
                                            child_style.opacity
                                            if child_style.opacity != 1.0
                                            else 1.0
                                        ),
                                        metadata=child_metadata,
                                    )
                                    result_shapes.append(sub_group)
                            continue

                        if child_node_type == "RectNode":
                            rectangle = self._resvg_rect_to_rectangle(
                                element=element,
                                resvg_node=child_proxy,
                                style=child_style,
                                metadata=child_metadata,
                                clip_ref=clip_ref,
                                mask_ref=mask_ref,
                                mask_instance=mask_instance,
                            )
                            if rectangle is not None:
                                result_shapes.append(rectangle)
                                continue
                        if child_node_type == "CircleNode":
                            circle = self._resvg_circle_to_circle(
                                element=element,
                                resvg_node=child_proxy,
                                style=child_style,
                                metadata=child_metadata,
                                clip_ref=clip_ref,
                                mask_ref=mask_ref,
                                mask_instance=mask_instance,
                            )
                            if circle is not None:
                                result_shapes.append(circle)
                                continue
                        if child_node_type == "EllipseNode":
                            ellipse = self._resvg_ellipse_to_ellipse(
                                element=element,
                                resvg_node=child_proxy,
                                style=child_style,
                                metadata=child_metadata,
                                clip_ref=clip_ref,
                                mask_ref=mask_ref,
                                mask_instance=mask_instance,
                            )
                            if ellipse is not None:
                                result_shapes.append(ellipse)
                                continue

                        adapter = ResvgShapeAdapter()
                        try:
                            if child_node_type == "PathNode":
                                segments = adapter.from_path_node(child_proxy)
                            elif child_node_type == "RectNode":
                                segments = adapter.from_rect_node(child_proxy)
                            elif child_node_type == "CircleNode":
                                segments = adapter.from_circle_node(child_proxy)
                            elif child_node_type == "EllipseNode":
                                segments = adapter.from_ellipse_node(child_proxy)
                            elif child_node_type == "LineNode":
                                segments = adapter.from_line_node(child_proxy)
                            elif child_node_type == "PolyNode":
                                segments = adapter.from_poly_node(child_proxy)
                            else:
                                segments = None
                        except Exception as exc:
                            self._logger.debug(
                                "Resvg adapter failed for %s child: %s",
                                element.get("id") or f"<{child_node_type}>",
                                exc,
                            )
                            segments = None

                        if segments:
                            child_shape = self._resvg_segments_to_path(
                                element=element,
                                segments=segments,
                                coord_space=CoordinateSpace(),
                                style=child_style,
                                metadata=child_metadata,
                                clip_ref=clip_ref,
                                mask_ref=mask_ref,
                                mask_instance=mask_instance,
                            )
                            if isinstance(child_shape, list):
                                result_shapes.extend(child_shape)
                            elif child_shape is not None:
                                result_shapes.append(child_shape)
                    return result_shapes

                group_children = _convert_resvg_children(
                    children, style, global_transform
                )
                if group_children:
                    group = Group(
                        children=group_children,
                        clip=clip_ref,
                        mask=mask_ref,
                        mask_instance=mask_instance,
                        opacity=style.opacity,
                        metadata=metadata,
                    )
                    self._trace_geometry_decision(element, "resvg", group.metadata)
                    return group

        # Convert using resvg adapter
        adapter = ResvgShapeAdapter()
        segments = None

        # Route to appropriate adapter method based on node type
        try:
            if node_type == "PathNode":
                segments = adapter.from_path_node(proxy_node)
            elif node_type == "RectNode":
                segments = adapter.from_rect_node(proxy_node)
            elif node_type == "CircleNode":
                segments = adapter.from_circle_node(proxy_node)
            elif node_type == "EllipseNode":
                segments = adapter.from_ellipse_node(proxy_node)
            elif node_type == "LineNode":
                segments = adapter.from_line_node(proxy_node)
            elif node_type == "PolyNode":
                segments = adapter.from_poly_node(proxy_node)
            else:
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

        # Resvg segments already have transforms applied, so use an identity coord space
        # for geometry policy + fallback rendering (EMF/bitmap) to avoid double transforms.
        resvg_coord_space = CoordinateSpace()
        return self._resvg_segments_to_path(
            element=element,
            segments=segments,
            coord_space=resvg_coord_space,
            style=style,
            metadata=metadata,
            clip_ref=clip_ref,
            mask_ref=mask_ref,
            mask_instance=mask_instance,
        )
