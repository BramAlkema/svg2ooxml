from __future__ import annotations

from svg2ooxml.core.export.animation_processor import _sampled_motion_group_key
from svg2ooxml.core.export.variant_expansion import _animation_group_key
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
)


def _animation(
    *,
    repeat_duration: float | None = None,
    target_attribute: str = "x",
) -> AnimationDefinition:
    return AnimationDefinition(
        element_id="shape",
        animation_type=AnimationType.ANIMATE,
        target_attribute=target_attribute,
        values=["0", "10"],
        timing=AnimationTiming(duration=1.0, repeat_duration=repeat_duration),
    )


def test_variant_group_key_distinguishes_repeat_duration() -> None:
    alias_map: dict[str, tuple[str, ...]] = {}

    assert _animation_group_key(
        _animation(repeat_duration=1.0),
        alias_map,
    ) != _animation_group_key(
        _animation(repeat_duration=2.0),
        alias_map,
    )


def test_sampled_motion_group_key_distinguishes_repeat_duration() -> None:
    alias_map: dict[str, tuple[str, ...]] = {}

    assert _sampled_motion_group_key(
        _animation(repeat_duration=1.0),
        alias_map,
    ) != _sampled_motion_group_key(
        _animation(repeat_duration=2.0),
        alias_map,
    )
