"""Classify SVG animation IR by editable native PowerPoint strategy."""

from __future__ import annotations

from svg2ooxml.ir.animation import AnimationDefinition

from .native_match_constraints import apply_native_match_constraints
from .native_match_rules import classify_native_match_core
from .native_match_types import NativeAnimationMatch, NativeAnimationMatchLevel

__all__ = [
    "NativeAnimationMatch",
    "NativeAnimationMatchLevel",
    "classify_native_animation",
]


def classify_native_animation(animation: AnimationDefinition) -> NativeAnimationMatch:
    """Return the best declared native PowerPoint match for an animation."""
    match = classify_native_match_core(animation)
    apply_native_match_constraints(match, animation)
    return match.freeze()
