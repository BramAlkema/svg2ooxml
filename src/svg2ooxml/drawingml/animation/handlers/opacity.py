"""Opacity animation handler.

Generates PowerPoint ``<p:animEffect>`` elements with fade filter for
opacity, fill-opacity, and stroke-opacity animations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import p_elem, p_sub
from svg2ooxml.ir.animation import AnimationType

from ..constants import FADE_ATTRIBUTES
from .base import AnimationHandler

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["OpacityAnimationHandler"]


class OpacityAnimationHandler(AnimationHandler):
    """Handler for opacity/fade animations."""

    def can_handle(self, animation: AnimationDefinition) -> bool:
        if animation.animation_type != AnimationType.ANIMATE:
            return False
        return animation.target_attribute in FADE_ATTRIBUTES

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element | None:
        """Build ``<p:par>`` containing ``<p:animEffect>`` with fade filter."""
        target_opacity = self._compute_target_opacity(animation)

        # Build <p:animEffect>
        anim_effect = p_elem("animEffect")

        # Behavior core
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim_effect.append(cBhvr)

        # Filter (ECMA-376: animEffect allows only cBhvr + progress)
        anim_effect.set("transition", "in")
        anim_effect.set("filter", f"fade(opacity={target_opacity})")

        # Wrap in <p:par>
        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=anim_effect,
            preset_id=10,
            preset_class="entr",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
        )

    def _compute_target_opacity(self, animation: AnimationDefinition) -> str:
        """Compute target opacity value for fade effect."""
        if animation.values:
            return self._processor.parse_opacity(animation.values[-1])
        default = "1" if animation.fill_mode == "freeze" else "0"
        return self._processor.parse_opacity(default)
