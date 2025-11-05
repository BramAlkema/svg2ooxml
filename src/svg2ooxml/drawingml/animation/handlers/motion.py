"""Motion animation handler.

This module handles motion path animations (animateMotion).
Generates PowerPoint <a:animMotion> elements with point lists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AnimationHandler, AnimationDefinition
from ..value_formatters import format_point_value

if TYPE_CHECKING:
    from svg2ooxml.common.units import UnitConverter
    from ..tav_builder import TAVBuilder
    from ..value_processors import ValueProcessor
    from ..xml_builders import AnimationXMLBuilder

__all__ = ["MotionAnimationHandler"]


class MotionAnimationHandler(AnimationHandler):
    """Handler for motion path animations.

    Handles animateMotion animations with motion paths.
    Generates PowerPoint <a:animMotion> with point list.

    PowerPoint motion animations use:
    - <a:animMotion> container
    - <a:ptLst> with list of <a:pt x="..." y="..."/> points
    - Points are in EMU (English Metric Units)

    Example:
        >>> handler = MotionAnimationHandler(xml_builder, value_processor, tav_builder, unit_converter)
        >>> animation = Mock(animation_type="animateMotion", values=["M0,0 L100,100"], duration_ms=1000)
        >>> if handler.can_handle(animation):
        ...     xml = handler.build(animation, par_id=1, behavior_id=2)
    """

    def __init__(
        self,
        xml_builder: AnimationXMLBuilder,
        value_processor: ValueProcessor,
        tav_builder: TAVBuilder,
        unit_converter: UnitConverter,
    ):
        """Initialize motion animation handler.

        Args:
            xml_builder: XML builder for creating PowerPoint elements
            value_processor: Processor for normalizing animation values
            tav_builder: Builder for creating keyframe (TAV) lists
            unit_converter: Converter for SVG units to PowerPoint EMU
        """
        super().__init__(xml_builder, value_processor, tav_builder, unit_converter)

    def can_handle(self, animation: AnimationDefinition) -> bool:
        """Check if this handler can process the animation.

        Handles animations with is_motion property or explicit motion animation type.

        Args:
            animation: Animation definition to check

        Returns:
            True if animation is a motion animation

        Example:
            >>> handler.can_handle(animation)
            True  # if animation.is_motion == True
        """
        # Import AnimationType enum
        from svg2ooxml.ir.animation import AnimationType

        # Check for explicit ANIMATE_MOTION animation type
        animation_type = self._resolve_animation_type(animation)
        if animation_type is not None:
            if isinstance(animation_type, AnimationType):
                if animation_type == AnimationType.ANIMATE_MOTION:
                    return True
            else:
                # String comparison for backward compatibility
                animation_type_str = self._animation_type_to_str(animation_type)
                canonical_token = animation_type_str
                for delimiter in (".", ":"):
                    if delimiter in canonical_token:
                        canonical_token = canonical_token.split(delimiter)[-1]
                canonical_token = canonical_token.replace("-", "_")
                if canonical_token == "ANIMATEMOTION":
                    canonical_token = "ANIMATE_MOTION"
                if canonical_token == "ANIMATE_MOTION":
                    return True

        # Check for is_motion property (from AnimationDefinition)
        # Must be explicitly True, not just truthy (to avoid Mock objects)
        if hasattr(animation, "is_motion"):
            is_motion_val = animation.is_motion
            # Check if it's a callable (property/method) or a boolean value
            if callable(is_motion_val):
                try:
                    return is_motion_val() is True
                except:
                    return False
            else:
                return is_motion_val is True

        return False

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        """Build PowerPoint timing XML for motion animation.

        Generates <p:par> container with <a:animMotion> element containing:
        - <a:cBhvr> with target shape
        - <a:ptLst> with motion path points in EMU

        Args:
            animation: Animation definition to convert
            par_id: Unique ID for the <p:par> element
            behavior_id: Unique ID for the behavior element

        Returns:
            PowerPoint timing XML as string

        Example:
            >>> xml = handler.build(animation, par_id=1, behavior_id=2)
            >>> # Returns: '<p:par>...<a:animMotion>...<a:ptLst>...</a:ptLst>...</a:animMotion>...</p:par>'
        """
        # Extract motion path from values
        if not animation.values:
            return ""

        path_value = animation.values[0]
        points = self._parse_motion_path(path_value)

        # Need at least 2 points for motion
        if len(points) < 2:
            return ""

        # Build point list entries
        point_entries = []
        for x_px, y_px in points:
            x_emu = self._units.to_emu(x_px, axis="x")
            y_emu = self._units.to_emu(y_px, axis="y")
            point_entries.append(
                f'                                        <a:pt x="{int(round(x_emu))}" y="{int(round(y_emu))}"/>'
            )

        pt_lst = "\n".join(point_entries)

        # Build behavior core
        behavior_core = self._xml.build_behavior_core(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id if hasattr(animation, "element_id") else "",
        )

        # Build animMotion element
        anim_motion = (
            f'                                    <a:animMotion>\n'
            f'{behavior_core}'
            f'                                        <a:ptLst>\n'
            f'{pt_lst}\n'
            f'                                        </a:ptLst>\n'
            f'                                    </a:animMotion>'
        )

        # Build par container
        par = self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_content=anim_motion,
        )

        return par

    def _parse_motion_path(self, path_value: str) -> list[tuple[float, float]]:
        """Parse SVG motion path into list of points.

        Handles SVG path data by:
        1. Parsing path commands (M, L, C, etc.)
        2. Converting curves to line segments by sampling
        3. Deduplicating points

        Args:
            path_value: SVG path data string (e.g., "M0,0 L100,100")

        Returns:
            List of (x, y) coordinate tuples in pixels

        Example:
            >>> handler._parse_motion_path("M0,0 L100,100")
            [(0.0, 0.0), (100.0, 100.0)]
        """
        if not path_value:
            return []

        # Import path parsing utilities
        try:
            from svg2ooxml.common.geometry.paths import (
                parse_path_data,
                PathParseError,
            )
            from svg2ooxml.common.geometry.paths.segments import (
                LineSegment,
                BezierSegment,
            )
            from svg2ooxml.ir.geometry import Point
        except ImportError:
            # Fallback: simple parsing
            return self._simple_path_parse(path_value)

        # Parse path data
        try:
            segments = parse_path_data(path_value)
        except PathParseError:
            return []

        if not segments:
            return []

        # Extract points from segments
        points: list[Point] = []
        first_segment = segments[0]
        points.append(first_segment.start)

        for segment in segments:
            if isinstance(segment, LineSegment):
                points.append(segment.end)
            elif isinstance(segment, BezierSegment):
                # Sample bezier curve
                points.extend(self._sample_bezier(segment))

        # Convert to tuples and deduplicate
        return self._dedupe_points(points)

    def _sample_bezier(
        self,
        segment: BezierSegment,
        *,
        steps: int = 20,
    ) -> list[Point]:
        """Sample bezier curve into line segments.

        Args:
            segment: Bezier curve segment
            steps: Number of sample points

        Returns:
            List of sampled points along the curve
        """
        from svg2ooxml.ir.geometry import Point

        samples: list[Point] = []
        for index in range(1, steps + 1):
            t = index / steps
            samples.append(self._bezier_point(segment, t))
        return samples

    def _bezier_point(self, segment: BezierSegment, t: float) -> Point:
        """Calculate point on cubic bezier curve at parameter t.

        Uses De Casteljau's algorithm for cubic bezier curves:
        P(t) = (1-t)³P₀ + 3(1-t)²tP₁ + 3(1-t)t²P₂ + t³P₃

        Args:
            segment: Bezier segment with start, control1, control2, end points
            t: Parameter in range [0, 1]

        Returns:
            Point on the curve at parameter t
        """
        from svg2ooxml.ir.geometry import Point

        mt = 1.0 - t
        x = (
            mt ** 3 * segment.start.x
            + 3 * mt ** 2 * t * segment.control1.x
            + 3 * mt * t ** 2 * segment.control2.x
            + t ** 3 * segment.end.x
        )
        y = (
            mt ** 3 * segment.start.y
            + 3 * mt ** 2 * t * segment.control1.y
            + 3 * mt * t ** 2 * segment.control2.y
            + t ** 3 * segment.end.y
        )
        return Point(x=x, y=y)

    def _dedupe_points(self, points: list[Point]) -> list[tuple[float, float]]:
        """Remove duplicate consecutive points from path.

        Args:
            points: List of Point objects

        Returns:
            List of unique (x, y) tuples with duplicates removed

        Example:
            >>> handler._dedupe_points([Point(0, 0), Point(0, 0), Point(1, 1)])
            [(0.0, 0.0), (1.0, 1.0)]
        """
        deduped: list[tuple[float, float]] = []
        epsilon = 1e-6

        for point in points:
            pair = (point.x, point.y)
            if not deduped or (
                abs(deduped[-1][0] - pair[0]) > epsilon
                or abs(deduped[-1][1] - pair[1]) > epsilon
            ):
                deduped.append(pair)

        return deduped

    def _simple_path_parse(self, path_value: str) -> list[tuple[float, float]]:
        """Fallback simple path parser for basic M/L commands.

        Args:
            path_value: SVG path string

        Returns:
            List of (x, y) points

        Example:
            >>> handler._simple_path_parse("M 0 0 L 100 100")
            [(0.0, 0.0), (100.0, 100.0)]
        """
        points: list[tuple[float, float]] = []
        tokens = path_value.replace(",", " ").split()

        i = 0
        while i < len(tokens):
            cmd = tokens[i]
            if cmd.upper() in ("M", "L"):
                if i + 2 < len(tokens):
                    try:
                        x = float(tokens[i + 1])
                        y = float(tokens[i + 2])
                        points.append((x, y))
                        i += 3
                    except ValueError:
                        i += 1
                else:
                    i += 1
            else:
                i += 1

        return points
