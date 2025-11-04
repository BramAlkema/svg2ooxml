"""Animation type handlers.

Each handler specializes in building XML for a specific animation type:
    - OpacityAnimationHandler: Opacity/fade animations
    - ColorAnimationHandler: Color animations
    - NumericAnimationHandler: Generic numeric properties
    - TransformAnimationHandler: Scale/rotate/translate
    - MotionAnimationHandler: Motion path animations
    - SetAnimationHandler: Set animations
"""

from __future__ import annotations

from .base import AnimationHandler, AnimationDefinition
from .opacity import OpacityAnimationHandler
from .color import ColorAnimationHandler
from .numeric import NumericAnimationHandler
from .transform import TransformAnimationHandler
from .motion import MotionAnimationHandler
from .set import SetAnimationHandler

# All handlers implemented
__all__ = [
    "AnimationHandler",  # Base class
    "AnimationDefinition",  # Protocol for animation data
    "OpacityAnimationHandler",
    "ColorAnimationHandler",
    "NumericAnimationHandler",
    "TransformAnimationHandler",
    "MotionAnimationHandler",
    "SetAnimationHandler",
]
