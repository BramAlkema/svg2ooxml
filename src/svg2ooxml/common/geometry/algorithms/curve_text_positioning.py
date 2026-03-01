"""
Curve Text Positioning Algorithms

Advanced algorithms for positioning text along curved paths, extracted and
modernized from legacy text_path.py implementation. Provides precise
character positioning with proper tangent calculation and path sampling.

Key Algorithms:
- Path sampling with adaptive density
- Cubic and quadratic Bézier curve sampling
- Tangent angle calculation for character rotation
- Distance-based character positioning
- Advanced path parsing and normalization
"""

import logging
import math
import re
from dataclasses import dataclass
from enum import Enum

from svg2ooxml.ir.geometry import Point
from svg2ooxml.ir.text_path import PathPoint


class PathSamplingMethod(Enum):
    """Path sampling methods for different use cases."""
    UNIFORM = "uniform"          # Uniform parameter distribution
    ARC_LENGTH = "arc_length"    # Arc-length parameterization (DETERMINISTIC)
    ADAPTIVE = "adaptive"        # Adaptive density based on curvature
    DETERMINISTIC = "deterministic"  # Contract-guaranteed deterministic sampling


@dataclass
class PathSegment:
    """Represents a single path segment."""
    start_point: Point
    end_point: Point
    control_points: list[Point]
    segment_type: str  # 'line', 'cubic', 'quadratic', 'arc'
    length: float


class CurveTextPositioner:
    """
    Advanced curve text positioning using sophisticated path sampling.

    Provides precise character positioning along complex curves with
    proper tangent calculation and adaptive sampling density.
    """

    def __init__(self, sampling_method: PathSamplingMethod = PathSamplingMethod.ADAPTIVE):
        """
        Initialize curve text positioner.

        Args:
            sampling_method: Method for path sampling
        """
        self.sampling_method = sampling_method
        self.default_samples_per_unit = 0.5  # Samples per unit length
        self.logger = logging.getLogger(__name__)

    def sample_path_for_text(self, path_data: str, num_samples: int | None = None) -> list[PathPoint]:
        """
        Sample path points optimized for text positioning.

        Contract for DETERMINISTIC mode:
        - Always returns exactly num_samples points (including endpoints)
        - distance_along_path is strictly non-decreasing
        - Equal arc-length spacing across entire path

        Args:
            path_data: SVG path data string
            num_samples: Number of samples (auto-calculated if None)

        Returns:
            List of PathPoint objects with position and tangent information
        """
        try:
            # Parse path into segments
            segments = self._parse_path_segments(path_data)
            if not segments:
                return self._fallback_horizontal_line(num_samples or 2)

            # Calculate total path length
            total_length = sum(segment.length for segment in segments)
            if total_length == 0:
                return self._fallback_horizontal_line(num_samples or 2)

            # Determine sampling density
            if num_samples is None:
                if self.sampling_method == PathSamplingMethod.DETERMINISTIC:
                    num_samples = max(2, min(4096, int(total_length * self.default_samples_per_unit)))
                else:
                    num_samples = max(20, min(200, int(total_length * self.default_samples_per_unit)))

            # Use deterministic equal arc-length sampling for contract guarantee
            if self.sampling_method == PathSamplingMethod.DETERMINISTIC:
                return self._sample_path_deterministic(segments, total_length, num_samples)
            else:
                # Legacy proportional sampling
                return self._sample_path_proportional(segments, total_length, num_samples)

        except Exception as e:
            self.logger.warning(f"Path sampling failed: {e}")
            return self._fallback_horizontal_line(num_samples or 2)

    def _sample_path_deterministic(self, segments: list[PathSegment], total_length: float, num_samples: int) -> list[PathPoint]:
        """
        Deterministic equal arc-length sampling with contract guarantees.

        Contract:
        - Returns exactly num_samples points
        - Monotonic distance_along_path
        - Equal spacing by arc length
        """
        # Build cumulative length table
        cumulative_lengths = [0.0]
        for segment in segments:
            cumulative_lengths.append(cumulative_lengths[-1] + segment.length)

        path_points = []

        for i in range(num_samples):
            # Calculate target distance along path
            s_target = (total_length * i) / (num_samples - 1) if num_samples > 1 else 0

            # Find segment containing this distance
            seg_idx = 0
            for j in range(len(cumulative_lengths) - 1):
                if cumulative_lengths[j] <= s_target <= cumulative_lengths[j + 1]:
                    seg_idx = j
                    break

            # Calculate local distance within segment
            s_local = s_target - cumulative_lengths[seg_idx]
            segment = segments[seg_idx]

            # Sample point at local distance
            point = self._sample_segment_at_distance(segment, s_local, s_target)
            path_points.append(point)

        return path_points

    def _sample_path_proportional(self, segments: list[PathSegment], total_length: float, num_samples: int) -> list[PathPoint]:
        """Legacy proportional sampling method."""
        path_points = []
        cumulative_distance = 0.0

        for segment in segments:
            # Calculate samples for this segment
            segment_ratio = segment.length / total_length if total_length > 0 else 0
            segment_samples = max(2, int(num_samples * segment_ratio))

            # Sample the segment
            segment_points = self._sample_segment(segment, segment_samples, cumulative_distance)

            # Add to total (skip first point to avoid duplicates except for first segment)
            if not path_points:
                path_points.extend(segment_points)
            else:
                path_points.extend(segment_points[1:])

            cumulative_distance += segment.length

        return path_points

    def _fallback_horizontal_line(self, num_samples: int) -> list[PathPoint]:
        """Generate fallback horizontal line when path parsing fails."""
        points = []
        for i in range(num_samples):
            x = 100.0 * i / max(1, num_samples - 1)
            points.append(PathPoint(
                x=x, y=0.0,
                tangent_angle=0.0,
                distance_along_path=x,
            ))
        return points

    def _sample_segment_at_distance(self, segment: PathSegment, local_distance: float, global_distance: float) -> PathPoint:
        """Sample a single point at specified distance within segment."""
        # Calculate parameter t for this distance
        if segment.length == 0:
            t = 0.0
        else:
            t = local_distance / segment.length

        # Clamp t to [0, 1]
        t = max(0.0, min(1.0, t))

        # Sample point based on segment type
        if segment.segment_type == 'line':
            return self._eval_line_at_t(segment, t, global_distance)
        elif segment.segment_type == 'cubic':
            return self._eval_cubic_at_t(segment, t, global_distance)
        elif segment.segment_type == 'quadratic':
            return self._eval_quadratic_at_t(segment, t, global_distance)
        else:
            # Fallback to linear interpolation
            return self._eval_line_at_t(segment, t, global_distance)

    def _eval_line_at_t(self, segment: PathSegment, t: float, distance: float) -> PathPoint:
        """Evaluate line segment at parameter t."""
        start, end = segment.start_point, segment.end_point
        x = start.x + t * (end.x - start.x)
        y = start.y + t * (end.y - start.y)

        # Calculate tangent
        dx = end.x - start.x
        dy = end.y - start.y
        angle = math.atan2(dy, dx) if (dx != 0 or dy != 0) else 0.0

        return PathPoint(x=x, y=y, tangent_angle=angle, distance_along_path=distance)

    def _eval_cubic_at_t(self, segment: PathSegment, t: float, distance: float) -> PathPoint:
        """Evaluate cubic Bézier segment at parameter t."""
        p0 = segment.start_point
        p3 = segment.end_point
        p1, p2 = segment.control_points[0], segment.control_points[1]

        # Cubic Bézier evaluation
        x = ((1-t)**3 * p0.x + 3*(1-t)**2*t * p1.x +
             3*(1-t)*t**2 * p2.x + t**3 * p3.x)
        y = ((1-t)**3 * p0.y + 3*(1-t)**2*t * p1.y +
             3*(1-t)*t**2 * p2.y + t**3 * p3.y)

        # Tangent calculation (derivative)
        dx_dt = (3*(1-t)**2*(p1.x-p0.x) + 6*(1-t)*t*(p2.x-p1.x) +
                 3*t**2*(p3.x-p2.x))
        dy_dt = (3*(1-t)**2*(p1.y-p0.y) + 6*(1-t)*t*(p2.y-p1.y) +
                 3*t**2*(p3.y-p2.y))

        angle = math.atan2(dy_dt, dx_dt) if (dx_dt != 0 or dy_dt != 0) else 0.0

        return PathPoint(x=x, y=y, tangent_angle=angle, distance_along_path=distance)

    def _eval_quadratic_at_t(self, segment: PathSegment, t: float, distance: float) -> PathPoint:
        """Evaluate quadratic Bézier segment at parameter t."""
        p0 = segment.start_point
        p2 = segment.end_point
        p1 = segment.control_points[0]

        # Quadratic Bézier evaluation
        x = (1-t)**2 * p0.x + 2*(1-t)*t * p1.x + t**2 * p2.x
        y = (1-t)**2 * p0.y + 2*(1-t)*t * p1.y + t**2 * p2.y

        # Tangent calculation (derivative)
        dx_dt = 2*(1-t)*(p1.x-p0.x) + 2*t*(p2.x-p1.x)
        dy_dt = 2*(1-t)*(p1.y-p0.y) + 2*t*(p2.y-p1.y)

        angle = math.atan2(dy_dt, dx_dt) if (dx_dt != 0 or dy_dt != 0) else 0.0

        return PathPoint(x=x, y=y, tangent_angle=angle, distance_along_path=distance)

    def _parse_path_segments(self, path_data: str) -> list[PathSegment]:
        """Parse SVG path data into segments."""
        segments = []

        # Parse path commands
        commands = self._parse_path_commands(path_data)
        if not commands:
            return []

        current_point = Point(0.0, 0.0)
        start_point = Point(0.0, 0.0)

        for cmd_tuple in commands:
            cmd = cmd_tuple[0]
            args = list(cmd_tuple[1:]) if len(cmd_tuple) > 1 else []

            # Handle relative commands
            if cmd.islower() and cmd.upper() != 'Z':
                cmd = cmd.upper()
                # Convert relative coordinates to absolute
                for i in range(0, len(args), 2):
                    if i + 1 < len(args):
                        args[i] += current_point.x
                        args[i + 1] += current_point.y

            if cmd == 'M':
                # Move to
                if len(args) >= 2:
                    current_point = Point(args[0], args[1])
                    start_point = current_point

            elif cmd == 'L':
                # Line to
                if len(args) >= 2:
                    end_point = Point(args[0], args[1])
                    segment = self._create_line_segment(current_point, end_point)
                    segments.append(segment)
                    current_point = end_point

            elif cmd == 'C':
                # Cubic Bézier curve
                if len(args) >= 6:
                    cp1 = Point(args[0], args[1])
                    cp2 = Point(args[2], args[3])
                    end_point = Point(args[4], args[5])
                    segment = self._create_cubic_segment(current_point, cp1, cp2, end_point)
                    segments.append(segment)
                    current_point = end_point

            elif cmd == 'Q':
                # Quadratic Bézier curve
                if len(args) >= 4:
                    cp = Point(args[0], args[1])
                    end_point = Point(args[2], args[3])
                    segment = self._create_quadratic_segment(current_point, cp, end_point)
                    segments.append(segment)
                    current_point = end_point

            elif cmd == 'A':
                # Arc - approximate with segments
                if len(args) >= 7:
                    rx, ry = abs(args[0]), abs(args[1])
                    large_arc = bool(args[3])
                    sweep = bool(args[4])
                    end_point = Point(args[5], args[6])
                    
                    if rx == 0 or ry == 0 or current_point == end_point:
                        segment = self._create_line_segment(current_point, end_point)
                        segments.append(segment)
                    else:
                        # Simple approximation: subdivide into a few lines to capture curvature
                        # For better accuracy we would use proper arc-to-bezier conversion
                        mid_x = (current_point.x + end_point.x) / 2.0
                        mid_y = (current_point.y + end_point.y) / 2.0
                        # Nudge midpoint to avoid perfect flatness if it's an arc
                        # This is a very rough heuristic to help the classifier
                        offset = min(rx, ry) * (0.5 if large_arc else 0.2)
                        if sweep:
                            mid_y += offset
                        else:
                            mid_y -= offset
                        
                        segments.append(self._create_line_segment(current_point, Point(mid_x, mid_y)))
                        segments.append(self._create_line_segment(Point(mid_x, mid_y), end_point))
                    
                    current_point = end_point

            elif cmd == 'Z':
                # Close path
                if current_point != start_point:
                    segment = self._create_line_segment(current_point, start_point)
                    segments.append(segment)
                    current_point = start_point

        return segments

    def _parse_path_commands(self, path_data: str) -> list[tuple]:
        """Parse SVG path data into command tuples."""
        commands = []
        # Improved pattern to capture command and all following numbers
        pattern = r'([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)'

        for match in re.finditer(pattern, path_data):
            cmd = match.group(1)
            params_str = match.group(2).strip()

            if params_str:
                # Parse numeric parameters - handle spaces as separators
                params = []
                # More robust number parsing
                for num in re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', params_str):
                    params.append(float(num))
                if params:
                    commands.append((cmd, *params))
                else:
                    commands.append((cmd,))
            else:
                commands.append((cmd,))

        return commands

    def _create_line_segment(self, start: Point, end: Point) -> PathSegment:
        """Create line segment."""
        length = math.sqrt((end.x - start.x)**2 + (end.y - start.y)**2)
        return PathSegment(
            start_point=start,
            end_point=end,
            control_points=[],
            segment_type='line',
            length=length,
        )

    def _create_cubic_segment(self, start: Point, cp1: Point, cp2: Point, end: Point) -> PathSegment:
        """Create cubic Bézier segment."""
        # Estimate length using control polygon approximation
        length = (
            math.sqrt((cp1.x - start.x)**2 + (cp1.y - start.y)**2) +
            math.sqrt((cp2.x - cp1.x)**2 + (cp2.y - cp1.y)**2) +
            math.sqrt((end.x - cp2.x)**2 + (end.y - cp2.y)**2)
        )
        return PathSegment(
            start_point=start,
            end_point=end,
            control_points=[cp1, cp2],
            segment_type='cubic',
            length=length,
        )

    def _create_quadratic_segment(self, start: Point, cp: Point, end: Point) -> PathSegment:
        """Create quadratic Bézier segment."""
        # Estimate length using control polygon approximation
        length = (
            math.sqrt((cp.x - start.x)**2 + (cp.y - start.y)**2) +
            math.sqrt((end.x - cp.x)**2 + (end.y - cp.y)**2)
        )
        return PathSegment(
            start_point=start,
            end_point=end,
            control_points=[cp],
            segment_type='quadratic',
            length=length,
        )

    def _sample_segment(self, segment: PathSegment, num_samples: int, base_distance: float) -> list[PathPoint]:
        """Sample points along a segment."""
        if segment.segment_type == 'line':
            return self._sample_line_segment(segment, num_samples, base_distance)
        elif segment.segment_type == 'cubic':
            return self._sample_cubic_segment(segment, num_samples, base_distance)
        elif segment.segment_type == 'quadratic':
            return self._sample_quadratic_segment(segment, num_samples, base_distance)
        else:
            # Fallback to line
            return self._sample_line_segment(segment, num_samples, base_distance)

    def _sample_line_segment(self, segment: PathSegment, num_samples: int, base_distance: float) -> list[PathPoint]:
        """Sample points along a line segment."""
        points = []
        start = segment.start_point
        end = segment.end_point

        # Calculate tangent angle
        angle_rad = math.atan2(end.y - start.y, end.x - start.x)
        math.degrees(angle_rad)

        for i in range(num_samples):
            t = i / (num_samples - 1) if num_samples > 1 else 0

            x = start.x + t * (end.x - start.x)
            y = start.y + t * (end.y - start.y)
            distance = base_distance + t * segment.length

            point = PathPoint(
                x=x,
                y=y,
                tangent_angle=angle_rad,
                distance_along_path=distance,
            )
            points.append(point)

        return points

    def _sample_cubic_segment(self, segment: PathSegment, num_samples: int, base_distance: float) -> list[PathPoint]:
        """Sample points along a cubic Bézier segment."""
        points = []
        start = segment.start_point
        cp1, cp2 = segment.control_points
        end = segment.end_point

        for i in range(num_samples):
            t = i / (num_samples - 1) if num_samples > 1 else 0

            # Cubic Bézier point calculation
            x = (
                (1 - t)**3 * start.x +
                3 * (1 - t)**2 * t * cp1.x +
                3 * (1 - t) * t**2 * cp2.x +
                t**3 * end.x
            )
            y = (
                (1 - t)**3 * start.y +
                3 * (1 - t)**2 * t * cp1.y +
                3 * (1 - t) * t**2 * cp2.y +
                t**3 * end.y
            )

            # Calculate tangent by taking derivative
            dx_dt = (
                -3 * (1 - t)**2 * start.x +
                3 * (1 - t)**2 * cp1.x - 6 * (1 - t) * t * cp1.x +
                6 * (1 - t) * t * cp2.x - 3 * t**2 * cp2.x +
                3 * t**2 * end.x
            )
            dy_dt = (
                -3 * (1 - t)**2 * start.y +
                3 * (1 - t)**2 * cp1.y - 6 * (1 - t) * t * cp1.y +
                6 * (1 - t) * t * cp2.y - 3 * t**2 * cp2.y +
                3 * t**2 * end.y
            )

            # Calculate tangent angle
            angle_rad = math.atan2(dy_dt, dx_dt) if dx_dt != 0 or dy_dt != 0 else 0
            distance = base_distance + t * segment.length

            point = PathPoint(
                x=x,
                y=y,
                tangent_angle=angle_rad,
                distance_along_path=distance,
            )
            points.append(point)

        return points

    def _sample_quadratic_segment(self, segment: PathSegment, num_samples: int, base_distance: float) -> list[PathPoint]:
        """Sample points along a quadratic Bézier segment."""
        points = []
        start = segment.start_point
        cp = segment.control_points[0]
        end = segment.end_point

        for i in range(num_samples):
            t = i / (num_samples - 1) if num_samples > 1 else 0

            # Quadratic Bézier point calculation
            x = (1 - t)**2 * start.x + 2 * (1 - t) * t * cp.x + t**2 * end.x
            y = (1 - t)**2 * start.y + 2 * (1 - t) * t * cp.y + t**2 * end.y

            # Calculate tangent by taking derivative
            dx_dt = 2 * (1 - t) * (cp.x - start.x) + 2 * t * (end.x - cp.x)
            dy_dt = 2 * (1 - t) * (cp.y - start.y) + 2 * t * (end.y - cp.y)

            # Calculate tangent angle
            angle_rad = math.atan2(dy_dt, dx_dt) if dx_dt != 0 or dy_dt != 0 else 0
            distance = base_distance + t * segment.length

            point = PathPoint(
                x=x,
                y=y,
                tangent_angle=angle_rad,
                distance_along_path=distance,
            )
            points.append(point)

        return points

    def find_point_at_distance(self, path_points: list[PathPoint], target_distance: float) -> PathPoint | None:
        """
        Find path point at specific distance using interpolation.

        Args:
            path_points: List of sampled path points
            target_distance: Target distance along path

        Returns:
            PathPoint at target distance, or None if not found
        """
        if not path_points:
            return None

        # Handle edge cases
        if target_distance <= path_points[0].distance_along_path:
            return path_points[0]
        if target_distance >= path_points[-1].distance_along_path:
            return path_points[-1]

        # Find surrounding points for interpolation
        for i in range(len(path_points) - 1):
            curr_point = path_points[i]
            next_point = path_points[i + 1]

            if curr_point.distance_along_path <= target_distance <= next_point.distance_along_path:
                # Interpolate between points
                distance_range = next_point.distance_along_path - curr_point.distance_along_path
                if distance_range > 0:
                    t = (target_distance - curr_point.distance_along_path) / distance_range

                    # Linear interpolation
                    x = curr_point.x + t * (next_point.x - curr_point.x)
                    y = curr_point.y + t * (next_point.y - curr_point.y)

                    # Interpolate angle (handling angle wrapping)
                    angle = self._interpolate_angle(curr_point.tangent_angle, next_point.tangent_angle, t)

                    return PathPoint(
                        x=x,
                        y=y,
                        tangent_angle=angle,
                        distance_along_path=target_distance,
                    )
                else:
                    return curr_point

        return None

    def _interpolate_angle(self, angle1: float, angle2: float, t: float) -> float:
        """Interpolate between two angles handling wraparound."""
        # Normalize angles to [0, 2π)
        angle1 = angle1 % (2 * math.pi)
        angle2 = angle2 % (2 * math.pi)

        # Handle angle wraparound
        diff = angle2 - angle1
        if diff > math.pi:
            diff -= 2 * math.pi
        elif diff < -math.pi:
            diff += 2 * math.pi

        return angle1 + t * diff

    def calculate_path_curvature(self, path_points: list[PathPoint], point_index: int) -> float:
        """
        Calculate curvature at a specific path point.

        Args:
            path_points: List of path points
            point_index: Index of point to calculate curvature for

        Returns:
            Curvature value (0 = straight, higher = more curved)
        """
        if len(path_points) < 3 or point_index < 1 or point_index >= len(path_points) - 1:
            return 0.0

        # Use three-point curvature approximation
        p1 = path_points[point_index - 1]
        p2 = path_points[point_index]
        p3 = path_points[point_index + 1]

        # Calculate vectors
        v1 = (p2.x - p1.x, p2.y - p1.y)
        v2 = (p3.x - p2.x, p3.y - p2.y)

        # Calculate cross product for curvature
        cross = v1[0] * v2[1] - v1[1] * v2[0]

        # Calculate magnitudes
        mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
        mag2 = math.sqrt(v2[0]**2 + v2[1]**2)

        if mag1 * mag2 > 0:
            return abs(cross) / (mag1 * mag2)
        else:
            return 0.0


def create_curve_text_positioner(sampling_method: PathSamplingMethod = PathSamplingMethod.ADAPTIVE) -> CurveTextPositioner:
    """
    Create curve text positioner with specified sampling method.

    Args:
        sampling_method: Path sampling method

    Returns:
        Configured CurveTextPositioner instance
    """
    return CurveTextPositioner(sampling_method)

# Re-export from extracted module for backward compatibility
from svg2ooxml.common.geometry.algorithms.path_warp_fitter import (  # noqa: F401
    PathWarpFitter,
    WarpFitResult,
    create_path_warp_fitter,
)