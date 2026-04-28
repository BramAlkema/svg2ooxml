"""lxml-based XML builders for PowerPoint animation timing."""

from __future__ import annotations

from lxml import etree

from .constants import SVG2_ANIMATION_NS
from .xml_behaviors import AnimationBehaviorXMLMixin
from .xml_containers import AnimationContainerXMLMixin
from .xml_timing_overrides import AnimationTimingOverrideMixin
from .xml_values import AnimationValueXMLMixin

# Register custom namespace for stable prefix in serialization.
etree.register_namespace("svg2", SVG2_ANIMATION_NS)

__all__ = ["AnimationXMLBuilder"]


class AnimationXMLBuilder(
    AnimationValueXMLMixin,
    AnimationContainerXMLMixin,
    AnimationTimingOverrideMixin,
    AnimationBehaviorXMLMixin,
):
    """Build PowerPoint animation timing XML using lxml."""
