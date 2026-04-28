"""Grouping keys for animation variant rewrites."""

from __future__ import annotations

from typing import Any

from svg2ooxml.core.export.animation_predicates import _timing_group_key
from svg2ooxml.ir.animation import AnimationDefinition, CalcMode


def _animation_group_key(
    animation: AnimationDefinition,
    alias_map: dict[str, tuple[str, ...]],
) -> tuple[Any, ...]:
    return (
        alias_map.get(animation.element_id, (animation.element_id,)),
        *_timing_group_key(animation.timing),
        animation.additive,
        animation.accumulate,
        animation.calc_mode.value
        if isinstance(animation.calc_mode, CalcMode)
        else str(animation.calc_mode),
        animation.restart,
        animation.min_ms,
        animation.max_ms,
    )


__all__ = ["_animation_group_key"]
