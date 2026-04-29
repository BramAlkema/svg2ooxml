"""Gradient descriptor materialization and DrawingML conversion helpers."""

from __future__ import annotations

import logging
import math
from collections.abc import Iterator
from dataclasses import replace

from lxml import etree

from svg2ooxml.color.adapters import color_object_to_hex
from svg2ooxml.color.models import Color
from svg2ooxml.color.parsers import parse_color
from svg2ooxml.common.conversions.angles import degrees_to_ppt
from svg2ooxml.common.conversions.opacity import opacity_to_ppt, parse_opacity
from svg2ooxml.common.conversions.scale import position_to_ppt
from svg2ooxml.common.gradient_units import (
    parse_gradient_coordinate,
    parse_gradient_offset,
)
from svg2ooxml.common.style.css_values import parse_style_declarations
from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.drawingml.bridges.resvg_paint_bridge import (
    GradientDescriptor,
    LinearGradientDescriptor,
    MeshGradientDescriptor,
    RadialGradientDescriptor,
    build_linear_gradient_element,
    build_mesh_gradient_element,
    build_radial_gradient_element,
    describe_gradient_element,
)
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.services.gradient_processor import GradientAnalysis

logger = logging.getLogger(__name__)


class GradientServiceConversionMixin:
    """Convert registered SVG gradients into DrawingML fragments."""

    def _simplify_stops(
        self,
        stops: list[tuple[int, Color]],
        target: int,
    ) -> list[tuple[int, Color]]:
        if target < 2 or len(stops) <= target:
            return stops
        stride = (len(stops) - 1) / (target - 1)
        simplified: list[tuple[int, Color]] = []
        for index in range(target):
            source = int(round(index * stride))
            simplified.append(stops[min(source, len(stops) - 1)])
        return simplified

    def _serialise_stop(self, position: int, color: Color) -> etree._Element:
        srgb = self._color_to_hex(color)
        gs = a_elem("gs", pos=position)
        srgbClr = a_sub(gs, "srgbClr", val=srgb)
        if color.a < 0.999:
            a_sub(srgbClr, "alpha", val=opacity_to_ppt(color.a))
        return gs

    def _color_to_hex(self, color: Color) -> str:
        return color_object_to_hex(color, scale="unit") or "000000"

    def _analysis_comment(self, analysis: GradientAnalysis | None) -> str:
        if analysis is None:
            return ""
        notes = ",".join(analysis.plan.notes) if analysis.plan.notes else ""
        return (
            f"<!-- svg2ooxml:gradient complexity={analysis.complexity.value}"
            f" stops={analysis.metrics.stop_count}"
            f" notes=\"{notes}\" -->"
        )

    def _coerce_descriptor(
        self,
        gradient_id: str,
        definition: GradientDescriptor | etree._Element,
    ) -> GradientDescriptor | None:
        descriptor: GradientDescriptor
        if isinstance(definition, (LinearGradientDescriptor, RadialGradientDescriptor, MeshGradientDescriptor)):
            descriptor = definition
        elif isinstance(definition, etree._Element):
            try:
                descriptor = describe_gradient_element(definition)
            except Exception:  # pragma: no cover - defensive
                logger.debug("Failed to convert gradient %s to descriptor", gradient_id, exc_info=True)
                return None
        else:
            logger.debug("Unsupported gradient definition type for %s: %r", gradient_id, type(definition))
            return None

        if descriptor.gradient_id in (None, ""):
            descriptor = replace(descriptor, gradient_id=gradient_id)
        return descriptor

    def _materialize_gradient(
        self,
        gradient_id: str,
        descriptor: GradientDescriptor,
    ) -> etree._Element:
        cached = self._materialized_elements.get(gradient_id)
        if cached is not None:
            return cached

        if isinstance(descriptor, LinearGradientDescriptor):
            element = build_linear_gradient_element(descriptor)
        elif isinstance(descriptor, RadialGradientDescriptor):
            element = build_radial_gradient_element(descriptor)
        elif isinstance(descriptor, MeshGradientDescriptor):
            element = build_mesh_gradient_element(descriptor)
        else:  # pragma: no cover - defensive
            raise TypeError(f"Unsupported gradient descriptor type: {type(descriptor)!r}")

        self._materialized_elements[gradient_id] = element
        return element

    def as_element(self, descriptor: GradientDescriptor) -> etree._Element:
        key = descriptor.gradient_id or "__anon__"
        return self._materialize_gradient(key, descriptor)

    def _convert_linear_gradient(
        self,
        element: etree._Element,
        analysis: GradientAnalysis | None,
    ) -> str:
        plan = analysis.plan if analysis else None
        max_stops = plan.simplify_to if plan and plan.simplify_to else None
        gs_list = self._extract_gradient_stops(element, max_stops=max_stops)
        angle = self._resolve_linear_angle(element)
        comment = self._analysis_comment(analysis)

        gradFill = a_elem("gradFill")
        gsLst = a_sub(gradFill, "gsLst")
        for gs_elem in gs_list:
            gsLst.append(gs_elem)
        a_sub(gradFill, "lin", ang=angle, scaled="0")

        result = to_string(gradFill)
        return f"{comment}{result}" if comment else result

    def _convert_radial_gradient(
        self,
        element: etree._Element,
        analysis: GradientAnalysis | None,
    ) -> str:
        plan = analysis.plan if analysis else None
        max_stops = plan.simplify_to if plan and plan.simplify_to else None
        gs_list = self._extract_gradient_stops(element, max_stops=max_stops)
        comment = self._analysis_comment(analysis)

        gradFill = a_elem("gradFill")
        gsLst = a_sub(gradFill, "gsLst")
        for gs_elem in gs_list:
            gsLst.append(gs_elem)
        a_sub(gradFill, "path", path="circle")

        result = to_string(gradFill)
        return f"{comment}{result}" if comment else result

    def _convert_mesh_gradient(
        self,
        element: etree._Element,
        analysis: GradientAnalysis | None,
    ) -> str:
        # Mesh gradients require dedicated tessellation; surface a hint so the caller can choose a fallback.
        rows, cols = self._analyze_mesh(element)
        comment = self._analysis_comment(analysis)
        return (
            f"{comment}"
            "<!-- svg2ooxml:mesh gradient -->"
            f"<!-- rows={rows} cols={cols} -->"
        )

    def _extract_gradient_stops(
        self,
        element: etree._Element,
        *,
        max_stops: int | None = None,
    ) -> list[etree._Element]:
        stops = []
        for stop in self._iter_stops(element):
            pos = self._parse_offset(stop.get("offset"))
            color = self._resolve_stop_color(stop)
            stops.append((pos, color))

        if not stops:
            stops = [
                (0, Color(0.0, 0.0, 0.0, 1.0)),
                (100000, Color(1.0, 1.0, 1.0, 1.0)),
            ]

        if max_stops is not None and max_stops >= 2 and len(stops) > max_stops:
            stops = self._simplify_stops(stops, max_stops)

        return [self._serialise_stop(pos, color) for pos, color in stops]

    # ------------------------------------------------------------------ #
    # Support functions                                                  #
    # ------------------------------------------------------------------ #

    def _iter_stops(self, element: etree._Element) -> Iterator[etree._Element]:
        for node in element.iter():
            if not hasattr(node, "tag"):
                continue
            if local_name(getattr(node, "tag", "")) == "stop":
                yield node

    def _parse_offset(self, value: str | None) -> int:
        return position_to_ppt(parse_gradient_offset(value))

    def _resolve_stop_color(self, stop: etree._Element) -> Color:
        style_map = self._parse_style(stop.get("style"))
        color_value = style_map.get("stop-color", stop.get("stop-color"))
        opacity_value = style_map.get("stop-opacity", stop.get("stop-opacity"))

        color = parse_color(color_value) or Color(0.0, 0.0, 0.0, 1.0)
        if opacity_value is not None:
            color = color.with_alpha(color.a * parse_opacity(opacity_value, default=1.0))
        return color

    def _parse_style(self, payload: str | None) -> dict[str, str]:
        return parse_style_declarations(payload)[0]

    def _resolve_linear_angle(self, element: etree._Element) -> int:
        # Map SVG x1/y1/x2/y2 into DrawingML degrees; fall back to 180° (top-to-bottom)
        try:
            units = element.get("gradientUnits")
            x1 = parse_gradient_coordinate(
                element.get("x1"),
                units=units,
                axis="x",
                default="0",
            )
            y1 = parse_gradient_coordinate(
                element.get("y1"),
                units=units,
                axis="y",
                default="0",
            )
            x2 = parse_gradient_coordinate(
                element.get("x2"),
                units=units,
                axis="x",
                default="0",
            )
            y2 = parse_gradient_coordinate(
                element.get("y2"),
                units=units,
                axis="y",
                default="1",
            )
            dx = x2 - x1
            dy = y2 - y1
            if dx == 0 and dy == 0:
                return 180000
            angle = math.degrees(math.atan2(dy, dx))
            rotated = (90 - angle) % 360
            return degrees_to_ppt(rotated)
        except Exception:  # pragma: no cover - defensive
            return 180000

    def _analyze_mesh(self, element: etree._Element) -> tuple[int, int]:
        rows = 0
        cols = 0
        for patch in element.findall(".//*[local-name()='meshrow']"):
            rows += 1
            cols = max(cols, len(list(patch)))
        return rows or 1, cols or 1


__all__ = ["GradientServiceConversionMixin"]
