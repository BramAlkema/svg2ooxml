"""Shared constants and public parser wrapper types."""

from __future__ import annotations

from dataclasses import dataclass

from svg2ooxml.common.time import parse_time_value
from svg2ooxml.ir.animation import AnimationDefinition, AnimationType

ANIMATION_TAGS = (
    "animate",
    "animateTransform",
    "animateColor",
    "animateMotion",
    "set",
)

_ANIMATION_TYPE_BY_TAG = {
    "animate": AnimationType.ANIMATE,
    "animateTransform": AnimationType.ANIMATE_TRANSFORM,
    "animateColor": AnimationType.ANIMATE_COLOR,
    "animateMotion": AnimationType.ANIMATE_MOTION,
    "set": AnimationType.SET,
}


class SMILParsingError(Exception):
    """Raised when an animation element cannot be parsed."""


@dataclass(slots=True)
class ParsedAnimation:
    """Convenience wrapper for parser outputs."""

    definition: AnimationDefinition


def get_animation_type(tag_name: str) -> AnimationType | None:
    return _ANIMATION_TYPE_BY_TAG.get(tag_name)


def parse_optional_duration_ms(value: str | None) -> int | None:
    """Parse an optional SMIL duration to milliseconds, or None."""
    if not value or value == "indefinite":
        return None
    try:
        return int(round(parse_time_value(value) * 1000))
    except (ValueError, TypeError):
        return None


__all__ = [
    "ANIMATION_TAGS",
    "ParsedAnimation",
    "SMILParsingError",
    "get_animation_type",
    "parse_optional_duration_ms",
]
