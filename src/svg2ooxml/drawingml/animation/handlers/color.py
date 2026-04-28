"""Color animation handler.

Generates PowerPoint color timing XML for fill, stroke, stop-color, etc.
Simple tweens use ``<p:animClr>``, while multi-keyframe sequences are split
into explicit segments because ``animClr`` cannot carry a ``tavLst``.
"""

from __future__ import annotations

from lxml import etree

from svg2ooxml.drawingml.animation.constants import (
    COLOR_ATTRIBUTE_NAME_MAP,
    COLOR_ATTRIBUTES,
)
from svg2ooxml.drawingml.animation.handlers.base import AnimationHandler
from svg2ooxml.ir.animation import AnimationDefinition, AnimationType

from .color_elements import ColorElementMixin
from .color_oracle import ColorOracleMixin
from .color_segments import ColorSegmentMixin

__all__ = ["ColorAnimationHandler"]


class ColorAnimationHandler(
    ColorOracleMixin,
    ColorSegmentMixin,
    ColorElementMixin,
    AnimationHandler,
):
    """Handler for color animations (fill, stroke, stop-color, etc.)."""

    def can_handle(self, animation: AnimationDefinition) -> bool:
        if animation.animation_type not in {
            AnimationType.ANIMATE,
            AnimationType.ANIMATE_COLOR,
        }:
            return False
        return animation.target_attribute in COLOR_ATTRIBUTES

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element | None:
        """Build ``<p:par>`` containing ``<p:animClr>`` with from/to colors."""
        ppt_attribute = self._map_color_attribute(animation.target_attribute)

        if self._should_use_color_pulse(animation, ppt_attribute):
            return self._build_color_pulse_animation(
                animation,
                par_id,
                behavior_id,
            )

        if self._should_use_simple_text_color_oracle(animation, ppt_attribute):
            return self._build_simple_text_color_animation(
                animation,
                par_id,
                behavior_id,
            )

        if self._should_segment(animation):
            return self._build_segmented_color_animation(
                animation,
                par_id,
                behavior_id,
                ppt_attribute,
            )

        if self._should_use_oracle_template(animation, ppt_attribute):
            return self._build_oracle_template_color_animation(
                animation,
                par_id,
                behavior_id,
                ppt_attribute,
            )

        anim_clr = self._build_anim_clr_element(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            ppt_attribute=ppt_attribute,
            from_color=animation.values[0],
            to_color=animation.values[-1],
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=anim_clr,
            preset_id=7,
            preset_class="emph",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
        )

    def _map_color_attribute(self, attribute: str) -> str:
        """Map SVG color attribute to PowerPoint attribute name."""
        return COLOR_ATTRIBUTE_NAME_MAP.get(attribute, "fill.color")
