"""Traversal-related hooks for the IR converter."""

from __future__ import annotations

import functools
from typing import Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.common.style.resolver import StyleContext as CSSStyleContext
from svg2ooxml.common.svg_refs import local_url_id, namespace_uri
from svg2ooxml.core.parser.switch_evaluator import SwitchEvaluator
from svg2ooxml.core.styling import style_runtime, use_expander
from svg2ooxml.core.traversal.clipping_hooks import ClippingHooksMixin
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.core.traversal.runtime import local_name
from svg2ooxml.core.traversal.shape_creation_hooks import ShapeCreationMixin
from svg2ooxml.core.traversal.styling_hooks import StylingHooksMixin
from svg2ooxml.ir.scene import Group


class TraversalHooksMixin(ShapeCreationMixin, StylingHooksMixin, ClippingHooksMixin):
    """Mixin exposing traversal callbacks consumed by :class:`ElementTraversal`."""

    _css_context: CSSStyleContext | None = None
    _SUPPORTED_FEATURES = {
        "http://www.w3.org/TR/SVG11/feature#BasicText",
    }
    _STRATEGY_RANK = {
        "native": 4,
        "resvg": 3,
        "vector": 2,
        "emf": 2,
        "raster": 1,
        "legacy": 0,
        "auto": 0,
    }

    def convert_group(
        self, element: etree._Element, children: list, matrix
    ) -> Group | None:
        if not children:
            return None
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)

        style = style_runtime.extract_style(self, element)
        style = self._style_with_local_opacity(element, style)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")
        group = Group(
            children=children,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            transform=None if matrix.is_identity() else matrix,
            metadata=metadata,
        )
        self._trace_geometry_decision(element, "native", group.metadata)
        return group

    @functools.cached_property
    def _dispatch(self) -> dict[str, Any]:
        return {
            "rect": self._convert_rect,
            "circle": self._convert_circle,
            "ellipse": self._convert_ellipse,
            "line": self._convert_line,
            "path": self._convert_path,
            "polygon": self._convert_polygon,
            "polyline": self._convert_polyline,
            "image": self._convert_image,
            "text": self._text_converter.convert,
            "use": self._convert_use,
        }

    def convert_element(
        self,
        *,
        tag: str,
        element: etree._Element,
        coord_space: CoordinateSpace,
        current_navigation,
        traverse_callback,
    ):
        if not tag:
            return None

        try:
            if tag == "foreignObject":
                return self._convert_foreign_object(
                    element=element,
                    coord_space=coord_space,
                    traverse_callback=traverse_callback,
                    current_navigation=current_navigation,
                )

            if tag == "switch":
                return self._convert_switch(
                    element=element,
                    coord_space=coord_space,
                    current_navigation=current_navigation,
                    traverse_callback=traverse_callback,
                )

            handler = self._dispatch.get(tag)
            if handler is None:
                return None

            if tag == "use":
                return handler(
                    element=element,
                    coord_space=coord_space,
                    current_navigation=current_navigation,
                    traverse_callback=traverse_callback,
                )
            if tag == "text":
                resvg_lookup = getattr(self, "_resvg_element_lookup", {})
                resvg_node = (
                    resvg_lookup.get(element)
                    if isinstance(resvg_lookup, dict)
                    else None
                )
                return handler(
                    element=element, coord_space=coord_space, resvg_node=resvg_node
                )
            return handler(element=element, coord_space=coord_space)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger = getattr(self, "_logger", None)
            if logger is not None:
                logger.exception("Failed to convert <%s>: %s", tag, exc)
            self._trace_stage(
                "conversion_error",
                stage="conversion",
                subject=element.get("id"),
                metadata={
                    "tag": tag,
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
            )
            return None

    def attach_metadata(
        self, ir_object, element: etree._Element, navigation_spec
    ) -> None:
        if ir_object is None or not hasattr(ir_object, "metadata"):
            return
        metadata: dict[str, Any] = ir_object.metadata  # type: ignore[attr-defined]

        def _append_element_id(value: str | None) -> None:
            if not isinstance(value, str) or not value:
                return
            element_ids = metadata.setdefault("element_ids", [])
            if not isinstance(element_ids, list):
                element_ids = []
                metadata["element_ids"] = element_ids
            if value not in element_ids:
                element_ids.append(value)

        _append_element_id(element.get("data-svg2ooxml-source-id"))
        _append_element_id(element.get("id"))

        class_attr = element.get("class")
        if class_attr:
            metadata["class"] = class_attr

        title = element.get("title")
        if title:
            metadata.setdefault("attributes", {})["title"] = title

        # Extract <title> and <desc> child elements for accessibility (cNvPr descr)
        desc_parts: list[str] = []
        ns = element.nsmap.get(None, "")
        for tag in ("title", "desc"):
            qualified = f"{{{ns}}}{tag}" if ns else tag
            child = element.find(qualified)
            if child is not None and child.text and child.text.strip():
                desc_parts.append(child.text.strip())
        if desc_parts:
            metadata["description"] = " — ".join(desc_parts)

        if navigation_spec is not None:
            try:
                metadata["navigation"] = navigation_spec.as_dict()
            except Exception:  # pragma: no cover - defensive
                metadata["navigation"] = navigation_spec

        self._apply_filter_metadata(ir_object, element, metadata)

    # ------------------------------------------------------------------ #
    # SVG switch evaluation                                             #
    # ------------------------------------------------------------------ #

    def _convert_switch(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,  # noqa: ARG002 - reserved for future use
        current_navigation,
        traverse_callback,
    ):
        evaluator = SwitchEvaluator(
            system_languages=getattr(self, "_system_languages", ("en",)),
            supported_features=self._SUPPORTED_FEATURES,
        )
        target = evaluator.select_child(element)
        if target is None:
            return []
        return traverse_callback(target, current_navigation)

    def expand_use(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        current_navigation,
        traverse_callback,
    ) -> list:
        href_attr = element.get("{http://www.w3.org/1999/xlink}href") or element.get(
            "href"
        )
        reference_id = self._normalize_href_reference(href_attr)
        if reference_id is None:
            return []

        target = self._symbol_definitions.get(reference_id)
        if target is None:
            target = self._element_index.get(reference_id)
        if target is None:
            return []

        if reference_id in self._use_expansion_stack:
            self._logger.debug(
                "Detected recursive <use> expansion for %s", reference_id
            )
            return []

        self._symbol_usage.add(reference_id)
        target_tag = (
            self._local_name(getattr(target, "tag", ""))
            if isinstance(target, etree._Element)
            else None
        )
        self._trace_stage(
            "symbol_expand",
            stage="symbol",
            subject=reference_id,
            metadata={"target_tag": target_tag},
        )
        self._use_expansion_stack.add(reference_id)
        try:
            nodes = use_expander.instantiate_use_target(self, target, element)
            transform_matrix = use_expander.compose_use_transform(
                self,
                element,
                target,
                tolerance=DEFAULT_TOLERANCE,
            )
            use_expander.apply_use_transform(
                self,
                nodes,
                transform_matrix or Matrix2D.identity(),
                tolerance=DEFAULT_TOLERANCE,
            )
            results: list = []
            for node in nodes:
                results.extend(traverse_callback(node, current_navigation))
            return results
        finally:
            self._use_expansion_stack.discard(reference_id)

    def _prepare_context(self, result) -> None:
        resvg_clip_defs = getattr(self, "_resvg_clip_definitions", {})
        self._clip_definitions = dict(resvg_clip_defs or {})

        resvg_masks = getattr(self, "_resvg_mask_info", {})
        self._mask_info = dict(resvg_masks or {})
        style_context = result.style_context
        if style_context is not None:
            conversion = style_context.conversion
            viewport_width = style_context.viewport_width
            viewport_height = style_context.viewport_height
        else:
            viewport_width = result.width_px or 0.0
            viewport_height = result.height_px or 0.0
            conversion = self._unit_converter.create_context(
                width=viewport_width,
                height=viewport_height,
                font_size=12.0,
                parent_width=viewport_width,
                parent_height=viewport_height,
            )
        self._css_context = CSSStyleContext(
            conversion=conversion,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        self._conversion_context = conversion
        if result.svg_root is not None:
            self._element_index = self._build_element_index(result.svg_root)
        else:
            self._element_index = {}
        self._symbol_definitions = dict(result.symbols or {})
        if self._symbol_definitions:
            self._trace_stage(
                "symbol_definitions",
                stage="symbol",
                metadata={"count": len(self._symbol_definitions)},
            )
        marker_defs = getattr(result, "markers", None)
        if marker_defs:
            self._marker_definitions = dict(marker_defs)
            self._trace_stage(
                "marker_definitions",
                stage="marker",
                metadata={"count": len(marker_defs)},
            )
        else:
            self._marker_definitions = {}
        self._use_expansion_stack.clear()

    @staticmethod
    def _normalize_href_reference(href: str | None) -> str | None:
        return local_url_id(href)

    _local_name = staticmethod(local_name)

    @staticmethod
    def _make_namespaced_tag(reference: etree._Element, local: str) -> str:
        namespace = namespace_uri(reference.tag)
        if namespace:
            return f"{{{namespace}}}{local}"
        return local

    @staticmethod
    def _build_element_index(root: etree._Element) -> dict[str, etree._Element]:
        index: dict[str, etree._Element] = {}
        for node in root.iter():
            node_id = node.get("id")
            if node_id:
                index[node_id] = node
        return index


__all__ = ["TraversalHooksMixin"]
