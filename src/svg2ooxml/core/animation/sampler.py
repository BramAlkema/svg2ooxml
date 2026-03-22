"""Timeline sampling utilities for animated SVG content."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from svg2ooxml.common.interpolation import InterpolationEngine
from svg2ooxml.ir.animation import AnimationDefinition, AnimationScene, CalcMode


@dataclass(slots=True)
class TimelineSamplingConfig:
    sample_rate: float = 30.0
    max_duration: float | None = None
    min_keyframes: int = 2
    max_keyframes: int = 100
    precision: float = 0.001
    optimize_static_periods: bool = True


class TimelineSampler:
    """Generate `AnimationScene` snapshots for a sequence of animations."""

    def __init__(self, config: TimelineSamplingConfig | None = None) -> None:
        self.config = config or TimelineSamplingConfig()
        self._interpolation = InterpolationEngine()
        self._conflict_resolver = _ConflictResolver(self._interpolation)
        self._optimizer = _SceneOptimizer(self.config.precision)

    def generate_scenes(
        self,
        animations: list[AnimationDefinition],
        *,
        target_duration: float | None = None,
    ) -> list[AnimationScene]:
        if not animations:
            return []

        duration = self._calculate_duration(animations, target_duration)
        samples = self._generate_time_samples(animations, duration)

        # Pre-compute grouping once (same for every timestamp)
        self._conflict_resolver.clear_cache()
        grouped = _group_by_element_and_attribute(animations)

        scenes: list[AnimationScene] = []
        for timestamp in samples:
            scene = self._generate_scene_at_time_fast(grouped, timestamp)
            if scene.element_states:
                scenes.append(scene)

        if self.config.optimize_static_periods:
            scenes = self._optimizer.optimize(scenes)

        return scenes

    def generate_keyframe_summary(self, animations: list[AnimationDefinition]) -> dict[str, Any]:
        summary = {
            "total_animations": len(animations),
            "elements": set(),
            "attributes": set(),
            "duration": 0.0,
            "keyframe_density": 0.0,
            "complexity_factors": [],
        }

        for animation in animations:
            summary["elements"].add(animation.element_id)
            summary["attributes"].add(animation.target_attribute)

            end_time = animation.timing.get_end_time()
            if end_time != float("inf"):
                summary["duration"] = max(summary["duration"], end_time)

            if animation.key_splines:
                summary["complexity_factors"].append("Custom easing curves")
            if animation.key_times:
                summary["complexity_factors"].append("Custom timing")
            if len(animation.values) > 2:
                summary["complexity_factors"].append("Multi-keyframe animation")

        if summary["duration"] > 0 and summary["total_animations"] > 0:
            summary["keyframe_density"] = summary["total_animations"] * 2 / summary["duration"]

        summary["elements"] = list(summary["elements"])
        summary["attributes"] = list(summary["attributes"])
        summary["unique_elements"] = len(summary["elements"])
        summary["unique_attributes"] = len(summary["attributes"])
        return summary

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #
    def _calculate_duration(
        self,
        animations: list[AnimationDefinition],
        target_duration: float | None,
    ) -> float:
        if target_duration is not None:
            return target_duration

        max_end = 0.0
        for animation in animations:
            end_time = animation.timing.get_end_time()
            if end_time != float("inf"):
                max_end = max(max_end, end_time)

        if max_end > 0:
            return max_end

        return 5.0

    def _generate_time_samples(
        self,
        animations: list[AnimationDefinition],
        duration: float,
    ) -> list[float]:
        samples = {0.0, duration}

        for animation in animations:
            samples.add(animation.timing.begin)
            end_time = animation.timing.get_end_time()
            if end_time != float("inf") and end_time <= duration:
                samples.add(end_time)

            if animation.key_times:
                for key_time in animation.key_times:
                    absolute = animation.timing.begin + key_time * animation.timing.duration
                    if absolute <= duration:
                        samples.add(absolute)

        interval = 1.0 / max(self.config.sample_rate, 1.0)
        current = 0.0
        while current <= duration:
            samples.add(current)
            current += interval

        sorted_samples = sorted(samples)
        filtered = [sorted_samples[0]]
        for value in sorted_samples[1:]:
            if value - filtered[-1] >= self.config.precision:
                filtered.append(value)
        return filtered

    def _generate_scene_at_time(
        self,
        animations: list[AnimationDefinition],
        timestamp: float,
    ) -> AnimationScene:
        grouped = _group_by_element_and_attribute(animations)
        return self._generate_scene_at_time_fast(grouped, timestamp)

    def _generate_scene_at_time_fast(
        self,
        grouped: dict[tuple[str, str], list[AnimationDefinition]],
        timestamp: float,
    ) -> AnimationScene:
        scene = AnimationScene(time=timestamp)

        for (element_id, attribute), attribute_animations in grouped.items():
            value = self._conflict_resolver.resolve(attribute_animations, timestamp, attribute)
            if value:
                scene.set_element_property(element_id, attribute, value)

        return scene


class _ConflictResolver:
    """Resolve competing animations targeting the same attribute."""

    def __init__(self, interpolation: InterpolationEngine) -> None:
        self._interpolation = interpolation
        self._value_cache: dict[tuple[int, float], str | None] = {}

    def clear_cache(self) -> None:
        self._value_cache.clear()

    def resolve(
        self,
        animations: list[AnimationDefinition],
        time: float,
        attribute: str,
    ) -> str | None:
        # Fast path: single animation (most common case)
        if len(animations) == 1:
            anim = animations[0]
            if anim.timing.is_active_at_time(time):
                return self._calculate_value(anim, time)
            return None

        active = [a for a in animations if a.timing.is_active_at_time(time)]
        if not active:
            return None

        if len(active) == 1:
            return self._calculate_value(active[0], time)

        base_value = None
        additive_values: list[str] = []

        for animation in sorted(active, key=lambda anim: anim.timing.begin):
            value = self._calculate_value(animation, time)
            if value is None:
                continue
            if animation.additive == "replace" or base_value is None:
                base_value = value
            elif animation.additive == "sum":
                additive_values.append(value)

        if base_value is None:
            return None

        if not additive_values:
            return base_value

        if attribute.lower() in _SUMMABLE_ATTRIBUTES:
            return _sum_numeric_values(base_value, additive_values)
        return additive_values[-1]

    def _calculate_value(self, animation: AnimationDefinition, time: float) -> str | None:
        cache_key = (id(animation), time)
        cached = self._value_cache.get(cache_key)
        if cached is not None:
            return cached

        if not animation.timing.is_active_at_time(time):
            return None

        local_time = animation.timing.get_local_time(time)
        if animation.calc_mode == CalcMode.DISCRETE:
            value = self._calculate_discrete(animation, local_time)
        else:
            result = self._interpolation.interpolate_keyframes(
                animation.values,
                animation.key_times,
                animation.key_splines,
                local_time,
                animation.target_attribute,
                transform_type=animation.transform_type,
            )
            value = result.value

        self._value_cache[cache_key] = value
        return value

    def _calculate_discrete(self, animation: AnimationDefinition, progress: float) -> str | None:
        if not animation.values:
            return None

        if len(animation.values) == 1:
            return animation.values[0]

        if animation.key_times and len(animation.key_times) == len(animation.values):
            times = animation.key_times
        else:
            times = [index / (len(animation.values) - 1) for index in range(len(animation.values))]

        for index, key_time in enumerate(times):
            if progress <= key_time:
                return animation.values[index]
        return animation.values[-1]


class _SceneOptimizer:
    """Remove redundant scenes while preserving animation fidelity."""

    def __init__(self, precision: float) -> None:
        self.precision = precision

    def optimize(self, scenes: list[AnimationScene]) -> list[AnimationScene]:
        if len(scenes) <= 2:
            return scenes

        optimized = [scenes[0]]
        for index in range(1, len(scenes) - 1):
            previous = optimized[-1]
            current = scenes[index]
            nxt = scenes[index + 1]
            if self._is_significant_change(previous, current, nxt):
                optimized.append(current)

        optimized.append(scenes[-1])
        return optimized

    def _is_significant_change(
        self,
        previous: AnimationScene,
        current: AnimationScene,
        nxt: AnimationScene,
    ) -> bool:
        prev_elements = set(previous.element_states.keys())
        current_elements = set(current.element_states.keys())
        next_elements = set(nxt.element_states.keys())

        if current_elements != prev_elements or current_elements != next_elements:
            return True

        for element_id in current_elements:
            prev_props = previous.element_states.get(element_id, {})
            curr_props = current.element_states.get(element_id, {})
            next_props = nxt.element_states.get(element_id, {})

            if set(curr_props.keys()) != set(prev_props.keys()):
                return True

            for prop, curr_value in curr_props.items():
                prev_value = prev_props.get(prop)
                next_value = next_props.get(prop)

                if _is_non_linear_change(prev_value, curr_value, next_value):
                    return True

        return False


def _group_by_element(animations: list[AnimationDefinition]) -> dict[str, list[AnimationDefinition]]:
    groups: dict[str, list[AnimationDefinition]] = {}
    for animation in animations:
        groups.setdefault(animation.element_id, []).append(animation)
    return groups


def _group_by_attribute(animations: list[AnimationDefinition]) -> dict[str, list[AnimationDefinition]]:
    groups: dict[str, list[AnimationDefinition]] = {}
    for animation in animations:
        groups.setdefault(animation.target_attribute, []).append(animation)
    return groups


def _group_by_element_and_attribute(
    animations: list[AnimationDefinition],
) -> dict[tuple[str, str], list[AnimationDefinition]]:
    """Group animations by (element_id, attribute) in a single pass."""
    groups: dict[tuple[str, str], list[AnimationDefinition]] = {}
    for animation in animations:
        key = (animation.element_id, animation.target_attribute)
        groups.setdefault(key, []).append(animation)
    return groups


def _is_non_linear_change(
    previous: str | None,
    current: str | None,
    nxt: str | None,
) -> bool:
    if previous is None or current is None or nxt is None:
        return True

    try:
        prev_num = float(_extract_numeric(previous))
        curr_num = float(_extract_numeric(current))
        next_num = float(_extract_numeric(nxt))

        expected = (prev_num + next_num) / 2.0
        tolerance = abs(next_num - prev_num) * 0.1
        return abs(curr_num - expected) > tolerance
    except (ValueError, TypeError):
        return current != previous or current != nxt


def _extract_numeric(value: str) -> float:
    match = _NUMERIC_VALUE_RE.match(value.strip())
    if not match:
        raise ValueError("non-numeric value")
    return float(match.group(1))


def _sum_numeric_values(base_value: str, additive_values: list[str]) -> str:
    try:
        base_num, base_unit = _parse_numeric_with_unit(base_value)
    except ValueError:
        return base_value

    total = base_num
    for candidate in additive_values:
        try:
            number, unit = _parse_numeric_with_unit(candidate)
        except ValueError:
            continue
        if unit == base_unit or not unit:
            total += number

    formatted = f"{total:.3f}"
    if base_unit:
        formatted += base_unit
    return formatted.rstrip("0").rstrip(".")


def _parse_numeric_with_unit(value: str) -> tuple[float, str | None]:
    match = _NUMERIC_VALUE_RE.match(value.strip())
    if not match:
        raise ValueError("not numeric")
    number = float(match.group(1))
    unit = match.group(2).strip() or None
    return number, unit


_NUMERIC_VALUE_RE = re.compile(r"^([-+]?(?:\d+\.?\d*|\.\d+))(.*)$")

_SUMMABLE_ATTRIBUTES = {
    "opacity",
    "fill-opacity",
    "stroke-opacity",
    "stroke-width",
    "font-size",
    "r",
    "rx",
    "ry",
    "x",
    "y",
    "cx",
    "cy",
    "width",
    "height",
    "dx",
    "dy",
    "offset",
}


__all__ = ["TimelineSampler", "TimelineSamplingConfig"]
