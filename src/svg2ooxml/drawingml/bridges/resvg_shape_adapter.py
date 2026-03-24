"""Adapter to convert resvg geometry to DrawingML-compatible IR segments.

This module bridges resvg's internal path representation (NormalizedPath with path
primitives like MoveTo, LineTo, CubicCurve) to the IR segment types (Point, LineSegment,
BezierSegment) expected by DrawingMLPathGenerator.

✅ **Transform Application**: Transform matrices ARE now applied to output segments!
Each resvg node carries a `transform` field (Matrix), and this adapter applies it to all
segment coordinates before returning them. The transform is baked into the coordinates,
so the DrawingML generator doesn't need to handle transforms separately.

Usage:
    adapter = ResvgShapeAdapter()

    # From resvg PathNode
    segments = adapter.from_path_node(path_node)  # Transforms applied automatically

    # From resvg shape nodes (rect/circle/ellipse)
    segments = adapter.from_rect_node(rect_node)    # Transforms applied automatically
    segments = adapter.from_circle_node(circle_node)
    segments = adapter.from_ellipse_node(ellipse_node)

    # Generate DrawingML
    generator = DrawingMLPathGenerator()
    geometry = generator.generate_custom_geometry(
        segments,
        fill_mode="norm",
        stroke_mode="norm",
        closed=True,
    )

Note: Fill and stroke properties are also not extracted here. Use resvg_paint_bridge.py
for paint server conversion (gradients, patterns, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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


class ResvgShapeAdapter:
    """Convert resvg geometry nodes to DrawingML-compatible IR segments.

    ✅ **Transform Application**: This adapter DOES apply node transforms! All shapes are
    converted with their transforms baked into the segment coordinates. The transform
    matrix is applied to all points before returning segments to the caller.

    Supported node types:
    - PathNode: Converts NormalizedPath primitives to IR segments
    - RectNode: Handles simple and rounded rectangles with Bezier arcs
    - CircleNode: Approximates with 4 cubic Bezier curves
    - EllipseNode: Approximates with 4 cubic Bezier curves
    - LineNode: Converts to a single line segment
    - PolyNode: Converts polyline/polygon points to line segments
    """

    def from_path_node(self, node: PathNode) -> list[SegmentType]:
        """Convert a resvg PathNode to IR segments.

        Preserves cubic bezier curves as BezierSegments instead of flattening
        them to line segments.  Quadratic curves and arcs are promoted to cubics
        (DrawingML only supports cubic beziers).

        ✅ node.transform IS applied! Transform is baked into segment coordinates.

        Args:
            node: PathNode with geometry (NormalizedPath) or d (path data string)

        Returns:
            List of IR segment objects with transforms already applied

        Raises:
            ResvgShapeAdapterError: If path has no geometry
        """
        if node.geometry is None:
            raise ResvgShapeAdapterError(f"PathNode {node.id or '(unnamed)'} has no geometry")

        segments = self._commands_to_segments(node.geometry)

        # Apply node transform to all segments
        if node.transform is not None and not self._is_identity(node.transform):
            segments = self._apply_transform_to_segments(segments, node.transform)

        return segments

    def from_rect_node(self, node: RectNode) -> list[SegmentType]:
        """Convert a resvg RectNode to IR segments.

        Creates a closed rectangular path. Handles rounded corners (rx/ry)
        using cubic Bezier approximation for smooth curves.

        ✅ node.transform IS applied! Transform is baked into segment coordinates.

        Args:
            node: RectNode with x, y, width, height, rx, ry

        Returns:
            List of IR segments forming a rectangle with transforms already applied
        """
        x, y, w, h = node.x, node.y, node.width, node.height
        rx, ry = node.rx, node.ry

        # Handle zero-size rects
        if w <= 0 or h <= 0:
            return []

        # Clamp corner radii to half dimensions (SVG spec)
        rx = min(rx, w / 2.0)
        ry = min(ry, h / 2.0)

        segments: list[SegmentType] = []

        if rx > 0 or ry > 0:
            # Rounded rectangle using cubic Bezier approximation for arcs
            # Magic constant for optimal circular arc approximation
            k = 0.5522847498
            kx = k * rx
            ky = k * ry

            # Define corner centers
            # Top-left corner center: (x + rx, y + ry)
            # Top-right corner center: (x + w - rx, y + ry)
            # Bottom-right corner center: (x + w - rx, y + h - ry)
            # Bottom-left corner center: (x + rx, y + h - ry)

            # Start at top-left corner (after arc)
            p_start = Point(x + rx, y)

            # Top edge (straight line)
            p_top_right_arc_start = Point(x + w - rx, y)
            segments.append(LineSegment(p_start, p_top_right_arc_start))

            # Top-right arc (90° clockwise from top to right)
            p_right_top = Point(x + w, y + ry)
            segments.append(BezierSegment(
                start=p_top_right_arc_start,
                control1=Point(x + w - rx + kx, y),
                control2=Point(x + w, y + ry - ky),
                end=p_right_top,
            ))

            # Right edge (straight line)
            p_right_bottom = Point(x + w, y + h - ry)
            segments.append(LineSegment(p_right_top, p_right_bottom))

            # Bottom-right arc (90° clockwise from right to bottom)
            p_bottom_right_arc_end = Point(x + w - rx, y + h)
            segments.append(BezierSegment(
                start=p_right_bottom,
                control1=Point(x + w, y + h - ry + ky),
                control2=Point(x + w - rx + kx, y + h),
                end=p_bottom_right_arc_end,
            ))

            # Bottom edge (straight line)
            p_bottom_left_arc_start = Point(x + rx, y + h)
            segments.append(LineSegment(p_bottom_right_arc_end, p_bottom_left_arc_start))

            # Bottom-left arc (90° clockwise from bottom to left)
            p_left_bottom = Point(x, y + h - ry)
            segments.append(BezierSegment(
                start=p_bottom_left_arc_start,
                control1=Point(x + rx - kx, y + h),
                control2=Point(x, y + h - ry + ky),
                end=p_left_bottom,
            ))

            # Left edge (straight line)
            p_left_top = Point(x, y + ry)
            segments.append(LineSegment(p_left_bottom, p_left_top))

            # Top-left arc (90° clockwise from left to top)
            segments.append(BezierSegment(
                start=p_left_top,
                control1=Point(x, y + ry - ky),
                control2=Point(x + rx - kx, y),
                end=p_start,  # Close back to start
            ))
        else:
            # Simple rectangle
            top_left = Point(x, y)
            top_right = Point(x + w, y)
            bottom_right = Point(x + w, y + h)
            bottom_left = Point(x, y + h)

            segments.append(LineSegment(top_left, top_right))
            segments.append(LineSegment(top_right, bottom_right))
            segments.append(LineSegment(bottom_right, bottom_left))
            segments.append(LineSegment(bottom_left, top_left))  # Close

        # Apply node transform to all segments
        if node.transform is not None and not self._is_identity(node.transform):
            segments = self._apply_transform_to_segments(segments, node.transform)

        return segments

    def from_circle_node(self, node: CircleNode) -> list[SegmentType]:
        """Convert a resvg CircleNode to IR segments.

        Approximates circle using 4 cubic Bezier curves (standard technique).

        ✅ node.transform IS applied! Transform is baked into segment coordinates.

        Args:
            node: CircleNode with cx, cy, r

        Returns:
            List of IR segments forming a circle with transforms already applied
        """
        cx, cy, r = node.cx, node.cy, node.r

        if r <= 0:
            return []

        # Use ellipse converter with equal radii
        segments = self._ellipse_segments(cx, cy, r, r)

        # Apply node transform to all segments
        if node.transform is not None and not self._is_identity(node.transform):
            segments = self._apply_transform_to_segments(segments, node.transform)

        return segments

    def from_ellipse_node(self, node: EllipseNode) -> list[SegmentType]:
        """Convert a resvg EllipseNode to IR segments.

        Approximates ellipse using 4 cubic Bezier curves.

        ✅ node.transform IS applied! Transform is baked into segment coordinates.

        Args:
            node: EllipseNode with cx, cy, rx, ry

        Returns:
            List of IR segments forming an ellipse with transforms already applied
        """
        cx, cy, rx, ry = node.cx, node.cy, node.rx, node.ry

        if rx <= 0 or ry <= 0:
            return []

        segments = self._ellipse_segments(cx, cy, rx, ry)

        # Apply node transform to all segments
        if node.transform is not None and not self._is_identity(node.transform):
            segments = self._apply_transform_to_segments(segments, node.transform)

        return segments

    def from_line_node(self, node: LineNode) -> list[SegmentType]:
        """Convert a resvg LineNode to IR segments.

        ✅ node.transform IS applied! Transform is baked into segment coordinates.

        Args:
            node: LineNode with x1, y1, x2, y2

        Returns:
            List of IR segments forming the line with transforms already applied
        """
        x1, y1, x2, y2 = node.x1, node.y1, node.x2, node.y2
        if x1 == x2 and y1 == y2:
            return []

        segments = [LineSegment(Point(x1, y1), Point(x2, y2))]

        if node.transform is not None and not self._is_identity(node.transform):
            segments = self._apply_transform_to_segments(segments, node.transform)

        return segments

    def from_poly_node(self, node: PolyNode) -> list[SegmentType]:
        """Convert a resvg PolyNode to IR segments.

        ✅ node.transform IS applied! Transform is baked into segment coordinates.

        Args:
            node: PolyNode with points (flat tuple of floats)

        Returns:
            List of IR segments forming the polyline/polygon with transforms applied
        """
        points = self._points_from_flat(node.points)
        if len(points) < 2:
            return []

        segments: list[SegmentType] = []
        for start, end in zip(points, points[1:]):
            segments.append(LineSegment(start, end))

        if node.tag == "polygon" and not self._points_close(points[0], points[-1]):
            segments.append(LineSegment(points[-1], points[0]))

        if node.transform is not None and not self._is_identity(node.transform):
            segments = self._apply_transform_to_segments(segments, node.transform)

        return segments

    def _ellipse_segments(self, cx: float, cy: float, rx: float, ry: float) -> list[SegmentType]:
        """Generate IR segments for an ellipse using cubic Bezier approximation.

        Uses the magic constant k = 0.5522847498 for optimal circular arc approximation.
        This produces 4 cubic curves (one per quadrant).

        BezierSegment in IR requires control1, control2, end (no start - it's implied from previous segment).
        But the first segment needs start, so we use a LineSegment as the first segment with zero length.

        Args:
            cx, cy: Center coordinates
            rx, ry: X and Y radii

        Returns:
            List of IR segments forming an ellipse
        """
        # Magic constant for cubic Bezier circle approximation
        # k = 4 * (√2 - 1) / 3 ≈ 0.5522847498
        k = 0.5522847498
        kx = k * rx
        ky = k * ry

        # Define all quadrant points
        right = Point(cx + rx, cy)      # 3 o'clock
        bottom = Point(cx, cy + ry)     # 6 o'clock
        left = Point(cx - rx, cy)       # 9 o'clock
        top = Point(cx, cy - ry)        # 12 o'clock

        segments: list[SegmentType] = []

        # Quadrant 1: right to bottom (3 o'clock → 6 o'clock)
        segments.append(BezierSegment(
            start=right,
            control1=Point(cx + rx, cy + ky),
            control2=Point(cx + kx, cy + ry),
            end=bottom,
        ))

        # Quadrant 2: bottom to left (6 o'clock → 9 o'clock)
        segments.append(BezierSegment(
            start=bottom,
            control1=Point(cx - kx, cy + ry),
            control2=Point(cx - rx, cy + ky),
            end=left,
        ))

        # Quadrant 3: left to top (9 o'clock → 12 o'clock)
        segments.append(BezierSegment(
            start=left,
            control1=Point(cx - rx, cy - ky),
            control2=Point(cx - kx, cy - ry),
            end=top,
        ))

        # Quadrant 4: top to right (12 o'clock → 3 o'clock)
        segments.append(BezierSegment(
            start=top,
            control1=Point(cx + kx, cy - ry),
            control2=Point(cx + rx, cy - ky),
            end=right,
        ))

        return segments

    def _commands_to_segments(self, geometry) -> list[SegmentType]:
        """Convert NormalizedPath commands directly to IR segments, preserving curves.

        Unlike ``to_primitives`` (which flattens cubics to lines), this reads
        the raw ``PathCommand`` list and emits ``BezierSegment`` for cubic and
        quadratic curves.  Arcs are first decomposed into cubic segments.
        """
        from svg2ooxml.core.resvg.geometry.path_commands import (
            ARC_TO, CLOSE, CUBIC_TO, LINE_TO, MOVE_TO,
            QUAD_TO, SMOOTH_CUBIC_TO, SMOOTH_QUAD_TO,
        )
        from svg2ooxml.core.resvg.geometry.path_normalizer import (
            _arc_to_cubic_segments,
        )

        # Return raw coordinates — from_path_node() applies node.transform
        # (which is the same object as geometry.transform) to the result.
        segments: list[SegmentType] = []
        cx, cy = 0.0, 0.0
        sx, sy = 0.0, 0.0  # subpath start
        prev_cubic_ctrl: tuple[float, float] | None = None
        prev_quad_ctrl: tuple[float, float] | None = None

        def _t(x: float, y: float) -> Point:
            return Point(x, y)

        for cmd in geometry.commands:
            op = cmd.command
            pts = cmd.points

            if op == MOVE_TO:
                cx, cy = pts[0], pts[1]
                sx, sy = cx, cy
                prev_cubic_ctrl = prev_quad_ctrl = None
            elif op == LINE_TO:
                segments.append(LineSegment(_t(cx, cy), _t(pts[0], pts[1])))
                cx, cy = pts[0], pts[1]
                prev_cubic_ctrl = prev_quad_ctrl = None
            elif op == CUBIC_TO:
                p1x, p1y = pts[0], pts[1]
                p2x, p2y = pts[2], pts[3]
                ex, ey = pts[4], pts[5]
                segments.append(BezierSegment(
                    start=_t(cx, cy), control1=_t(p1x, p1y),
                    control2=_t(p2x, p2y), end=_t(ex, ey),
                ))
                prev_cubic_ctrl = (p2x, p2y)
                prev_quad_ctrl = None
                cx, cy = ex, ey
            elif op == SMOOTH_CUBIC_TO:
                if prev_cubic_ctrl is None:
                    r = (cx, cy)
                else:
                    r = (2*cx - prev_cubic_ctrl[0], 2*cy - prev_cubic_ctrl[1])
                p2x, p2y = pts[0], pts[1]
                ex, ey = pts[2], pts[3]
                segments.append(BezierSegment(
                    start=_t(cx, cy), control1=_t(r[0], r[1]),
                    control2=_t(p2x, p2y), end=_t(ex, ey),
                ))
                prev_cubic_ctrl = (p2x, p2y)
                prev_quad_ctrl = None
                cx, cy = ex, ey
            elif op == QUAD_TO:
                # Promote quadratic to cubic
                qx, qy = pts[0], pts[1]
                ex, ey = pts[2], pts[3]
                c1x = cx + (2/3)*(qx - cx)
                c1y = cy + (2/3)*(qy - cy)
                c2x = ex + (2/3)*(qx - ex)
                c2y = ey + (2/3)*(qy - ey)
                segments.append(BezierSegment(
                    start=_t(cx, cy), control1=_t(c1x, c1y),
                    control2=_t(c2x, c2y), end=_t(ex, ey),
                ))
                prev_quad_ctrl = (qx, qy)
                prev_cubic_ctrl = None
                cx, cy = ex, ey
            elif op == SMOOTH_QUAD_TO:
                if prev_quad_ctrl is None:
                    r = (cx, cy)
                else:
                    r = (2*cx - prev_quad_ctrl[0], 2*cy - prev_quad_ctrl[1])
                ex, ey = pts[0], pts[1]
                c1x = cx + (2/3)*(r[0] - cx)
                c1y = cy + (2/3)*(r[1] - cy)
                c2x = ex + (2/3)*(r[0] - ex)
                c2y = ey + (2/3)*(r[1] - ey)
                segments.append(BezierSegment(
                    start=_t(cx, cy), control1=_t(c1x, c1y),
                    control2=_t(c2x, c2y), end=_t(ex, ey),
                ))
                prev_quad_ctrl = r
                prev_cubic_ctrl = None
                cx, cy = ex, ey
            elif op == ARC_TO:
                rx, ry, rotation, large, sweep, ex, ey = pts
                arc_cubics = _arc_to_cubic_segments(
                    (cx, cy), (rx, ry, rotation, large, sweep, ex, ey),
                )
                for seg in arc_cubics:
                    segments.append(BezierSegment(
                        start=_t(seg[0][0], seg[0][1]),
                        control1=_t(seg[1][0], seg[1][1]),
                        control2=_t(seg[2][0], seg[2][1]),
                        end=_t(seg[3][0], seg[3][1]),
                    ))
                prev_cubic_ctrl = prev_quad_ctrl = None
                cx, cy = ex, ey
            elif op == CLOSE:
                if abs(cx - sx) > 1e-6 or abs(cy - sy) > 1e-6:
                    segments.append(LineSegment(_t(cx, cy), _t(sx, sy)))
                cx, cy = sx, sy
                prev_cubic_ctrl = prev_quad_ctrl = None

        return segments

    def _primitives_to_segments(self, primitives: tuple[object, ...]) -> list[SegmentType]:
        """Convert resvg path primitives to IR segments.

        MoveTo primitives update the current position without creating a segment.
        The first real drawing command (LineTo/CubicCurve/QuadraticCurve) will
        set the start point automatically.

        Args:
            primitives: Tuple of resvg primitive objects (MoveTo, LineTo, CubicCurve, etc.)

        Returns:
            List of IR segment objects
        """
        from svg2ooxml.core.resvg.geometry.primitives import (
            ClosePath,
            CubicCurve,
            LineTo,
            MoveTo,
            QuadraticCurve,
        )

        segments: list[SegmentType] = []
        current = Point(0.0, 0.0)  # Track current position
        subpath_start: Point | None = None

        for prim in primitives:
            if isinstance(prim, MoveTo):
                # MoveTo: just update current position, don't create a segment
                # The next drawing command will use this as its start point
                current = Point(prim.x, prim.y)
                subpath_start = current
            elif isinstance(prim, LineTo):
                # LineTo: create LineSegment from current to new point
                next_pt = Point(prim.x, prim.y)
                segments.append(LineSegment(current, next_pt))
                current = next_pt
            elif isinstance(prim, CubicCurve):
                # CubicCurve becomes a BezierSegment
                next_pt = Point(prim.x, prim.y)
                segments.append(BezierSegment(
                    start=current,
                    control1=Point(prim.p1x, prim.p1y),
                    control2=Point(prim.p2x, prim.p2y),
                    end=next_pt,
                ))
                current = next_pt
            elif isinstance(prim, QuadraticCurve):
                # Convert quadratic to cubic Bezier
                # For quadratic P0-P1-P2, cubic control points are:
                # C1 = P0 + 2/3 * (P1 - P0)
                # C2 = P2 + 2/3 * (P1 - P2)
                p0 = current
                p1 = Point(prim.px, prim.py)  # Control point
                p2 = Point(prim.x, prim.y)    # End point

                c1x = p0.x + (2.0 / 3.0) * (p1.x - p0.x)
                c1y = p0.y + (2.0 / 3.0) * (p1.y - p0.y)
                c2x = p2.x + (2.0 / 3.0) * (p1.x - p2.x)
                c2y = p2.y + (2.0 / 3.0) * (p1.y - p2.y)

                segments.append(BezierSegment(
                    start=p0,
                    control1=Point(c1x, c1y),
                    control2=Point(c2x, c2y),
                    end=p2,
                ))
                current = p2
            elif isinstance(prim, ClosePath):
                if subpath_start is not None and (
                    abs(current.x - subpath_start.x) > 1e-6 or abs(current.y - subpath_start.y) > 1e-6
                ):
                    segments.append(LineSegment(current, subpath_start))
                if subpath_start is not None:
                    current = subpath_start

        return segments

    def from_node(self, node: BaseNode) -> list[SegmentType]:
        """Convert any supported resvg node to IR segments.

        Dispatches to appropriate converter based on node type.

        Args:
            node: Any BaseNode subclass (PathNode, RectNode, CircleNode, EllipseNode, LineNode, PolyNode)

        Returns:
            List of IR segments

        Raises:
            ResvgShapeAdapterError: If node type is unsupported
        """
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
        elif isinstance(node, RectNode):
            return self.from_rect_node(node)
        elif isinstance(node, CircleNode):
            return self.from_circle_node(node)
        elif isinstance(node, EllipseNode):
            return self.from_ellipse_node(node)
        elif isinstance(node, LineNode):
            return self.from_line_node(node)
        elif isinstance(node, PolyNode):
            return self.from_poly_node(node)
        else:
            raise ResvgShapeAdapterError(
                f"Unsupported node type: {type(node).__name__}. "
                "Only PathNode, RectNode, CircleNode, EllipseNode, LineNode, and PolyNode are supported."
            )

    # -------------------------------------------------------------------------
    # Transform application helpers
    # -------------------------------------------------------------------------

    def _is_identity(self, matrix) -> bool:
        """Check if a Matrix is the identity matrix.

        Args:
            matrix: resvg Matrix object with a, b, c, d, e, f fields

        Returns:
            True if matrix is identity (no transformation), False otherwise
        """
        return (
            abs(matrix.a - 1.0) < 1e-9
            and abs(matrix.b) < 1e-9
            and abs(matrix.c) < 1e-9
            and abs(matrix.d - 1.0) < 1e-9
            and abs(matrix.e) < 1e-9
            and abs(matrix.f) < 1e-9
        )

    def _apply_transform_to_point(self, point: Point, matrix) -> Point:
        """Apply resvg Matrix transform to a Point.

        Args:
            point: IR Point to transform
            matrix: resvg Matrix with a, b, c, d, e, f fields

        Returns:
            New Point with transformed coordinates
        """
        if hasattr(matrix, "apply_to_point"):
            x, y = matrix.apply_to_point(point.x, point.y)
            return Point(x, y)
        if hasattr(matrix, "transform_xy"):
            x, y = matrix.transform_xy(point.x, point.y)
            return Point(x, y)
        if hasattr(matrix, "transform_point"):
            transformed = matrix.transform_point(point)
            return Point(transformed.x, transformed.y)
        return point

    def _apply_transform_to_segments(self, segments: list[SegmentType], matrix) -> list[SegmentType]:
        """Apply resvg Matrix transform to all segments.

        Args:
            segments: List of IR segments (LineSegment, BezierSegment)
            matrix: resvg Matrix to apply

        Returns:
            New list of segments with transformed coordinates
        """
        transformed: list[SegmentType] = []

        for segment in segments:
            if isinstance(segment, LineSegment):
                transformed.append(LineSegment(
                    start=self._apply_transform_to_point(segment.start, matrix),
                    end=self._apply_transform_to_point(segment.end, matrix),
                ))
            elif isinstance(segment, BezierSegment):
                transformed.append(BezierSegment(
                    start=self._apply_transform_to_point(segment.start, matrix),
                    control1=self._apply_transform_to_point(segment.control1, matrix),
                    control2=self._apply_transform_to_point(segment.control2, matrix),
                    end=self._apply_transform_to_point(segment.end, matrix),
                ))
            else:
                # Unknown segment type, pass through unchanged
                transformed.append(segment)

        return transformed

    def _points_from_flat(self, values: tuple[float, ...]) -> list[Point]:
        """Convert a flat tuple of floats into a list of Points."""
        if len(values) < 2:
            return []
        points: list[Point] = []
        for i in range(0, len(values) - 1, 2):
            points.append(Point(values[i], values[i + 1]))
        return points

    def _points_close(self, a: Point, b: Point, tol: float = 1e-9) -> bool:
        """Return True if two points are effectively identical."""
        return abs(a.x - b.x) < tol and abs(a.y - b.y) < tol


__all__ = ["ResvgShapeAdapter", "ResvgShapeAdapterError"]
