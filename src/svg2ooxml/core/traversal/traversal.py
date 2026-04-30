"""DOM traversal for IR conversion."""



from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from lxml import etree

from svg2ooxml.common.math_utils import finite_float
from svg2ooxml.common.svg_refs import local_name as svg_local_name
from svg2ooxml.core.parser.xml_utils import children
from svg2ooxml.core.pipeline.navigation import NavigationSpec, parse_svg_navigation
from svg2ooxml.core.traversal import runtime as traversal_runtime
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.core.traversal.transform_parser import TransformParser
from svg2ooxml.core.traversal.viewbox import viewbox_matrix_from_element

TraverseCallback = Callable[[etree._Element, Any | None], list]


class ElementTraversal:
    """Traverse the SVG DOM and delegate element conversion."""

    def __init__(
        self,
        ir_converter,
        hyperlink_processor,
        logger,
        child_iter: Callable[[etree._Element], Iterable[etree._Element]] | None = None,
        transform_parser: TransformParser | None = None,
        normalized_lookup: dict[int, Any] | None = None,
    ) -> None:
        self._converter = ir_converter
        self._hyperlinks = hyperlink_processor
        self._logger = logger
        self._children = child_iter or children
        self._transform_parser = transform_parser or TransformParser()
        self._coord_space = CoordinateSpace()
        self._normalized_lookup = normalized_lookup or {}
        self._root_element: etree._Element | None = None

    def extract(self, svg_root: etree._Element) -> list:
        self._root_element = svg_root
        viewbox_matrix = None
        if svg_root is not None:
            converter = self._converter
            unit_converter = getattr(converter, "_unit_converter", None)
            if unit_converter is not None:
                default_width = 800.0
                default_height = 600.0
                conversion_context = getattr(converter, "_conversion_context", None)
                if conversion_context is not None:
                    width_value = getattr(conversion_context, "width", None)
                    height_value = getattr(conversion_context, "height", None)
                    default_width = finite_float(width_value, default_width) or default_width
                    default_height = finite_float(height_value, default_height) or default_height
                viewbox_matrix, _ = viewbox_matrix_from_element(
                    svg_root,
                    unit_converter,
                    default_width=default_width,
                    default_height=default_height,
                )

        if viewbox_matrix is not None and not viewbox_matrix.is_identity():
            self._coord_space.push(viewbox_matrix)
            try:
                return self._extract_recursive(svg_root, current_navigation=None)
            finally:
                self._coord_space.pop()

        return self._extract_recursive(svg_root, current_navigation=None)

    def navigation_from_attributes(self, element: etree._Element):
        return navigation_from_attributes(element)

    def _extract_recursive(self, element: etree._Element, current_navigation) -> list:
        ir_elements: list = []
        pushed = traversal_runtime.push_element_transform(self, element)

        try:
            tag = traversal_runtime.local_name(getattr(element, "tag", None))
            if tag == "a":
                return traversal_runtime.process_anchor(self, element, current_navigation, self._extract_recursive)

            active_navigation = traversal_runtime.resolve_active_navigation(self, element, current_navigation)

            if tag == "g":
                return traversal_runtime.process_group(self, element, active_navigation, self._extract_recursive)

            if tag in {"defs", "symbol"}:
                return ir_elements

            if tag == "use":
                return traversal_runtime.process_use(self, element, active_navigation, self._extract_recursive)

            return traversal_runtime.process_generic(self, tag, element, active_navigation, self._extract_recursive)
        finally:
            if pushed:
                try:
                    self._coord_space.pop()
                except Exception as exc:  # pragma: no cover - defensive
                    self._logger.warning("Failed to pop transform: %s", exc)

    @staticmethod
    def _local_name(tag: str | None) -> str:
        return svg_local_name(tag)


__all__ = ["ElementTraversal", "TraverseCallback"]


def navigation_from_attributes(element: etree._Element) -> NavigationSpec | None:
    """Inspect data-* attributes on non-anchor elements to infer navigation."""

    attrs: dict[str, str] = {}
    for name in ("data-slide", "data-jump", "data-bookmark", "data-custom-show", "data-visited"):
        value = element.get(name)
        if value is not None:
            attrs[name] = value
    if not attrs:
        return None
    tooltip = element.get("title")
    try:
        return parse_svg_navigation(None, attrs, tooltip)
    except Exception:
        return None
