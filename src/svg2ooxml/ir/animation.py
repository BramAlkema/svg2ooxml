"""Intermediate animation data structures used across the svg2ooxml pipeline."""

from __future__ import annotations

from svg2ooxml.ir.animation_definition import (
    AnimationDefinition as AnimationDefinition,
)
from svg2ooxml.ir.animation_definition import (
    AnimationKeyframe as AnimationKeyframe,
)
from svg2ooxml.ir.animation_enums import (
    AnimationComplexity as AnimationComplexity,
)
from svg2ooxml.ir.animation_enums import (
    AnimationType as AnimationType,
)
from svg2ooxml.ir.animation_enums import (
    BeginTriggerType as BeginTriggerType,
)
from svg2ooxml.ir.animation_enums import (
    CalcMode as CalcMode,
)
from svg2ooxml.ir.animation_enums import (
    FillMode as FillMode,
)
from svg2ooxml.ir.animation_enums import (
    TransformType as TransformType,
)
from svg2ooxml.ir.animation_scene import AnimationScene as AnimationScene
from svg2ooxml.ir.animation_summary import AnimationSummary as AnimationSummary
from svg2ooxml.ir.animation_timing import (
    AnimationTiming as AnimationTiming,
)
from svg2ooxml.ir.animation_timing import (
    BeginTrigger as BeginTrigger,
)
from svg2ooxml.ir.animation_transform import (
    format_transform_string as format_transform_string,
)

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
