"""Resvg routing helpers for SVG shape conversion."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.core.ir.shape_converters_utils import _local_name
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace


class ShapeResvgRoutingMixin:
    def _convert_use(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        current_navigation,
        traverse_callback,
    ):
        """Convert <use> elements via resvg only."""
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            text_result = self._try_convert_resvg_use_text(element, coord_space)
            if text_result is not None:
                return text_result
            use_target = self._resolve_use_target(element)
            use_target_tag = (
                _local_name(getattr(use_target, "tag", "")).lower()
                if use_target is not None
                else ""
            )
            if use_target_tag in {"image", "symbol"}:
                expanded_result = self.expand_use(
                    element=element,
                    coord_space=coord_space,
                    current_navigation=current_navigation,
                    traverse_callback=traverse_callback,
                )
                if expanded_result:
                    return expanded_result
            self._trace_resvg_only_miss(element, "resvg_conversion_failed")
            return None
        self._trace_resvg_only_miss(element, self._resvg_miss_reason(element))
        return None

    def _try_convert_resvg_use_text(self, element: etree._Element, coord_space: CoordinateSpace):
        resvg_lookup = getattr(self, "_resvg_element_lookup", {})
        resvg_node = resvg_lookup.get(element) if isinstance(resvg_lookup, dict) else None
        if type(resvg_node).__name__ != "TextNode":
            return None
        text_converter = getattr(self, "_text_converter", None)
        text_convert = getattr(text_converter, "convert", None)
        if not callable(text_convert):
            return None
        try:
            return text_convert(
                element=element,
                coord_space=coord_space,
                resvg_node=resvg_node,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.debug(
                "Resvg text conversion failed for %s: %s",
                element.get("id") or "<use>",
                exc,
            )
            return None

    def _resolve_use_target(self, element: etree._Element) -> etree._Element | None:
        href_attr = element.get("{http://www.w3.org/1999/xlink}href") or element.get("href")
        if not href_attr:
            return None
        reference_id = self._normalize_href_reference(href_attr)
        if reference_id is None:
            return None

        symbol_definitions = getattr(self, "_symbol_definitions", {})
        target = symbol_definitions.get(reference_id) if isinstance(symbol_definitions, dict) else None
        if target is not None:
            return target

        element_index = getattr(self, "_element_index", {})
        if isinstance(element_index, dict):
            target = element_index.get(reference_id)
        return target if isinstance(target, etree._Element) else None

    def _convert_rect(self, *, element: etree._Element, coord_space: CoordinateSpace):
        return self._convert_resvg_shape(element, coord_space, allow_degenerate_fallback=True)

    def _convert_circle(self, *, element: etree._Element, coord_space: CoordinateSpace):
        return self._convert_resvg_shape(element, coord_space, allow_degenerate_fallback=True)

    def _convert_ellipse(self, *, element: etree._Element, coord_space: CoordinateSpace):
        return self._convert_resvg_shape(element, coord_space, allow_degenerate_fallback=True)

    def _convert_line(self, *, element: etree._Element, coord_space: CoordinateSpace):
        return self._convert_resvg_shape(element, coord_space, allow_degenerate_fallback=True)

    def _convert_path(self, *, element: etree._Element, coord_space: CoordinateSpace):
        return self._convert_resvg_shape(element, coord_space, allow_degenerate_fallback=False)

    def _convert_polygon(self, *, element: etree._Element, coord_space: CoordinateSpace):
        return self._convert_resvg_shape(element, coord_space, allow_degenerate_fallback=False)

    def _convert_polyline(self, *, element: etree._Element, coord_space: CoordinateSpace):
        return self._convert_resvg_shape(element, coord_space, allow_degenerate_fallback=False)

    def _convert_resvg_shape(
        self,
        element: etree._Element,
        coord_space: CoordinateSpace,
        *,
        allow_degenerate_fallback: bool,
    ):
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            if allow_degenerate_fallback:
                fallback = self._convert_degenerate_shape_fallback(
                    element=element,
                    coord_space=coord_space,
                )
                if fallback is not None:
                    return fallback
            self._trace_resvg_only_miss(element, "resvg_conversion_failed")
            return None
        self._trace_resvg_only_miss(element, self._resvg_miss_reason(element))
        return None


__all__ = ["ShapeResvgRoutingMixin"]
