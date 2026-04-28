"""Types for sampled center-motion composition."""

from __future__ import annotations

from dataclasses import dataclass

from svg2ooxml.ir.animation import AnimationDefinition

AnimationMember = tuple[int, AnimationDefinition]


@dataclass(frozen=True)
class _SampledCenterMotionComposition:
    replacement_index: int
    consumed_indices: set[int]
    replacement_animation: AnimationDefinition
    updated_indices: dict[int, AnimationDefinition]
    start_center: tuple[float, float]
    element_id: str


__all__ = ["AnimationMember", "_SampledCenterMotionComposition"]
