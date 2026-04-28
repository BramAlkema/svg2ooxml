"""Adapter to convert resvg geometry to DrawingML-compatible IR segments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from svg2ooxml.drawingml.bridges.resvg_shape_geometry import ResvgShapeGeometryMixin
from svg2ooxml.drawingml.bridges.resvg_shape_path import ResvgShapePathMixin
from svg2ooxml.drawingml.bridges.resvg_shape_transform import ResvgShapeTransformMixin
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.usvg_tree import (
        BaseNode,
        CircleNode,
        EllipseNode,
        LineNode,
        PathNode,
        PolyNode,
        RectNode,
    )


class ResvgShapeAdapterError(Exception):
    """Raised when resvg shape adaptation fails."""


class ResvgShapeAdapter(
    ResvgShapeGeometryMixin,
    ResvgShapePathMixin,
    ResvgShapeTransformMixin,
):
    """Convert resvg geometry nodes to DrawingML-compatible IR segments."""

    def from_path_node(self, node: PathNode) -> list[SegmentType]:
        """Convert a resvg PathNode to IR segments."""
        if node.geometry is None:
            raise ResvgShapeAdapterError(
                f"PathNode {node.id or '(unnamed)'} has no geometry"
            )

        segments = self._commands_to_segments(node.geometry)
        return self._apply_node_transform(segments, node)

    def from_rect_node(self, node: RectNode) -> list[SegmentType]:
        """Convert a resvg RectNode to IR segments."""
        x, y, w, h = node.x, node.y, node.width, node.height
        rx, ry = self._normalized_corner_radii(node.rx, node.ry, w, h)

        if w <= 0 or h <= 0:
            return []

        segments: list[SegmentType] = []

        if rx > 0 or ry > 0:
            k = 0.5522847498
            kx = k * rx
            ky = k * ry

            p_start = Point(x + rx, y)

            p_top_right_arc_start = Point(x + w - rx, y)
            segments.append(LineSegment(p_start, p_top_right_arc_start))

            p_right_top = Point(x + w, y + ry)
            segments.append(
                BezierSegment(
                    start=p_top_right_arc_start,
                    control1=Point(x + w - rx + kx, y),
                    control2=Point(x + w, y + ry - ky),
                    end=p_right_top,
                )
            )

            p_right_bottom = Point(x + w, y + h - ry)
            segments.append(LineSegment(p_right_top, p_right_bottom))

            p_bottom_right_arc_end = Point(x + w - rx, y + h)
            segments.append(
                BezierSegment(
                    start=p_right_bottom,
                    control1=Point(x + w, y + h - ry + ky),
                    control2=Point(x + w - rx + kx, y + h),
                    end=p_bottom_right_arc_end,
                )
            )

            p_bottom_left_arc_start = Point(x + rx, y + h)
            segments.append(
                LineSegment(p_bottom_right_arc_end, p_bottom_left_arc_start)
            )

            p_left_bottom = Point(x, y + h - ry)
            segments.append(
                BezierSegment(
                    start=p_bottom_left_arc_start,
                    control1=Point(x + rx - kx, y + h),
                    control2=Point(x, y + h - ry + ky),
                    end=p_left_bottom,
                )
            )

            p_left_top = Point(x, y + ry)
            segments.append(LineSegment(p_left_bottom, p_left_top))

            segments.append(
                BezierSegment(
                    start=p_left_top,
                    control1=Point(x, y + ry - ky),
                    control2=Point(x + rx - kx, y),
                    end=p_start,
                )
            )
        else:
            top_left = Point(x, y)
            top_right = Point(x + w, y)
            bottom_right = Point(x + w, y + h)
            bottom_left = Point(x, y + h)

            segments.append(LineSegment(top_left, top_right))
            segments.append(LineSegment(top_right, bottom_right))
            segments.append(LineSegment(bottom_right, bottom_left))
            segments.append(LineSegment(bottom_left, top_left))

        return self._apply_node_transform(segments, node)

    def from_circle_node(self, node: CircleNode) -> list[SegmentType]:
        """Convert a resvg CircleNode to IR segments."""
        cx, cy, r = node.cx, node.cy, node.r

        if r <= 0:
            return []

        segments = self._ellipse_segments(cx, cy, r, r)
        return self._apply_node_transform(segments, node)

    def from_ellipse_node(self, node: EllipseNode) -> list[SegmentType]:
        """Convert a resvg EllipseNode to IR segments."""
        cx, cy, rx, ry = node.cx, node.cy, node.rx, node.ry

        if rx <= 0 or ry <= 0:
            return []

        segments = self._ellipse_segments(cx, cy, rx, ry)
        return self._apply_node_transform(segments, node)

    def from_line_node(self, node: LineNode) -> list[SegmentType]:
        """Convert a resvg LineNode to IR segments."""
        x1, y1, x2, y2 = node.x1, node.y1, node.x2, node.y2
        if x1 == x2 and y1 == y2:
            return []

        segments = [LineSegment(Point(x1, y1), Point(x2, y2))]
        return self._apply_node_transform(segments, node)

    def from_poly_node(self, node: PolyNode) -> list[SegmentType]:
        """Convert a resvg PolyNode to IR segments."""
        points = self._points_from_flat(node.points)
        if len(points) < 2:
            return []

        segments: list[SegmentType] = []
        for start, end in zip(points, points[1:], strict=False):
            segments.append(LineSegment(start, end))

        if node.tag == "polygon" and not self._points_close(points[0], points[-1]):
            segments.append(LineSegment(points[-1], points[0]))

        return self._apply_node_transform(segments, node)

    def from_node(self, node: BaseNode) -> list[SegmentType]:
        """Convert any supported resvg node to IR segments."""
        from svg2ooxml.core.resvg.usvg_tree import (
            CircleNode,
            EllipseNode,
            LineNode,
            PathNode,
            PolyNode,
            RectNode,
        )

        if isinstance(node, PathNode):
            return self.from_path_node(node)
        if isinstance(node, RectNode):
            return self.from_rect_node(node)
        if isinstance(node, CircleNode):
            return self.from_circle_node(node)
        if isinstance(node, EllipseNode):
            return self.from_ellipse_node(node)
        if isinstance(node, LineNode):
            return self.from_line_node(node)
        if isinstance(node, PolyNode):
            return self.from_poly_node(node)
        raise ResvgShapeAdapterError(
            f"Unsupported node type: {type(node).__name__}. "
            "Only PathNode, RectNode, CircleNode, EllipseNode, LineNode, and "
            "PolyNode are supported."
        )


__all__ = ["ResvgShapeAdapter", "ResvgShapeAdapterError"]
