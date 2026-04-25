from __future__ import annotations

from svg2ooxml.core.animation.sampler import TimelineSampler, TimelineSamplingConfig
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    CalcMode,
)


def _animation(
    *,
    element_id: str = "shape",
    attribute: str = "opacity",
    values: list[str],
    begin: float = 0.0,
    duration: float = 1.0,
    additive: str = "replace",
    calc_mode: CalcMode = CalcMode.LINEAR,
) -> AnimationDefinition:
    return AnimationDefinition(
        element_id=element_id,
        animation_type=AnimationType.ANIMATE,
        target_attribute=attribute,
        values=values,
        timing=AnimationTiming(begin=begin, duration=duration),
        additive=additive,
        calc_mode=calc_mode,
    )


def test_sampler_generates_scenes_for_simple_animation() -> None:
    sampler = TimelineSampler()
    animation = _animation(values=["0", "1"], duration=2.0)

    scenes = sampler.generate_scenes([animation])

    assert scenes
    first = scenes[0]
    assert first.time == 0.0
    assert first.get_element_property("shape", "opacity") in {"0", "0.0"}

    assert any(scene.get_element_property("shape", "opacity") == "1" for scene in scenes)


def test_sampler_additive_conflict_resolution() -> None:
    sampler = TimelineSampler(TimelineSamplingConfig(sample_rate=10.0))
    base = _animation(values=["0", "1"], duration=1.0)
    additive = _animation(values=["0", "1"], duration=1.0, additive="sum")

    scenes = sampler.generate_scenes([base, additive])

    values = [scene.get_element_property("shape", "opacity") for scene in scenes]
    assert "2" in values


def test_sampler_respects_configured_max_duration() -> None:
    sampler = TimelineSampler(
        TimelineSamplingConfig(sample_rate=10.0, max_duration=0.5, optimize_static_periods=False)
    )
    animation = _animation(values=["0", "1"], duration=2.0)

    scenes = sampler.generate_scenes([animation])

    assert scenes
    assert max(scene.time for scene in scenes) <= 0.5


def test_sampler_discrete_mode_respects_keyframes() -> None:
    sampler = TimelineSampler(TimelineSamplingConfig(sample_rate=2.0))
    animation = AnimationDefinition(
        element_id="shape",
        animation_type=AnimationType.ANIMATE,
        target_attribute="opacity",
        values=["0", "1", "0"],
        timing=AnimationTiming(duration=1.0),
        calc_mode=CalcMode.DISCRETE,
    )

    scenes = sampler.generate_scenes([animation])
    values = [scene.get_element_property("shape", "opacity") for scene in scenes]
    assert "1" in values
    assert values.count("0") >= 1


def test_sampler_discrete_mode_holds_value_until_next_key_time() -> None:
    sampler = TimelineSampler(
        TimelineSamplingConfig(sample_rate=4.0, optimize_static_periods=False)
    )
    animation = AnimationDefinition(
        element_id="shape",
        animation_type=AnimationType.ANIMATE,
        target_attribute="opacity",
        values=["0", "1", "2"],
        timing=AnimationTiming(duration=1.0),
        calc_mode=CalcMode.DISCRETE,
        key_times=[0.0, 0.4, 1.0],
    )

    scenes = sampler.generate_scenes([animation])
    at_quarter = next(scene for scene in scenes if abs(scene.time - 0.25) < 1e-9)
    at_boundary = next(scene for scene in scenes if abs(scene.time - 0.4) < 1e-9)

    assert at_quarter.get_element_property("shape", "opacity") == "0"
    assert at_boundary.get_element_property("shape", "opacity") == "1"
