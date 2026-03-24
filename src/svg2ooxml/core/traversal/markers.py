"""Marker definition helpers shared by the IR converter."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D, parse_transform_list
from svg2ooxml.core.traversal.viewbox import (
    ViewBox,
    ViewportEngine,
    parse_viewbox_attribute,
)
from svg2ooxml.ir.geometry import Point


@dataclass(slots=True)
class MarkerDefinition:
    """Normalized representation of an SVG ``<marker>`` element."""

    marker_id: str
    element: etree._Element
    ref_x: float
    ref_y: float
    marker_width: float
    marker_height: float
    orient: str
    marker_units: str
    overflow: str
    viewbox: ViewBox | None
    preserve_aspect_ratio: str | None

    def clone(self) -> MarkerDefinition:
        # ``element`` is shared intentionally to avoid deep copies of the DOM.
        return MarkerDefinition(
            marker_id=self.marker_id,
            element=self.element,
            ref_x=self.ref_x,
            ref_y=self.ref_y,
            marker_width=self.marker_width,
            marker_height=self.marker_height,
            orient=self.orient,
            marker_units=self.marker_units,
            overflow=self.overflow,
            viewbox=self.viewbox,
            preserve_aspect_ratio=self.preserve_aspect_ratio,
        )


@dataclass(slots=True)
class MarkerInstance:
    """Placement metadata for a marker applied to a path."""

    definition: MarkerDefinition
    position: str  # start | mid | end
    anchor: Point
    angle: float
    stroke_width: float

    def clone(self) -> MarkerInstance:
        return MarkerInstance(
            definition=self.definition.clone(),
            position=self.position,
            anchor=Point(self.anchor.x, self.anchor.y),
            angle=self.angle,
            stroke_width=self.stroke_width,
        )


@dataclass(slots=True)
class MarkerTransform:
    matrix: Matrix2D
    clip_rect: tuple[float, float, float, float] | None

    def clone(self) -> MarkerTransform:
        clip = None if self.clip_rect is None else tuple(self.clip_rect)
        return MarkerTransform(
            matrix=Matrix2D(
                self.matrix.a,
                self.matrix.b,
                self.matrix.c,
                self.matrix.d,
                self.matrix.e,
                self.matrix.f,
            ),
            clip_rect=clip,
        )


def parse_marker_definition(element: etree._Element) -> MarkerDefinition:
    """Parse a ``<marker>`` element into a ``MarkerDefinition`` record."""

    marker_id = element.get("id")
    if not marker_id:
        raise ValueError("marker element is missing an id attribute")

    def _parse_numeric(value: str | None, default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    ref_x = _parse_numeric(element.get("refX"), 0.0)
    ref_y = _parse_numeric(element.get("refY"), 0.0)
    marker_width = max(_parse_numeric(element.get("markerWidth"), 3.0), 0.0)
    marker_height = max(_parse_numeric(element.get("markerHeight"), 3.0), 0.0)
    orient = (element.get("orient") or "auto").strip()
    marker_units = (element.get("markerUnits") or "strokeWidth").strip()
    overflow = (element.get("overflow") or element.get("style", "")).strip()
    if overflow not in {"visible", "hidden", "auto"}:
        overflow = "visible" if "overflow:visible" in overflow else "hidden"

    viewbox = parse_viewbox_attribute(element.get("viewBox"))
    preserve_aspect_ratio = element.get("preserveAspectRatio")

    return MarkerDefinition(
        marker_id=marker_id,
        element=element,
        ref_x=ref_x,
        ref_y=ref_y,
        marker_width=marker_width,
        marker_height=marker_height,
        orient=orient,
        marker_units=marker_units or "strokeWidth",
        overflow=overflow,
        viewbox=viewbox,
        preserve_aspect_ratio=preserve_aspect_ratio,
    )


def build_marker_transform(
    *,
    definition: MarkerDefinition,
    anchor: Point,
    angle: float,
    stroke_width: float,
    position: str,
) -> MarkerTransform:
    """Return the composed matrix that positions the marker geometry."""

    matrix = Matrix2D.identity()
    clip_rect: tuple[float, float, float, float] | None = None

    size_x = definition.marker_width
    size_y = definition.marker_height
    if definition.marker_units.lower() == "strokewidth":
        size_x *= stroke_width
        size_y *= stroke_width

    viewport_width = max(size_x, 1e-9)
    viewport_height = max(size_y, 1e-9)

    if (
        definition.viewbox is not None
        and definition.viewbox.width > 0.0
        and definition.viewbox.height > 0.0
    ):
        engine = ViewportEngine()
        result = engine.compute(
            (
                definition.viewbox.min_x,
                definition.viewbox.min_y,
                definition.viewbox.width,
                definition.viewbox.height,
            ),
            (viewport_width, viewport_height),
            definition.preserve_aspect_ratio,
        )
        viewport_matrix = Matrix2D(
            result.scale_x,
            0.0,
            0.0,
            result.scale_y,
            result.translate_x,
            result.translate_y,
        )
        matrix = matrix.multiply(viewport_matrix)
        clip_rect = (0.0, 0.0, result.clip_width, result.clip_height)
    else:
        base_width = definition.marker_width if definition.marker_width else 1.0
        base_height = definition.marker_height if definition.marker_height else 1.0
        scale_x = viewport_width / base_width if base_width else 1.0
        scale_y = viewport_height / base_height if base_height else 1.0
        matrix = matrix.multiply(_matrix_scale(scale_x, scale_y))
        clip_rect = (0.0, 0.0, viewport_width, viewport_height)

    orient = definition.orient.lower()
    orient_angle = angle
    if orient == "auto-start-reverse":
        if position == "start":
            orient_angle = (angle + 180.0) % 360.0
    elif orient not in {"auto"}:
        try:
            orient_angle = float(definition.orient)
        except ValueError:
            orient_angle = angle

    # SVG marker transform order: translate(anchor) * rotate * scale * translate(-ref)
    # `matrix` already holds the scale/viewport part from above.
    # Prepend translate(-ref), then prepend rotate, then prepend translate(anchor).
    scale_matrix = matrix
    matrix = _matrix_translate(anchor.x, anchor.y)
    matrix = matrix.multiply(_matrix_rotate(orient_angle))
    matrix = matrix.multiply(scale_matrix)
    matrix = matrix.multiply(_matrix_translate(-definition.ref_x, -definition.ref_y))
    return MarkerTransform(matrix=matrix, clip_rect=clip_rect)


def apply_local_transform(matrix: Matrix2D, transform_attr: str | None) -> Matrix2D:
    """Compose *transform_attr* with the provided matrix if present."""
    if not transform_attr:
        return matrix
    local = parse_transform_list(transform_attr)
    return matrix.multiply(local)


def _matrix_translate(x: float, y: float) -> Matrix2D:
    return Matrix2D(1.0, 0.0, 0.0, 1.0, x, y)


def _matrix_scale(x: float, y: float) -> Matrix2D:
    return Matrix2D(x, 0.0, 0.0, y, 0.0, 0.0)


def _matrix_rotate(degrees: float) -> Matrix2D:
    from math import cos, radians, sin

    angle = radians(degrees)
    cos_a = cos(angle)
    sin_a = sin(angle)
    return Matrix2D(cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)


def flatten_points(points: Iterable[Point]) -> list[tuple[float, float]]:
    """Convert sequence of Points to tuples for convenience."""
    return [(point.x, point.y) for point in points]


__all__ = [
    "MarkerDefinition",
    "MarkerInstance",
    "MarkerTransform",
    "apply_local_transform",
    "build_marker_transform",
    "flatten_points",
    "parse_marker_definition",
]
