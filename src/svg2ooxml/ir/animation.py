"""Intermediate animation data structures used across the svg2ooxml pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AnimationType(Enum):
    """SVG animation element types."""

    ANIMATE = "animate"
    ANIMATE_TRANSFORM = "animateTransform"
    ANIMATE_COLOR = "animateColor"
    ANIMATE_MOTION = "animateMotion"
    SET = "set"


class FillMode(Enum):
    """Animation fill behaviour after playback."""

    REMOVE = "remove"
    FREEZE = "freeze"


class TransformType(Enum):
    """Supported transform animation types."""

    TRANSLATE = "translate"
    SCALE = "scale"
    ROTATE = "rotate"
    SKEWX = "skewX"
    SKEWY = "skewY"
    MATRIX = "matrix"


class CalcMode(Enum):
    """Supported SMIL calculation modes."""

    LINEAR = "linear"
    DISCRETE = "discrete"
    PACED = "paced"
    SPLINE = "spline"


class BeginTriggerType(Enum):
    """Supported SMIL begin trigger categories."""

    TIME_OFFSET = "time_offset"
    CLICK = "click"
    ELEMENT_BEGIN = "element_begin"
    ELEMENT_END = "element_end"
    INDEFINITE = "indefinite"


@dataclass(slots=True)
class BeginTrigger:
    """Structured begin trigger extracted from SMIL begin expressions."""

    trigger_type: BeginTriggerType
    delay_seconds: float = 0.0
    target_element_id: str | None = None


@dataclass(slots=True)
class AnimationTiming:
    """Timing definition for a single animation."""

    begin: float = 0.0
    duration: float = 1.0
    repeat_count: int | str = 1
    fill_mode: FillMode = FillMode.REMOVE
    begin_triggers: list[BeginTrigger] | None = None

    def get_end_time(self) -> float:
        """Return the absolute end time for an animation."""
        if self.repeat_count == "indefinite":
            return float("inf")

        try:
            count = int(self.repeat_count)
            return self.begin + (self.duration * count)
        except (ValueError, TypeError):
            return self.begin + self.duration

    def is_active_at_time(self, time: float) -> bool:
        """Return True when the animation is active at the supplied time."""
        if time < self.begin:
            return False

        end_time = self.get_end_time()
        if end_time == float("inf"):
            return True

        return time <= end_time

    def get_local_time(self, global_time: float) -> float:
        """Map a global timestamp to the animation's 0-1 progress space."""
        if global_time < self.begin:
            return 0.0

        local_time = global_time - self.begin
        if self.repeat_count == "indefinite":
            return (local_time % self.duration) / self.duration

        try:
            count = int(self.repeat_count)
            total_duration = self.duration * count
            if local_time >= total_duration:
                return 1.0 if self.fill_mode == FillMode.FREEZE else 0.0

            cycle_time = local_time % self.duration
            return cycle_time / self.duration
        except (ValueError, TypeError):
            if local_time >= self.duration:
                return 1.0 if self.fill_mode == FillMode.FREEZE else 0.0
            return local_time / self.duration


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
    key_times: list[float] | None = None
    key_splines: list[list[float]] | None = None
    calc_mode: CalcMode = CalcMode.LINEAR
    transform_type: TransformType | None = None
    additive: str = "replace"
    accumulate: str = "none"
    motion_rotate: str | None = None
    element_center_px: tuple[float, float] | None = None
    restart: str | None = None  # "always", "whenNotActive", "never"
    min_ms: int | None = None
    max_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.element_id:
            raise ValueError("Element ID is required")
        if not self.target_attribute:
            raise ValueError("Target attribute is required")
        if not self.values:
            raise ValueError("Animation must have at least one value")

        if self.key_times:
            is_motion_with_path = (
                self.animation_type == AnimationType.ANIMATE_MOTION
                and len(self.values) == 1
            )
            if not is_motion_with_path and len(self.key_times) != len(self.values):
                raise ValueError("key_times length must match values length")
            if not all(0.0 <= t <= 1.0 for t in self.key_times):
                raise ValueError("All key_times must be between 0 and 1")
            if self.key_times != sorted(self.key_times):
                raise ValueError("key_times must be in ascending order")

        if self.key_splines:
            calc_mode_value = self.calc_mode.value if isinstance(self.calc_mode, CalcMode) else self.calc_mode
            if calc_mode_value != "spline":
                raise ValueError("key_splines only valid with spline calc_mode")
            expected_count = len(self.values) - 1
            if len(self.key_splines) != expected_count:
                raise ValueError(f"Expected {expected_count} key_splines, got {len(self.key_splines)}")
            for spline in self.key_splines:
                if len(spline) != 4:
                    raise ValueError("Each key_spline must have exactly 4 values")
                if not all(0.0 <= v <= 1.0 for v in spline):
                    raise ValueError("All key_spline values must be between 0 and 1")

    def get_keyframes(self) -> list[AnimationKeyframe]:
        """Expand the animation into keyframes."""
        if self.key_times:
            keyframes: list[AnimationKeyframe] = []
            for index, (time, value) in enumerate(zip(self.key_times, self.values, strict=True)):
                easing = None
                if self.key_splines and index < len(self.key_splines):
                    spline = self.key_splines[index]
                    easing = f"cubic-bezier({spline[0]}, {spline[1]}, {spline[2]}, {spline[3]})"
                keyframes.append(AnimationKeyframe(time=time, values=[value], easing=easing))
            return keyframes

        if len(self.values) == 1:
            return [AnimationKeyframe(time=0.0, values=self.values)]

        keyframes = []
        for index, value in enumerate(self.values):
            time = index / (len(self.values) - 1)
            easing = None
            if self.key_splines and index < len(self.key_splines):
                spline = self.key_splines[index]
                easing = f"cubic-bezier({spline[0]}, {spline[1]}, {spline[2]}, {spline[3]})"
            keyframes.append(AnimationKeyframe(time=time, values=[value], easing=easing))
        return keyframes

    def is_transform_animation(self) -> bool:
        return self.animation_type == AnimationType.ANIMATE_TRANSFORM

    def is_motion_animation(self) -> bool:
        return self.animation_type == AnimationType.ANIMATE_MOTION

    def is_color_animation(self) -> bool:
        if self.animation_type == AnimationType.ANIMATE_COLOR:
            return True
        if self.animation_type == AnimationType.ANIMATE and self.target_attribute in {"fill", "stroke", "stop-color"}:
            return True
        return False

    @property
    def duration_ms(self) -> int:
        """Return duration in milliseconds (for compatibility with handlers)."""
        dur = self.timing.duration
        if dur == float("inf") or dur > 1e9:
            return 2_147_483_647  # max 32-bit signed int (~24 days)
        return int(dur * 1000)

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
        # This is optional - return None by default
        return None

    @property
    def begin_triggers(self) -> list[BeginTrigger] | None:
        """Return parsed begin triggers (for compatibility with handlers)."""
        return self.timing.begin_triggers

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
        calc_mode_value = self.calc_mode.value if isinstance(self.calc_mode, CalcMode) else self.calc_mode
        if (calc_mode_value == "spline" and self.key_splines) or calc_mode_value == "discrete":
            relative_time = self._apply_easing(relative_time)

        return self._interpolate_value(relative_time)

    def _apply_easing(self, t: float) -> float:
        calc_mode_value = self.calc_mode.value if isinstance(self.calc_mode, CalcMode) else self.calc_mode

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
                    return self._cubic_bezier(segment_t, spline[0], spline[1], spline[2], spline[3])
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
                    start_val = self.values[index] if index < len(self.values) else self.values[-1]
                    end_val = self.values[index + 1] if index + 1 < len(self.values) else self.values[-1]
                    segment_t = (t - self.key_times[index]) / (self.key_times[index + 1] - self.key_times[index])
                    return self._lerp_values(start=start_val, end=end_val, t=segment_t)
        else:
            scaled_t = t * (len(self.values) - 1)
            index = int(scaled_t)
            fraction = scaled_t - index
            if index >= len(self.values) - 1:
                return self.values[-1]
            return self._lerp_values(start=self.values[index], end=self.values[index + 1], t=fraction)

        return self.values[-1]

    @staticmethod
    def _lerp_values(start: Any, end: Any, t: float) -> Any:
        try:
            start_num = float(start)
            end_num = float(end)
            return start_num + (end_num - start_num) * t
        except (ValueError, TypeError):
            return start if t < 0.5 else end


@dataclass(slots=True)
class AnimationScene:
    """Snapshot of all animated element states at a specific time."""

    time: float
    element_states: dict[str, dict[str, str]] = field(default_factory=dict)

    def set_element_property(self, element_id: str, property_name: str, value: str) -> None:
        state = self.element_states.setdefault(element_id, {})
        state[property_name] = value

    def get_element_property(self, element_id: str, property_name: str) -> str | None:
        return self.element_states.get(element_id, {}).get(property_name)

    def get_all_animated_elements(self) -> list[str]:
        return list(self.element_states.keys())

    def merge_scene(self, other: AnimationScene) -> None:
        for element_id, properties in other.element_states.items():
            state = self.element_states.setdefault(element_id, {})
            state.update(properties)


def format_transform_string(transform_type: TransformType, values: list[float]) -> str:
    """Format numeric transform arguments into an SVG transform string."""
    if transform_type == TransformType.TRANSLATE:
        if len(values) == 1:
            return f"translate({values[0]})"
        if len(values) == 2:
            return f"translate({values[0]}, {values[1]})"
        raise ValueError("translate requires 1 or 2 values")

    if transform_type == TransformType.SCALE:
        if len(values) == 1:
            return f"scale({values[0]})"
        if len(values) == 2:
            return f"scale({values[0]}, {values[1]})"
        raise ValueError("scale requires 1 or 2 values")

    if transform_type == TransformType.ROTATE:
        if len(values) == 1:
            return f"rotate({values[0]})"
        if len(values) == 3:
            return f"rotate({values[0]}, {values[1]}, {values[2]})"
        raise ValueError("rotate requires 1 or 3 values")

    if transform_type == TransformType.SKEWX:
        if len(values) == 1:
            return f"skewX({values[0]})"
        raise ValueError("skewX requires 1 value")

    if transform_type == TransformType.SKEWY:
        if len(values) == 1:
            return f"skewY({values[0]})"
        raise ValueError("skewY requires 1 value")

    if transform_type == TransformType.MATRIX:
        if len(values) == 6:
            return f"matrix({', '.join(map(str, values))})"
        raise ValueError("matrix requires 6 values")

    raise ValueError(f"Unknown transform type: {transform_type}")


class AnimationComplexity(Enum):
    """High level buckets for animation complexity analysis."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


@dataclass(slots=True)
class AnimationSummary:
    """Roll-up statistics describing the animations found in an SVG."""

    total_animations: int = 0
    complexity: AnimationComplexity = AnimationComplexity.SIMPLE
    duration: float = 0.0
    has_transforms: bool = False
    has_motion_paths: bool = False
    has_color_animations: bool = False
    has_easing: bool = False
    has_sequences: bool = False
    element_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def add_warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def calculate_complexity(self) -> None:
        score = 0
        score += min(self.total_animations, 10)

        if self.has_transforms:
            score += 5
        if self.has_motion_paths:
            score += 8
        if self.has_color_animations:
            score += 3
        if self.has_easing:
            score += 4
        if self.has_sequences:
            score += 6

        if self.duration > 10:
            score += 3
        elif self.duration > 5:
            score += 1

        if self.element_count > 10:
            score += 4
        elif self.element_count > 5:
            score += 2

        if score <= 5:
            self.complexity = AnimationComplexity.SIMPLE
        elif score <= 15:
            self.complexity = AnimationComplexity.MODERATE
        elif score <= 25:
            self.complexity = AnimationComplexity.COMPLEX
        else:
            self.complexity = AnimationComplexity.VERY_COMPLEX


__all__ = [
    "BeginTrigger",
    "BeginTriggerType",
    "AnimationComplexity",
    "AnimationDefinition",
    "AnimationKeyframe",
    "AnimationScene",
    "AnimationSummary",
    "AnimationTiming",
    "AnimationType",
    "CalcMode",
    "FillMode",
    "TransformType",
    "format_transform_string",
]
