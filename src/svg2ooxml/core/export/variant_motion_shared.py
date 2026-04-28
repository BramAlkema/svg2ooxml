"""Shared helpers for animation variant motion rewrites."""

from __future__ import annotations

from collections.abc import Sequence

from svg2ooxml.core.export.motion_path_sampling import _format_motion_delta
from svg2ooxml.ir.animation import AnimationDefinition

AnimationReplacement = tuple[Sequence[AnimationDefinition], set[int]]


def _motion_delta_path(dx: float, dy: float) -> str:
    return f"M 0 0 L {_format_motion_delta(dx)} {_format_motion_delta(dy)} E"


def _apply_index_replacements(
    animations: Sequence[AnimationDefinition],
    replacements: dict[int, AnimationReplacement],
) -> list[AnimationDefinition]:
    rewritten: list[AnimationDefinition] = []
    consumed: set[int] = set()
    for index, animation in enumerate(animations):
        if index in consumed:
            continue
        replacement = replacements.get(index)
        if replacement is not None:
            rewritten.extend(replacement[0])
            consumed.update(replacement[1])
            continue
        rewritten.append(animation)
    return rewritten


__all__ = [
    "AnimationReplacement",
    "_apply_index_replacements",
    "_motion_delta_path",
]
