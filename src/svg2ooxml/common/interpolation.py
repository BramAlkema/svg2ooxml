"""Interpolation helpers used by the animation sampler."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from svg2ooxml.color import Color, parse_color
from svg2ooxml.ir.animation import TransformType


@dataclass(slots=True)
class InterpolationResult:
    value: str
    progress: float
    easing_applied: bool = False


class ColorInterpolator:
    """Interpolate colours in RGB space."""

    def interpolate(self, from_value: str, to_value: str, progress: float) -> str:
        try:
            start = self._parse(from_value)
            end = self._parse(to_value)
        except ValueError:
            return from_value if progress < 0.5 else to_value

        if not start or not end:
            return from_value if progress < 0.5 else to_value

        r = _lerp(start.r, end.r, progress)
        g = _lerp(start.g, end.g, progress)
        b = _lerp(start.b, end.b, progress)
        a = _lerp(start.a, end.a, progress)
        return Color(r, g, b, a).to_hex(include_alpha=a < 0.999)

    def _parse(self, token: str | None) -> Color | None:
        if not token:
            return None
        colour = parse_color(token)
        if colour is None:
            raise ValueError("unknown colour")
        return colour


class NumericInterpolator:
    """Interpolate numeric values with unit awareness."""

    NUMBER_RE = re.compile(r"^([-+]?(?:\d+\.?\d*|\.\d+))(.*)$")

    def interpolate(self, from_value: str, to_value: str, progress: float) -> str:
        try:
            start_num, start_unit = self._parse(from_value)
            end_num, end_unit = self._parse(to_value)
        except ValueError:
            return from_value if progress < 0.5 else to_value

        if start_num is None or end_num is None:
            return from_value if progress < 0.5 else to_value

        if start_unit != end_unit:
            return from_value if progress < 0.5 else to_value

        interpolated = _lerp(start_num, end_num, progress)
        unit = start_unit or ""

        if unit:
            return _format_numeric(interpolated, unit, from_value, to_value)

        return _format_numeric(interpolated, "", from_value, to_value)

    def _parse(self, value: str) -> tuple[float | None, str | None]:
        if not value:
            return None, None
        match = self.NUMBER_RE.match(value.strip())
        if not match:
            raise ValueError("not numeric")
        number = float(match.group(1))
        unit = match.group(2).strip() or None
        return number, unit


class TransformInterpolator:
    """Interpolate transform parameters."""

    NUMBER_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)")

    def interpolate(
        self,
        from_transform: str,
        to_transform: str,
        progress: float,
        transform_type: TransformType,
    ) -> str:
        try:
            start = self._parse(from_transform)
            end = self._parse(to_transform)
        except ValueError:
            return from_transform if progress < 0.5 else to_transform

        if not start or not end or len(start) != len(end):
            return from_transform if progress < 0.5 else to_transform

        values = [_lerp(a, b, progress) for a, b in zip(start, end, strict=True)]
        return self._format(values, transform_type)

    def _parse(self, transform: str | None) -> list[float] | None:
        if not transform:
            return None
        numbers = self.NUMBER_RE.findall(transform)
        if not numbers:
            return None
        try:
            return [float(value) for value in numbers]
        except ValueError:
            raise ValueError("invalid transform values") from None

    def _format(self, values: Iterable[float], transform_type: TransformType) -> str:
        values = list(values)
        if transform_type == TransformType.TRANSLATE:
            return _format_transform("translate", values, {1, 2})
        if transform_type == TransformType.SCALE:
            return _format_transform("scale", values, {1, 2})
        if transform_type == TransformType.ROTATE:
            return _format_transform("rotate", values, {1, 3})
        if transform_type == TransformType.SKEWX:
            return _format_transform("skewX", values, {1})
        if transform_type == TransformType.SKEWY:
            return _format_transform("skewY", values, {1})
        if transform_type == TransformType.MATRIX:
            if len(values) == 6:
                formatted = ", ".join(f"{val:.6f}" for val in values)
                return f"matrix({formatted})"
            return " ".join(f"{val:.3f}" for val in values)
        return " ".join(f"{val:.3f}" for val in values)


class BezierEasing:
    """Evaluate cubic Bezier easing curves."""

    @staticmethod
    def evaluate(progress: float, control_points: list[float]) -> float:
        if len(control_points) != 4:
            return progress

        x1, y1, x2, y2 = control_points
        t = _solve_bezier(progress, x1, x2)
        return _cubic_bezier(t, y1, y2)


class InterpolationEngine:
    """Coordinate interpolation across attribute types."""

    def __init__(self) -> None:
        self._color = ColorInterpolator()
        self._numeric = NumericInterpolator()
        self._transform = TransformInterpolator()

    def interpolate_value(
        self,
        from_value: str,
        to_value: str,
        progress: float,
        attribute_name: str,
        *,
        transform_type: TransformType | None = None,
        easing: list[float] | None = None,
    ) -> InterpolationResult:
        eased_progress = progress
        easing_applied = False
        if easing and len(easing) == 4:
            eased_progress = BezierEasing.evaluate(progress, easing)
            easing_applied = True

        attribute_lower = attribute_name.lower()
        if attribute_lower in _COLOR_ATTRIBUTES:
            value = self._color.interpolate(from_value, to_value, eased_progress)
        elif transform_type:
            value = self._transform.interpolate(from_value, to_value, eased_progress, transform_type)
        elif attribute_lower in _NUMERIC_ATTRIBUTES:
            value = self._numeric.interpolate(from_value, to_value, eased_progress)
        else:
            value = from_value if eased_progress < 0.5 else to_value

        return InterpolationResult(value=value, progress=eased_progress, easing_applied=easing_applied)

    def interpolate_keyframes(
        self,
        values: list[str],
        key_times: list[float] | None,
        key_splines: list[list[float]] | None,
        progress: float,
        attribute_name: str,
        *,
        transform_type: TransformType | None = None,
    ) -> InterpolationResult:
        if not values:
            return InterpolationResult(value="", progress=progress)
        if len(values) == 1:
            return InterpolationResult(value=values[0], progress=progress)

        times = key_times if key_times and len(key_times) == len(values) else _uniform_times(len(values))

        for index in range(len(times) - 1):
            start = times[index]
            end = times[index + 1]
            if start <= progress <= end:
                segment_duration = end - start
                local_progress = 0.0 if segment_duration == 0 else (progress - start) / segment_duration
                easing = key_splines[index] if key_splines and index < len(key_splines) else None
                return self.interpolate_value(
                    values[index],
                    values[index + 1],
                    local_progress,
                    attribute_name,
                    transform_type=transform_type,
                    easing=easing,
                )

        if progress <= times[0]:
            return InterpolationResult(value=values[0], progress=progress)
        return InterpolationResult(value=values[-1], progress=progress)

    def get_supported_attributes(self) -> dict[str, str]:
        return {
            **{attribute: "color" for attribute in _COLOR_ATTRIBUTES},
            **{attribute: "numeric" for attribute in _NUMERIC_ATTRIBUTES},
            "transform": "transform",
        }


def _lerp(start: float, end: float, t: float) -> float:
    return start + (end - start) * t


def _format_numeric(value: float, unit: str, start: str, end: str) -> str:
    if unit:
        if "." in start or "." in end:
            return f"{value:.3f}{unit}".rstrip("0").rstrip(".")
        return f"{value:.0f}{unit}"
    if "." in start or "." in end:
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{value:.0f}"


def _format_transform(name: str, values: list[float], allowed_lengths: set[int]) -> str:
    if len(values) not in allowed_lengths:
        return " ".join(f"{val:.3f}" for val in values)
    formatted = ", ".join(f"{val:.3f}" for val in values)
    return f"{name}({formatted})"


def _uniform_times(count: int) -> list[float]:
    if count <= 1:
        return [0.0]
    return [index / (count - 1) for index in range(count)]


def _solve_bezier(target: float, x1: float, x2: float, *, precision: float = 1e-6) -> float:
    low, high = 0.0, 1.0
    for _ in range(50):
        mid = (low + high) / 2.0
        value = _cubic_bezier(mid, x1, x2)
        if abs(value - target) < precision:
            return mid
        if value < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _cubic_bezier(t: float, p1: float, p2: float) -> float:
    return 3 * (1 - t) * (1 - t) * t * p1 + 3 * (1 - t) * t * t * p2 + t * t * t


_COLOR_ATTRIBUTES = {
    "fill",
    "stroke",
    "stop-color",
    "flood-color",
    "lighting-color",
    "color",
    "background-color",
}

_NUMERIC_ATTRIBUTES = {
    "opacity",
    "fill-opacity",
    "stroke-opacity",
    "stroke-width",
    "r",
    "cx",
    "cy",
    "x",
    "y",
    "width",
    "height",
    "rx",
    "ry",
    "x1",
    "y1",
    "x2",
    "y2",
    "dx",
    "dy",
    "offset",
    "font-size",
}


__all__ = [
    "InterpolationEngine",
    "InterpolationResult",
    "ColorInterpolator",
    "NumericInterpolator",
    "TransformInterpolator",
    "BezierEasing",
]
