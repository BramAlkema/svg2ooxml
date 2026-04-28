"""Animation enum definitions."""

from __future__ import annotations

from enum import Enum


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
    EVENT = "event"
    ELEMENT_BEGIN = "element_begin"
    ELEMENT_END = "element_end"
    ELEMENT_REPEAT = "element_repeat"
    ACCESS_KEY = "access_key"
    WALLCLOCK = "wallclock"
    INDEFINITE = "indefinite"


class AnimationComplexity(Enum):
    """High level buckets for animation complexity analysis."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


__all__ = [
    "AnimationComplexity",
    "AnimationType",
    "BeginTriggerType",
    "CalcMode",
    "FillMode",
    "TransformType",
]
