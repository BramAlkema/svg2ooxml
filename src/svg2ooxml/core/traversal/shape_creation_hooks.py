"""Shape descriptor and serialization hooks for the IR converter."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, SegmentType
from svg2ooxml.ir.geometry import Rect as IRRect
from svg2ooxml.ir.paint import (
    GradientPaintRef,
    LinearGradientPaint,
    PatternPaint,
    RadialGradientPaint,
    SolidPaint,
    Stroke,
)
from svg2ooxml.ir.scene import Group as IRGroup
from svg2ooxml.ir.scene import Path as IRShapePath
from svg2ooxml.ir.shapes import (
    Circle as IRShapeCircle,
)
from svg2ooxml.ir.shapes import (
    Ellipse as IRShapeEllipse,
)
from svg2ooxml.ir.shapes import (
    Line as IRShapeLine,
)
from svg2ooxml.ir.shapes import (
    Polygon as IRShapePolygon,
)
from svg2ooxml.ir.shapes import (
    Polyline as IRShapePolyline,
)
from svg2ooxml.ir.shapes import (
    Rectangle as IRShapeRectangle,
)


class ShapeCreationMixin:
    """Mixin providing shape descriptor and paint serialization methods."""

    def _shape_descriptor(self, ir_object: Any) -> dict[str, Any] | None:
        if isinstance(ir_object, list):
            if not ir_object:
                return None
            return self._group_descriptor(IRGroup(children=ir_object))

        if isinstance(ir_object, IRGroup):
            return self._group_descriptor(ir_object)
        if isinstance(ir_object, IRShapePath):
            return self._path_descriptor(ir_object)
        if isinstance(ir_object, IRShapeRectangle):
            return self._rectangle_descriptor(ir_object)
        if isinstance(ir_object, IRShapeCircle):
            return self._circle_descriptor(ir_object)
        if isinstance(ir_object, IRShapeEllipse):
            return self._ellipse_descriptor(ir_object)
        if isinstance(ir_object, IRShapePolygon):
            return self._polygon_descriptor(ir_object)
        if isinstance(ir_object, IRShapePolyline):
            return self._polyline_descriptor(ir_object)
        if isinstance(ir_object, IRShapeLine):
            return self._line_descriptor(ir_object)
        return None

    def _group_descriptor(self, group: IRGroup) -> dict[str, Any] | None:
        children = [
            descriptor
            for child in group.children
            if (descriptor := self._shape_descriptor(child)) is not None
        ]
        if not children:
            return None
        return {
            "shape_type": "Group",
            "children": children,
            "opacity": getattr(group, "opacity", 1.0),
            "transform": self._serialize_matrix(getattr(group, "transform", None)),
            "bbox": self._serialize_rect(group.bbox),
        }

    def _path_descriptor(self, path: IRShapePath) -> dict[str, Any]:
        return {
            "shape_type": "Path",
            "geometry": self._serialize_segments(path.segments),
            "closed": path.is_closed,
            "fill": self._serialize_paint(path.fill),
            "stroke": self._serialize_stroke(path.stroke),
            "opacity": getattr(path, "opacity", 1.0),
            "transform": self._serialize_matrix(getattr(path, "transform", None)),
            "bbox": self._serialize_rect(path.bbox),
        }

    def _rectangle_descriptor(self, rect: IRShapeRectangle) -> dict[str, Any]:
        if rect.is_rounded:
            segments = _rounded_rect_segments(
                rect.bounds.x,
                rect.bounds.y,
                rect.bounds.width,
                rect.bounds.height,
                rect.corner_radius,
                rect.corner_radius,
            )
        else:
            segments = _rect_segments(
                rect.bounds.x, rect.bounds.y, rect.bounds.width, rect.bounds.height
            )
        return {
            "shape_type": "Rectangle",
            "geometry": self._serialize_segments(segments),
            "closed": True,
            "bounds": self._serialize_rect(rect.bounds),
            "corner_radius": rect.corner_radius,
            "fill": self._serialize_paint(rect.fill),
            "stroke": self._serialize_stroke(rect.stroke),
            "opacity": getattr(rect, "opacity", 1.0),
            "transform": None,
            "bbox": self._serialize_rect(rect.bbox),
        }

    def _circle_descriptor(self, circle: IRShapeCircle) -> dict[str, Any]:
        segments = _ellipse_segments(
            circle.center.x, circle.center.y, circle.radius, circle.radius
        )
        return {
            "shape_type": "Circle",
            "geometry": self._serialize_segments(segments),
            "closed": True,
            "center": self._point_tuple(circle.center),
            "radius": circle.radius,
            "fill": self._serialize_paint(circle.fill),
            "stroke": self._serialize_stroke(circle.stroke),
            "opacity": getattr(circle, "opacity", 1.0),
            "transform": None,
            "bbox": self._serialize_rect(circle.bbox),
        }

    def _ellipse_descriptor(self, ellipse: IRShapeEllipse) -> dict[str, Any]:
        segments = _ellipse_segments(
            ellipse.center.x, ellipse.center.y, ellipse.radius_x, ellipse.radius_y
        )
        return {
            "shape_type": "Ellipse",
            "geometry": self._serialize_segments(segments),
            "closed": True,
            "center": self._point_tuple(ellipse.center),
            "radius_x": ellipse.radius_x,
            "radius_y": ellipse.radius_y,
            "fill": self._serialize_paint(ellipse.fill),
            "stroke": self._serialize_stroke(ellipse.stroke),
            "opacity": getattr(ellipse, "opacity", 1.0),
            "transform": None,
            "bbox": self._serialize_rect(ellipse.bbox),
        }

    def _polygon_descriptor(self, polygon: IRShapePolygon) -> dict[str, Any]:
        segments = _points_to_segments(polygon.points, closed=True)
        return {
            "shape_type": "Polygon",
            "geometry": self._serialize_segments(segments),
            "closed": True,
            "points": [self._point_tuple(pt) for pt in polygon.points],
            "fill": self._serialize_paint(polygon.fill),
            "stroke": self._serialize_stroke(polygon.stroke),
            "opacity": getattr(polygon, "opacity", 1.0),
            "transform": None,
            "bbox": self._serialize_rect(polygon.bbox),
        }

    def _polyline_descriptor(self, polyline: IRShapePolyline) -> dict[str, Any]:
        segments = _points_to_segments(polyline.points, closed=False)
        return {
            "shape_type": "Polyline",
            "geometry": self._serialize_segments(segments),
            "closed": False,
            "points": [self._point_tuple(pt) for pt in polyline.points],
            "fill": self._serialize_paint(polyline.fill),
            "stroke": self._serialize_stroke(polyline.stroke),
            "opacity": getattr(polyline, "opacity", 1.0),
            "transform": None,
            "bbox": self._serialize_rect(polyline.bbox),
        }

    def _line_descriptor(self, line: IRShapeLine) -> dict[str, Any]:
        segment = LineSegment(line.start, line.end)
        return {
            "shape_type": "Line",
            "geometry": self._serialize_segments([segment]),
            "closed": False,
            "points": [self._point_tuple(line.start), self._point_tuple(line.end)],
            "stroke": self._serialize_stroke(line.stroke),
            "opacity": getattr(line, "opacity", 1.0),
            "transform": None,
            "bbox": self._serialize_rect(line.bbox),
        }

    def _serialize_segments(
        self, segments: Iterable[SegmentType]
    ) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for segment in segments:
            if isinstance(segment, LineSegment):
                serialized.append(
                    {
                        "type": "line",
                        "start": self._point_tuple(segment.start),
                        "end": self._point_tuple(segment.end),
                    }
                )
            elif isinstance(segment, BezierSegment):
                serialized.append(
                    {
                        "type": "cubic",
                        "start": self._point_tuple(segment.start),
                        "control1": self._point_tuple(segment.control1),
                        "control2": self._point_tuple(segment.control2),
                        "end": self._point_tuple(segment.end),
                    }
                )
        return serialized

    @staticmethod
    def _point_tuple(point: Any | None) -> tuple[float, float] | None:
        if point is None:
            return None
        return (float(point.x), float(point.y))

    @staticmethod
    def _serialize_rect(rect: IRRect | None) -> dict[str, float] | None:
        if rect is None:
            return None
        return {
            "x": float(rect.x),
            "y": float(rect.y),
            "width": float(rect.width),
            "height": float(rect.height),
        }

    def _serialize_paint(self, paint: Any) -> dict[str, Any] | None:
        if paint is None:
            return None
        if isinstance(paint, SolidPaint):
            return {"type": "solid", "rgb": paint.rgb, "opacity": paint.opacity}
        if isinstance(paint, LinearGradientPaint):
            return {
                "type": "linearGradient",
                "stops": [
                    {"offset": stop.offset, "rgb": stop.rgb, "opacity": stop.opacity}
                    for stop in paint.stops
                ],
                "start": tuple(paint.start),
                "end": tuple(paint.end),
                "transform": self._serialize_matrix(paint.transform),
                "gradient_id": paint.gradient_id,
                "gradient_units": paint.gradient_units,
                "spread_method": paint.spread_method,
            }
        if isinstance(paint, RadialGradientPaint):
            result = {
                "type": "radialGradient",
                "stops": [
                    {"offset": stop.offset, "rgb": stop.rgb, "opacity": stop.opacity}
                    for stop in paint.stops
                ],
                "center": tuple(paint.center),
                "radius": float(paint.radius),
                "focal_point": tuple(paint.focal_point) if paint.focal_point else None,
                "focal_radius": paint.focal_radius,
                "transform": self._serialize_matrix(paint.transform),
                "gradient_id": paint.gradient_id,
                "gradient_units": paint.gradient_units,
                "spread_method": paint.spread_method,
            }

            # Phase 1: Include transform telemetry fields if present
            if hasattr(paint, "had_transform_flag") and paint.had_transform_flag:
                result["had_transform"] = True
                result["gradient_transform"] = self._serialize_matrix(
                    paint.gradient_transform
                )

                if paint.policy_decision:
                    result["policy_decision"] = paint.policy_decision

                if paint.transform_class:
                    result["transform_class"] = {
                        "non_uniform": paint.transform_class.non_uniform,
                        "has_shear": paint.transform_class.has_shear,
                        "det_sign": paint.transform_class.det_sign,
                        "s1": float(paint.transform_class.s1),
                        "s2": float(paint.transform_class.s2),
                        "ratio": float(paint.transform_class.ratio),
                    }

            return result
        if isinstance(paint, PatternPaint):
            return {
                "type": "pattern",
                "pattern_id": paint.pattern_id,
                "transform": self._serialize_matrix(paint.transform),
                "preset": paint.preset,
                "foreground": paint.foreground,
                "background": paint.background,
            }
        if isinstance(paint, GradientPaintRef):
            return {
                "type": "gradientRef",
                "gradient_id": paint.gradient_id,
                "gradient_type": paint.gradient_type,
                "transform": self._serialize_matrix(paint.transform),
            }
        return {"type": type(paint).__name__}

    def _serialize_stroke(self, stroke: Stroke | None) -> dict[str, Any] | None:
        if stroke is None:
            return None
        return {
            "width": stroke.width,
            "paint": self._serialize_paint(stroke.paint),
            "join": stroke.join.value,
            "cap": stroke.cap.value,
            "miter_limit": stroke.miter_limit,
            "dash_array": list(stroke.dash_array) if stroke.dash_array else None,
            "dash_offset": stroke.dash_offset,
            "opacity": stroke.opacity,
        }

    @staticmethod
    def _serialize_matrix(matrix: Any) -> list[list[float]] | None:
        if matrix is None:
            return None
        if hasattr(matrix, "tolist"):
            return matrix.tolist()
        return None


def _ellipse_segments(cx: float, cy: float, rx: float, ry: float):
    from svg2ooxml.core.ir.shape_converters import _ellipse_segments as _impl

    globals()["_ellipse_segments"] = _impl
    return _impl(cx, cy, rx, ry)


def _points_to_segments(points, *, closed: bool):
    from svg2ooxml.core.ir.shape_converters import _points_to_segments as _impl

    globals()["_points_to_segments"] = _impl
    return _impl(points, closed=closed)


def _rect_segments(x: float, y: float, width: float, height: float):
    from svg2ooxml.core.ir.rectangles import _rect_segments as _impl

    globals()["_rect_segments"] = _impl
    return _impl(x, y, width, height)


def _rounded_rect_segments(
    x: float,
    y: float,
    width: float,
    height: float,
    radius_x: float,
    radius_y: float,
):
    from svg2ooxml.core.ir.rectangles import _rounded_rect_segments as _impl

    globals()["_rounded_rect_segments"] = _impl
    return _impl(x, y, width, height, radius_x, radius_y)
