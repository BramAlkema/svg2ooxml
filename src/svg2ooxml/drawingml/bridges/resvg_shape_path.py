"""Path conversion helpers for ``ResvgShapeAdapter``."""

from __future__ import annotations

from svg2ooxml.common.geometry.paths.quadratic import (
    quadratic_to_cubic,
    quadratic_tuple_to_cubic_controls,
)
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType


class ResvgShapePathMixin:
    """Convert resvg path commands and primitives into IR segments."""

    def _commands_to_segments(self, geometry) -> list[SegmentType]:
        """Convert NormalizedPath commands directly to IR segments."""
        from svg2ooxml.core.resvg.geometry.path_commands import (
            ARC_TO,
            CLOSE,
            CUBIC_TO,
            LINE_TO,
            MOVE_TO,
            QUAD_TO,
            SMOOTH_CUBIC_TO,
            SMOOTH_QUAD_TO,
        )
        from svg2ooxml.core.resvg.geometry.path_normalizer import (
            _arc_to_cubic_segments,
        )

        segments: list[SegmentType] = []
        cx, cy = 0.0, 0.0
        sx, sy = 0.0, 0.0
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
                segments.append(
                    BezierSegment(
                        start=_t(cx, cy),
                        control1=_t(p1x, p1y),
                        control2=_t(p2x, p2y),
                        end=_t(ex, ey),
                    )
                )
                prev_cubic_ctrl = (p2x, p2y)
                prev_quad_ctrl = None
                cx, cy = ex, ey
            elif op == SMOOTH_CUBIC_TO:
                if prev_cubic_ctrl is None:
                    r = (cx, cy)
                else:
                    r = (2 * cx - prev_cubic_ctrl[0], 2 * cy - prev_cubic_ctrl[1])
                p2x, p2y = pts[0], pts[1]
                ex, ey = pts[2], pts[3]
                segments.append(
                    BezierSegment(
                        start=_t(cx, cy),
                        control1=_t(r[0], r[1]),
                        control2=_t(p2x, p2y),
                        end=_t(ex, ey),
                    )
                )
                prev_cubic_ctrl = (p2x, p2y)
                prev_quad_ctrl = None
                cx, cy = ex, ey
            elif op == QUAD_TO:
                qx, qy = pts[0], pts[1]
                ex, ey = pts[2], pts[3]
                c1, c2 = quadratic_tuple_to_cubic_controls(
                    (cx, cy),
                    (qx, qy),
                    (ex, ey),
                )
                segments.append(
                    BezierSegment(
                        start=_t(cx, cy),
                        control1=_t(c1[0], c1[1]),
                        control2=_t(c2[0], c2[1]),
                        end=_t(ex, ey),
                    )
                )
                prev_quad_ctrl = (qx, qy)
                prev_cubic_ctrl = None
                cx, cy = ex, ey
            elif op == SMOOTH_QUAD_TO:
                if prev_quad_ctrl is None:
                    r = (cx, cy)
                else:
                    r = (2 * cx - prev_quad_ctrl[0], 2 * cy - prev_quad_ctrl[1])
                ex, ey = pts[0], pts[1]
                c1, c2 = quadratic_tuple_to_cubic_controls(
                    (cx, cy),
                    r,
                    (ex, ey),
                )
                segments.append(
                    BezierSegment(
                        start=_t(cx, cy),
                        control1=_t(c1[0], c1[1]),
                        control2=_t(c2[0], c2[1]),
                        end=_t(ex, ey),
                    )
                )
                prev_quad_ctrl = r
                prev_cubic_ctrl = None
                cx, cy = ex, ey
            elif op == ARC_TO:
                rx, ry, rotation, large, sweep, ex, ey = pts
                arc_cubics = _arc_to_cubic_segments(
                    (cx, cy), (rx, ry, rotation, large, sweep, ex, ey)
                )
                for seg in arc_cubics:
                    segments.append(
                        BezierSegment(
                            start=_t(seg[0][0], seg[0][1]),
                            control1=_t(seg[1][0], seg[1][1]),
                            control2=_t(seg[2][0], seg[2][1]),
                            end=_t(seg[3][0], seg[3][1]),
                        )
                    )
                prev_cubic_ctrl = prev_quad_ctrl = None
                cx, cy = ex, ey
            elif op == CLOSE:
                if abs(cx - sx) > 1e-6 or abs(cy - sy) > 1e-6:
                    segments.append(LineSegment(_t(cx, cy), _t(sx, sy)))
                cx, cy = sx, sy
                prev_cubic_ctrl = prev_quad_ctrl = None

        return segments

    def _primitives_to_segments(
        self, primitives: tuple[object, ...]
    ) -> list[SegmentType]:
        """Convert resvg path primitives to IR segments."""
        from svg2ooxml.core.resvg.geometry.primitives import (
            ClosePath,
            CubicCurve,
            LineTo,
            MoveTo,
            QuadraticCurve,
        )

        segments: list[SegmentType] = []
        current = Point(0.0, 0.0)
        subpath_start: Point | None = None

        for prim in primitives:
            if isinstance(prim, MoveTo):
                current = Point(prim.x, prim.y)
                subpath_start = current
            elif isinstance(prim, LineTo):
                next_pt = Point(prim.x, prim.y)
                segments.append(LineSegment(current, next_pt))
                current = next_pt
            elif isinstance(prim, CubicCurve):
                next_pt = Point(prim.x, prim.y)
                segments.append(
                    BezierSegment(
                        start=current,
                        control1=Point(prim.p1x, prim.p1y),
                        control2=Point(prim.p2x, prim.p2y),
                        end=next_pt,
                    )
                )
                current = next_pt
            elif isinstance(prim, QuadraticCurve):
                p0 = current
                p1 = Point(prim.px, prim.py)
                p2 = Point(prim.x, prim.y)
                segments.append(quadratic_to_cubic(p0, p1, p2))
                current = p2
            elif isinstance(prim, ClosePath):
                if subpath_start is not None and (
                    abs(current.x - subpath_start.x) > 1e-6
                    or abs(current.y - subpath_start.y) > 1e-6
                ):
                    segments.append(LineSegment(current, subpath_start))
                if subpath_start is not None:
                    current = subpath_start

        return segments


__all__ = ["ResvgShapePathMixin"]
