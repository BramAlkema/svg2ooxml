"""Opacity animation handler.

Generates PowerPoint ``<p:animEffect>`` elements with fade filter for
opacity, fill-opacity, and stroke-opacity animations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import p_elem, p_sub
from svg2ooxml.ir.animation import AnimationType, CalcMode

from ..constants import FADE_ATTRIBUTES
from ..value_formatters import format_numeric_value
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
        """Build opacity animation using fade or generic property animation."""
        if self._should_use_property_animation(animation):
            return self._build_property_animation(animation, par_id, behavior_id)

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

    def _build_property_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element:
        anim = p_elem("anim")
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            attr_name_list=[self._map_opacity_attribute(animation.target_attribute)],
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim.append(cBhvr)

        values = [self._processor.parse_opacity(value) for value in animation.values]
        key_times = animation.key_times
        if animation.calc_mode == CalcMode.DISCRETE and (len(values) > 1 or key_times):
            tav_elements = self._tav.build_discrete_tav_list(
                values=values,
                key_times=key_times,
                value_formatter=format_numeric_value,
            )
        else:
            tav_elements, _ = self._tav.build_tav_list(
                values=values,
                key_times=key_times,
                key_splines=animation.key_splines,
                duration_ms=animation.duration_ms,
                value_formatter=format_numeric_value,
            )
        anim.append(self._xml.build_tav_list_container(tav_elements))

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=anim,
            preset_id=None,
            preset_class="emph",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
        )

    def _compute_target_opacity(self, animation: AnimationDefinition) -> str:
        """Compute target opacity value for fade effect."""
        if animation.values:
            return self._processor.parse_opacity(animation.values[-1])
        default = "1" if animation.fill_mode == "freeze" else "0"
        return self._processor.parse_opacity(default)

    @staticmethod
    def _map_opacity_attribute(attribute: str) -> str:
        return "style.opacity"

    def _should_use_property_animation(self, animation: AnimationDefinition) -> bool:
        if animation.target_attribute != "opacity":
            return True
        if len(animation.values) > 2 or animation.key_times:
            return True
        if animation.repeat_count not in (None, 1, "1"):
            return True
        if not animation.values:
            return False
        try:
            start_opacity = float(animation.values[0])
        except (TypeError, ValueError):
            start_opacity = 1.0
        if start_opacity > 0.0:
            return True
        return False
