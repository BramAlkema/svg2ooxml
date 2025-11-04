"""Time-Animated Value (TAV) list builder.

This module builds PowerPoint keyframe lists (<a:tavLst>) with proper timing,
spline metadata, and acceleration/deceleration values.

TAV elements represent keyframes in PowerPoint animations, with support for:
- Timing resolution (auto-distribute or explicit keyTimes)
- Bezier spline metadata (svg2:spline, svg2:accel, svg2:decel)
- Value formatting (numeric, color, point, etc.)
"""

from __future__ import annotations

from typing import Protocol, Sequence, TYPE_CHECKING

from lxml import etree

if TYPE_CHECKING:
    from .xml_builders import AnimationXMLBuilder

__all__ = ["TAVBuilder", "ValueFormatter"]


class ValueFormatter(Protocol):
    """Protocol for value formatters.

    Value formatters convert animation values to lxml elements.
    """

    def __call__(self, value: str) -> etree._Element:
        """Format value as lxml element.

        Args:
            value: Animation value as string

        Returns:
            lxml Element (e.g., <a:val val="..."/>)
        """
        ...


class TAVBuilder:
    """Build Time-Animated Value (keyframe) lists.

    This class handles timing resolution, spline metadata computation,
    and TAV list construction for PowerPoint animations.

    Example:
        >>> builder = TAVBuilder(xml_builder)
        >>> tav_elements, needs_ns = builder.build_tav_list(
        ...     values=["0", "100"],
        ...     key_times=None,
        ...     key_splines=None,
        ...     duration_ms=1000,
        ...     value_formatter=format_numeric_value
        ... )
    """

    def __init__(self, xml_builder: AnimationXMLBuilder):
        """Initialize TAV builder.

        Args:
            xml_builder: XML builder for creating TAV elements
        """
        self._xml = xml_builder

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def build_tav_list(
        self,
        *,
        values: Sequence[str],
        key_times: Sequence[float] | None,
        key_splines: Sequence[list[float]] | None,
        duration_ms: int,
        value_formatter: ValueFormatter,
    ) -> tuple[list[etree._Element], bool]:
        """Build list of <a:tav> elements.

        Args:
            values: Animation values as strings
            key_times: Explicit keyframe times (0.0-1.0) or None for auto
            key_splines: Bezier spline control points or None
            duration_ms: Total animation duration in milliseconds
            value_formatter: Formatter to convert values to lxml elements

        Returns:
            (tav_elements, needs_custom_namespace) tuple where:
            - tav_elements: List of <a:tav> lxml elements
            - needs_custom_namespace: True if svg2: namespace is used

        Example:
            >>> tav_list, needs_ns = builder.build_tav_list(
            ...     values=["0", "100"],
            ...     key_times=[0.0, 1.0],
            ...     key_splines=None,
            ...     duration_ms=1000,
            ...     value_formatter=format_numeric_value
            ... )
        """
        if not values:
            return ([], False)

        # Resolve keyframe times
        resolved_times = self.resolve_key_times(values, key_times)

        # Build TAV elements
        tav_elements: list[etree._Element] = []
        uses_custom_namespace = False
        splines = key_splines or []

        for index, (time_fraction, raw_value) in enumerate(zip(resolved_times, values)):
            # Compute time in milliseconds
            tm = int(round(max(0.0, min(1.0, time_fraction)) * duration_ms))

            # Format value
            value_elem = value_formatter(raw_value)

            # Compute metadata for this TAV
            metadata = self.compute_tav_metadata(
                index, resolved_times, duration_ms, splines
            )

            # Extract accel/decel
            accel = 0
            decel = 0
            if "svg2:accel" in metadata:
                accel = int(metadata["svg2:accel"])
            if "svg2:decel" in metadata:
                decel = int(metadata["svg2:decel"])

            # Build TAV element
            tav = self._xml.build_tav_element(
                tm=tm,
                value_elem=value_elem,
                accel=accel,
                decel=decel,
                metadata=metadata if metadata else None,
            )

            tav_elements.append(tav)

            # Check if custom namespace is used
            if metadata:
                uses_custom_namespace = True

        return (tav_elements, uses_custom_namespace)

    def resolve_key_times(
        self,
        values: Sequence[str],
        key_times: Sequence[float] | None,
    ) -> list[float]:
        """Resolve keyframe times (auto-distribute if not provided).

        If key_times is None or wrong length, auto-distributes keyframes
        evenly from 0.0 to 1.0.

        Args:
            values: Animation values (determines count)
            key_times: Explicit times (0.0-1.0) or None

        Returns:
            List of resolved keyframe times

        Example:
            >>> builder.resolve_key_times(["0", "50", "100"], None)
            [0.0, 0.5, 1.0]
            >>> builder.resolve_key_times(["0", "100"], [0.0, 1.0])
            [0.0, 1.0]
        """
        if not values:
            return []

        # If key_times provided and valid, use it
        if key_times is not None and len(key_times) == len(values):
            return list(key_times)

        # Otherwise, auto-distribute evenly
        steps = len(values) - 1
        if steps <= 0:
            return [0.0]

        return [index / steps for index in range(len(values))]

    def compute_tav_metadata(
        self,
        index: int,
        key_times: Sequence[float],
        duration_ms: int,
        splines: Sequence[list[float]],
    ) -> dict[str, str]:
        """Compute TAV metadata attributes (spline info, timing).

        Metadata is only generated for keyframes after the first (index > 0)
        when splines are present.

        Args:
            index: Keyframe index (0-based)
            key_times: Resolved keyframe times
            duration_ms: Total animation duration
            splines: Bezier spline control points

        Returns:
            Dictionary of metadata attributes (svg2:spline, svg2:accel, etc.)

        Example:
            >>> metadata = builder.compute_tav_metadata(
            ...     1, [0.0, 1.0], 1000, [[0.42, 0, 0.58, 1]]
            ... )
            >>> metadata["svg2:spline"]
            '0.4200,0.0000,0.5800,1.0000'
        """
        # No metadata for first keyframe or when no splines
        if index == 0 or not splines:
            return {}

        # Check bounds
        if index - 1 >= len(splines) or index >= len(key_times):
            return {}

        # Get spline for this segment (between index-1 and index)
        spline = splines[index - 1]

        # Compute acceleration/deceleration
        accel_val, decel_val = self._segment_accel_decel(spline)

        # Compute segment duration
        segment_duration = max(
            0,
            int(round((key_times[index] - key_times[index - 1]) * duration_ms)),
        )

        # Build metadata dictionary
        metadata: dict[str, str] = {}

        if accel_val > 0:
            metadata["svg2:accel"] = str(accel_val)
        if decel_val > 0:
            metadata["svg2:decel"] = str(decel_val)

        metadata["svg2:spline"] = self._format_spline(spline)
        metadata["svg2:segDur"] = str(segment_duration)

        return metadata

    # ------------------------------------------------------------------ #
    # Helper Methods                                                     #
    # ------------------------------------------------------------------ #

    def _segment_accel_decel(self, spline: list[float]) -> tuple[int, int]:
        """Extract acceleration/deceleration from spline control points.

        Uses the y-coordinates of the control points to estimate
        acceleration and deceleration percentages.

        Args:
            spline: Bezier control points [x1, y1, x2, y2]

        Returns:
            (accel, decel) tuple in percentage units (0-100000)

        Example:
            >>> builder._segment_accel_decel([0.42, 0, 0.58, 1])
            (0, 0)  # Linear-ish ease
        """
        if len(spline) != 4:
            return (0, 0)

        _, y1, _, y2 = spline

        # Clamp to 0.0-1.0 and convert to percentage
        accel = self._clamp_percentage(y1)
        decel = self._clamp_percentage(1.0 - y2)

        return (accel, decel)

    def _format_spline(self, spline: list[float]) -> str:
        """Format spline control points as comma-separated string.

        Args:
            spline: Control points [x1, y1, x2, y2]

        Returns:
            Formatted string like "0.4200,0.0000,0.5800,1.0000"

        Example:
            >>> builder._format_spline([0.42, 0, 0.58, 1])
            '0.4200,0.0000,0.5800,1.0000'
        """
        # Clamp each value to 0.0-1.0 and format with 4 decimals
        formatted = [
            "{0:.4f}".format(max(0.0, min(1.0, value)))
            for value in spline
        ]
        return ",".join(formatted)

    @staticmethod
    def _clamp_percentage(value: float) -> int:
        """Clamp value to 0.0-1.0 and convert to percentage (0-100000).

        Args:
            value: Value to clamp (typically 0.0-1.0)

        Returns:
            Percentage in PowerPoint units (0-100000)

        Example:
            >>> TAVBuilder._clamp_percentage(0.5)
            50000
            >>> TAVBuilder._clamp_percentage(1.5)
            100000
        """
        clamped = max(0.0, min(1.0, value))
        return int(round(clamped * 100000))
