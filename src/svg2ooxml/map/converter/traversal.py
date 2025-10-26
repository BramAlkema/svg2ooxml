"""DOM traversal for IR conversion."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Optional

from lxml import etree

from svg2ooxml.parser.xml import children
from svg2ooxml.pipeline.navigation import NavigationSpec, parse_svg_navigation

from .coordinate_space import CoordinateSpace
from .transform_parser import TransformParser
from . import traversal_runtime


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

    def extract(self, svg_root: etree._Element) -> list:
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

            if tag == "defs":
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
        if not tag:
            return ""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag


__all__ = ["ElementTraversal", "TraverseCallback"]


def navigation_from_attributes(element: etree._Element) -> Optional[NavigationSpec]:
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
