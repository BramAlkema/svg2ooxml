"""Animation keyframe and definition models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from svg2ooxml.ir.animation_enums import (
    AnimationType,
    CalcMode,
    TransformType,
)
from svg2ooxml.ir.animation_timing import AnimationTiming, BeginTrigger


@dataclass(slots=True)
class AnimationKeyframe:
    """Normalized keyframe entry with easing data."""

    time: float
    values: list[str]
    easing: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.time <= 1.0:
            raise ValueError(f"Keyframe time must be between 0 and 1, got {self.time}")
        if not self.values:
            raise ValueError("Keyframe must have at least one value")


@dataclass(slots=True)
class AnimationDefinition:
    """Complete description of a single SVG animation."""

    element_id: str
    animation_type: AnimationType
    target_attribute: str
    values: list[str]
    timing: AnimationTiming
    animation_id: str | None = None
    attribute_type: str | None = None
    from_value: str | None = None
    to_value: str | None = None
    by_value: str | None = None
    key_times: list[float] | None = None
    key_points: list[float] | None = None
    key_splines: list[list[float]] | None = None
    calc_mode: CalcMode = CalcMode.LINEAR
    transform_type: TransformType | None = None
    additive: str = "replace"
    accumulate: str = "none"
    motion_rotate: str | None = None
    element_center_px: tuple[float, float] | None = None
    element_heading_deg: float | None = None
    motion_space_matrix: tuple[float, float, float, float, float, float] | None = None
    element_motion_offset_px: tuple[float, float] | None = None
    motion_viewport_px: tuple[float, float] | None = None
    restart: str | None = None
    min_ms: int | None = None
    max_ms: int | None = None
    raw_attributes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.element_id:
            raise ValueError("Element ID is required")
        if not self.target_attribute:
            raise ValueError("Target attribute is required")
        if not self.values:
            raise ValueError("Animation must have at least one value")

        self._validate_key_times()
        self._validate_key_points()
        self._validate_key_splines()

    def _validate_key_times(self) -> None:
        if not self.key_times:
            return
        is_motion_with_path = (
            self.animation_type == AnimationType.ANIMATE_MOTION and len(self.values) == 1
        )
        if not is_motion_with_path and len(self.key_times) != len(self.values):
            raise ValueError("key_times length must match values length")
        if not all(0.0 <= t <= 1.0 for t in self.key_times):
            raise ValueError("All key_times must be between 0 and 1")
        if self.key_times != sorted(self.key_times):
            raise ValueError("key_times must be in ascending order")

    def _validate_key_points(self) -> None:
        if not self.key_points:
            return
        if self.animation_type != AnimationType.ANIMATE_MOTION:
            raise ValueError("key_points only valid with animateMotion")
        if not all(0.0 <= value <= 1.0 for value in self.key_points):
            raise ValueError("All key_points must be between 0 and 1")

    def _validate_key_splines(self) -> None:
        if not self.key_splines:
            return
        calc_mode_value = _calc_mode_value(self.calc_mode)
        if calc_mode_value != "spline":
            raise ValueError("key_splines only valid with spline calc_mode")
        expected_count = self._expected_key_spline_count()
        if len(self.key_splines) != expected_count:
            raise ValueError(
                f"Expected {expected_count} key_splines, got {len(self.key_splines)}"
            )
        for spline in self.key_splines:
            if len(spline) != 4:
                raise ValueError("Each key_spline must have exactly 4 values")
            if not all(0.0 <= value <= 1.0 for value in spline):
                raise ValueError("All key_spline values must be between 0 and 1")

    def _expected_key_spline_count(self) -> int:
        is_motion_with_path = (
            self.animation_type == AnimationType.ANIMATE_MOTION and len(self.values) == 1
        )
        if is_motion_with_path and self.key_times:
            return len(self.key_times) - 1
        return len(self.values) - 1

    def get_keyframes(self) -> list[AnimationKeyframe]:
        """Expand the animation into keyframes."""
        if self.key_times:
            keyframes: list[AnimationKeyframe] = []
            for index, (time, value) in enumerate(
                zip(self.key_times, self.values, strict=True)
            ):
                easing = self._keyframe_easing(index)
                keyframes.append(
                    AnimationKeyframe(time=time, values=[value], easing=easing)
                )
            return keyframes

        if len(self.values) == 1:
            return [AnimationKeyframe(time=0.0, values=self.values)]

        keyframes = []
        for index, value in enumerate(self.values):
            time = index / (len(self.values) - 1)
            easing = self._keyframe_easing(index)
            keyframes.append(AnimationKeyframe(time=time, values=[value], easing=easing))
        return keyframes

    def _keyframe_easing(self, index: int) -> str | None:
        if self.key_splines and index < len(self.key_splines):
            spline = self.key_splines[index]
            return f"cubic-bezier({spline[0]}, {spline[1]}, {spline[2]}, {spline[3]})"
        return None

    def is_transform_animation(self) -> bool:
        return self.animation_type == AnimationType.ANIMATE_TRANSFORM

    def is_motion_animation(self) -> bool:
        return self.animation_type == AnimationType.ANIMATE_MOTION

    def is_color_animation(self) -> bool:
        if self.animation_type == AnimationType.ANIMATE_COLOR:
            return True
        if self.animation_type == AnimationType.ANIMATE and self.target_attribute in {
            "fill",
            "stroke",
            "stop-color",
        }:
            return True
        return False

    @property
    def duration_ms(self) -> int:
        """Return duration in milliseconds (for compatibility with handlers)."""
        duration = self.timing.duration
        if duration == float("inf") or duration > 1e9:
            return 2_147_483_647
        return int(duration * 1000)

    @property
    def begin_ms(self) -> int:
        """Return begin time in milliseconds (for compatibility with handlers)."""
        return int(self.timing.begin * 1000)

    @property
    def fill_mode(self) -> str:
        """Return fill_mode as string (for compatibility with handlers)."""
        return self.timing.fill_mode.value

    @property
    def repeat_count(self) -> int | str:
        """Return repeat_count (for compatibility with handlers)."""
        return self.timing.repeat_count

    @property
    def repeat_duration_ms(self) -> int | None:
        """Return repeat_duration in milliseconds (for compatibility with handlers)."""
        if self.timing.repeat_duration is None:
            return None
        return int(self.timing.repeat_duration * 1000)

    @property
    def begin_triggers(self) -> list[BeginTrigger] | None:
        """Return parsed begin triggers (for compatibility with handlers)."""
        return self.timing.begin_triggers

    @property
    def end_triggers(self) -> list[BeginTrigger] | None:
        """Return parsed end triggers (for compatibility with handlers)."""
        return self.timing.end_triggers

    @property
    def is_motion(self) -> bool:
        """Return True if this is a motion animation (for compatibility with handlers)."""
        return self.is_motion_animation()

    def get_value_at_time(self, time: float) -> Any:
        """Return an interpolated value for the supplied timestamp."""
        if time < self.timing.begin:
            return self.values[0] if self.values else None

        duration = self.timing.duration
        if time >= self.timing.begin + duration:
            return self.values[-1] if self.values else None

        relative_time = (time - self.timing.begin) / duration
        calc_mode_value = _calc_mode_value(self.calc_mode)
        if (calc_mode_value == "spline" and self.key_splines) or calc_mode_value == "discrete":
            relative_time = self._apply_easing(relative_time)

        return self._interpolate_value(relative_time)

    def _apply_easing(self, t: float) -> float:
        calc_mode_value = _calc_mode_value(self.calc_mode)

        if calc_mode_value == "linear":
            return t
        if calc_mode_value == "discrete":
            if not self.key_times:
                return 0.0 if t < 0.5 else 1.0
            for index, key_time in enumerate(self.key_times[1:], 1):
                if t <= key_time:
                    return self.key_times[index - 1]
            return 1.0
        if calc_mode_value == "spline" and self.key_splines:
            return self._apply_bezier_easing(t)
        return t

    def _apply_bezier_easing(self, t: float) -> float:
        if not self.key_splines or not self.key_times:
            return t

        for segment_index in range(len(self.key_times) - 1):
            if t <= self.key_times[segment_index + 1]:
                segment_start = self.key_times[segment_index]
                segment_end = self.key_times[segment_index + 1]
                segment_t = (t - segment_start) / (segment_end - segment_start)

                if segment_index < len(self.key_splines):
                    spline = self.key_splines[segment_index]
                    return self._cubic_bezier(
                        segment_t, spline[0], spline[1], spline[2], spline[3]
                    )
        return t

    @staticmethod
    def _cubic_bezier(t: float, x1: float, y1: float, x2: float, y2: float) -> float:
        return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t**2 * y2 + t**3

    def _interpolate_value(self, t: float) -> Any:
        if not self.values:
            return None
        if len(self.values) == 1:
            return self.values[0]

        if self.key_times:
            for index in range(len(self.key_times) - 1):
                if t <= self.key_times[index + 1]:
                    start_val = (
                        self.values[index] if index < len(self.values) else self.values[-1]
                    )
                    end_val = (
                        self.values[index + 1]
                        if index + 1 < len(self.values)
                        else self.values[-1]
                    )
                    segment_t = (t - self.key_times[index]) / (
                        self.key_times[index + 1] - self.key_times[index]
                    )
                    return self._lerp_values(start=start_val, end=end_val, t=segment_t)
        else:
            scaled_t = t * (len(self.values) - 1)
            index = int(scaled_t)
            fraction = scaled_t - index
            if index >= len(self.values) - 1:
                return self.values[-1]
            return self._lerp_values(
                start=self.values[index],
                end=self.values[index + 1],
                t=fraction,
            )

        return self.values[-1]

    @staticmethod
    def _lerp_values(start: Any, end: Any, t: float) -> Any:
        try:
            start_num = float(start)
            end_num = float(end)
            return start_num + (end_num - start_num) * t
        except (ValueError, TypeError):
            return start if t < 0.5 else end


def _calc_mode_value(calc_mode: CalcMode | str) -> str:
    return calc_mode.value if isinstance(calc_mode, CalcMode) else str(calc_mode)


__all__ = ["AnimationDefinition", "AnimationKeyframe"]
