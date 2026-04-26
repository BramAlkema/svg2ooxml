"""Main resvg-backed shape conversion traversal."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.paint import PatternPaint
from svg2ooxml.ir.scene import ClipRef, Group, MaskInstance, MaskRef


class ResvgConversionMixin:
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

        if hasattr(self, "_local_name"):
            element_local = self._local_name(element.tag).lower()
        else:
            element_local = (
                element.tag.split("}")[-1].lower()
                if isinstance(element.tag, str)
                else ""
            )

        # Extract style (same as legacy path)
        # Keep runtime-style lookup patchable via the legacy module path.
        from svg2ooxml.core.ir import shape_converters as shape_converters_module

        style = shape_converters_module.styles_runtime.extract_style(self, element)
        use_paint_dict: Mapping[str, Any] | None = None
        if element_local == "use":
            try:
                use_paint_dict = (
                    self._style_extractor._compute_paint_style_with_inheritance(
                        element,
                        context=self._css_context,
                    )
                )
            except Exception:
                use_paint_dict = self._style_resolver.compute_paint_style(
                    element,
                    context=self._css_context,
                )
            style = self._materialize_style(element, dict(use_paint_dict))
        style = self._style_with_local_opacity(element, style)
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
            if element_local == "use":
                paint_dict = self._style_resolver.compute_paint_style(
                    source_element, context=self._css_context
                )
                source_style = self._materialize_style(source_element, paint_dict)
                style = self._merge_use_styles(
                    style,
                    source_style,
                    use_element=element,
                    source_element=source_element,
                    use_paint_style=use_paint_dict,
                )
                metadata.update(source_style.metadata or {})

        # For <use> elements, resvg expansion does not apply viewBox scaling or
        # the <use> element's own transform. Rebuild the local transform to keep
        # parity with legacy behavior.
        use_global_override: Matrix2D | None = None
        original_global_transform = global_transform
        if element_local == "use" and isinstance(source_element, etree._Element):
            from svg2ooxml.core.styling.use_expander import (
                compose_use_transform,
            )

            combined = compose_use_transform(
                self,
                element,
                source_element,
                tolerance=DEFAULT_TOLERANCE,
            )
            local_transform = self._matrix_from_transform(element.get("transform"))
            try:
                parent_transform = coord_space.current.multiply(local_transform.inverse())
            except Exception:
                parent_transform = coord_space.current
            use_global_override = parent_transform.multiply(combined)
            global_transform = use_global_override

        # Resvg's local tree currently omits nested <svg> viewport transforms.
        # The traversal CTM includes them, plus ordinary XML transforms.
        if element_local != "use":
            global_transform = coord_space.current

        def _resolved_paint_opacity(
            opacity_source: etree._Element | None,
            key: str,
        ) -> float:
            if opacity_source is None:
                opacity_source = element
            try:
                paint_style = (
                    self._style_extractor._compute_paint_style_with_inheritance(
                        opacity_source,
                        context=self._css_context,
                    )
                )
            except Exception:
                return 1.0
            return self._style_opacity(paint_style, key)

        def _apply_resvg_paint_overrides(
            node,
            base_style: StyleResult,
            *,
            preserve_base_paint_opacity: bool = False,
            preserve_base_paint_presence: bool = False,
        ) -> StyleResult:
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
                        preserve_base_paint_presence
                        and updated.stroke is None
                        and not self._source_has_property(source_element, "stroke")
                    ):
                        pass
                    else:
                        stroke_paint = resvg_stroke.paint
                        if (
                            isinstance(stroke_paint, PatternPaint)
                            and updated.stroke is not None
                            and isinstance(updated.stroke.paint, PatternPaint)
                        ):
                            stroke_paint = self._merge_pattern_paint(
                                stroke_paint,
                                updated.stroke.paint,
                            )
                        elif preserve_base_paint_opacity and updated.stroke is not None:
                            stroke_paint = self._paint_with_base_opacity(
                                stroke_paint,
                                updated.stroke.paint,
                            )
                        elif preserve_base_paint_opacity:
                            stroke_paint = self._paint_with_opacity(
                                stroke_paint,
                                _resolved_paint_opacity(
                                    source_element,
                                    "stroke_opacity",
                                ),
                            )
                        if updated.stroke is not None:
                            resvg_stroke = replace(
                                resvg_stroke,
                                width=updated.stroke.width,
                                join=updated.stroke.join,
                                cap=updated.stroke.cap,
                                miter_limit=updated.stroke.miter_limit,
                                dash_array=updated.stroke.dash_array,
                                dash_offset=updated.stroke.dash_offset,
                                opacity=updated.stroke.opacity,
                            )
                        updated = replace(
                            updated,
                            stroke=replace(resvg_stroke, paint=stroke_paint),
                        )
            elif self._source_explicitly_disables_paint(source_element, "stroke"):
                updated = replace(updated, stroke=None)
            if hasattr(node, "fill") and node.fill is not None:
                from svg2ooxml.paint.resvg_bridge import resolve_fill_paint

                resvg_fill = resolve_fill_paint(node.fill, tree)
                if resvg_fill is not None:
                    if (
                        preserve_base_paint_presence
                        and updated.fill is None
                        and not self._source_has_property(source_element, "fill")
                    ):
                        return updated
                    if isinstance(resvg_fill, PatternPaint) and isinstance(
                        updated.fill, PatternPaint
                    ):
                        resvg_fill = self._merge_pattern_paint(resvg_fill, updated.fill)
                    elif preserve_base_paint_opacity:
                        preserved_fill = self._paint_with_base_opacity(
                            resvg_fill,
                            updated.fill,
                        )
                        if preserved_fill is resvg_fill:
                            resvg_fill = self._paint_with_opacity(
                                resvg_fill,
                                _resolved_paint_opacity(
                                    source_element,
                                    "fill_opacity",
                                ),
                            )
                        else:
                            resvg_fill = preserved_fill
                    updated = replace(updated, fill=resvg_fill)
                elif self._source_explicitly_disables_paint(source_element, "fill"):
                    updated = replace(updated, fill=None)
            elif self._source_explicitly_disables_paint(source_element, "fill"):
                updated = replace(updated, fill=None)
            return updated

        style = _apply_resvg_paint_overrides(
            resvg_node,
            style,
            preserve_base_paint_opacity=True,
            preserve_base_paint_presence=element_local == "use",
        )

        node_type = type(resvg_node).__name__
        # Get clip/mask refs
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)
        if element_local == "use" and isinstance(source_element, etree._Element):
            if clip_ref is None:
                clip_ref = self._resolve_clip_ref(source_element)
            if mask_ref is None and mask_instance is None:
                mask_ref, mask_instance = self._resolve_mask_ref(source_element)

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

                def _node_source_element(node) -> etree._Element | None:
                    source = getattr(node, "source", None)
                    return source if isinstance(source, etree._Element) else None

                def _style_for_resvg_node(
                    node,
                    fallback_style: StyleResult,
                ) -> StyleResult:
                    node_source = _node_source_element(node)
                    if node_source is not None:
                        paint_dict = self._style_resolver.compute_paint_style(
                            node_source,
                            context=self._css_context,
                        )
                        node_style = self._materialize_style(node_source, paint_dict)
                        node_style = self._style_with_local_opacity(
                            node_source,
                            node_style,
                        )
                        if element_local == "use":
                            node_style = self._merge_use_styles(
                                fallback_style,
                                node_style,
                                use_element=element,
                                source_element=node_source,
                                use_paint_style=use_paint_dict,
                                multiply_opacity=False,
                            )
                    else:
                        node_style = replace(fallback_style, opacity=1.0)
                    return _apply_resvg_paint_overrides(
                        node,
                        node_style,
                        preserve_base_paint_opacity=node_source is not None,
                        preserve_base_paint_presence=element_local == "use",
                    )

                def _metadata_for_resvg_node(
                    node,
                    node_style: StyleResult,
                ) -> dict[str, Any]:
                    node_metadata = dict(node_style.metadata)
                    self._attach_policy_metadata(node_metadata, "geometry")
                    node_source = _node_source_element(node)
                    if node_source is not None:
                        self._append_metadata_element_id(
                            node_metadata,
                            node_source.get("id"),
                        )
                    use_instance = getattr(node, "use_source", None)
                    if isinstance(use_instance, etree._Element):
                        self._append_metadata_element_id(
                            node_metadata,
                            use_instance.get("id"),
                        )
                    return node_metadata

                def _clip_mask_for_source(
                    child_element: etree._Element | None,
                ) -> tuple[ClipRef | None, MaskRef | None, MaskInstance | None]:
                    if child_element is None:
                        return None, None, None
                    child_clip_ref = self._resolve_clip_ref(child_element)
                    child_mask_ref, child_mask_instance = self._resolve_mask_ref(
                        child_element
                    )
                    return child_clip_ref, child_mask_ref, child_mask_instance

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
                        child_style = _style_for_resvg_node(child, parent_style)
                        child_metadata = _metadata_for_resvg_node(child, child_style)
                        child_source_element = _node_source_element(child)
                        child_element = child_source_element if child_source_element is not None else element
                        (
                            child_clip_ref,
                            child_mask_ref,
                            child_mask_instance,
                        ) = _clip_mask_for_source(child_source_element)
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
                                        clip=child_clip_ref,
                                        mask=child_mask_ref,
                                        mask_instance=child_mask_instance,
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
                                element=child_element,
                                resvg_node=child_proxy,
                                style=child_style,
                                metadata=child_metadata,
                                clip_ref=child_clip_ref,
                                mask_ref=child_mask_ref,
                                mask_instance=child_mask_instance,
                            )
                            if rectangle is not None:
                                result_shapes.append(rectangle)
                                continue
                        if child_node_type == "CircleNode":
                            circle = self._resvg_circle_to_circle(
                                element=child_element,
                                resvg_node=child_proxy,
                                style=child_style,
                                metadata=child_metadata,
                                clip_ref=child_clip_ref,
                                mask_ref=child_mask_ref,
                                mask_instance=child_mask_instance,
                            )
                            if circle is not None:
                                result_shapes.append(circle)
                                continue
                        if child_node_type == "EllipseNode":
                            ellipse = self._resvg_ellipse_to_ellipse(
                                element=child_element,
                                resvg_node=child_proxy,
                                style=child_style,
                                metadata=child_metadata,
                                clip_ref=child_clip_ref,
                                mask_ref=child_mask_ref,
                                mask_instance=child_mask_instance,
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
                                child_element.get("id") or f"<{child_node_type}>",
                                exc,
                            )
                            segments = None

                        if segments:
                            child_shape = self._resvg_segments_to_path(
                                element=child_element,
                                segments=segments,
                                coord_space=CoordinateSpace(),
                                style=child_style,
                                metadata=child_metadata,
                                clip_ref=child_clip_ref,
                                mask_ref=child_mask_ref,
                                mask_instance=child_mask_instance,
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
