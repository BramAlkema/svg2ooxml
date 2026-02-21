"""Color animation handler.

Generates PowerPoint ``<p:animClr>`` elements with from/to color values
and optional keyframes for fill, stroke, stop-color, etc. animations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import a_sub, p_elem, p_sub
from svg2ooxml.ir.animation import AnimationType, CalcMode

from ..constants import COLOR_ATTRIBUTE_NAME_MAP, COLOR_ATTRIBUTES
from ..value_formatters import format_color_value
from .base import AnimationHandler

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["ColorAnimationHandler"]


class ColorAnimationHandler(AnimationHandler):
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
        from_color = self._processor.parse_color(animation.values[0])
        to_color = self._processor.parse_color(animation.values[-1])
        ppt_attribute = self._map_color_attribute(animation.target_attribute)

        # Build <p:animClr> — clrSpc and dir are required by ECMA-376
        anim_clr = p_elem("animClr", clrSpc="rgb", dir="cw")

        # Behavior core with attribute name list
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            attr_name_list=[ppt_attribute],
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim_clr.append(cBhvr)

        # <p:from><a:srgbClr val="..."/></p:from>
        from_elem = p_sub(anim_clr, "from")
        a_sub(from_elem, "srgbClr", val=from_color)

        # <p:to><a:srgbClr val="..."/></p:to>
        to_elem = p_sub(anim_clr, "to")
        a_sub(to_elem, "srgbClr", val=to_color)

        # Open XML schema for animClr does not allow tavLst; keep from/to only.

        # Wrap in <p:par>
        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=anim_clr,
            preset_id=7,
            preset_class="emph",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
        )

    def _map_color_attribute(self, attribute: str) -> str:
        """Map SVG color attribute to PowerPoint attribute name."""
        return COLOR_ATTRIBUTE_NAME_MAP.get(attribute, "fillClr")

    def _build_color_tav_list(
        self,
        animation: AnimationDefinition,
    ) -> list[etree._Element]:
        """Build TAV list for multi-keyframe color animations.

        Only builds TAV list if more than 2 values or explicit key_times.
        """
        values = animation.values
        if not values:
            return []

        if animation.calc_mode == CalcMode.DISCRETE and (len(values) > 1 or animation.key_times):
            return self._tav.build_discrete_tav_list(
                values=values,
                key_times=animation.key_times,
                value_formatter=format_color_value,
            )

        if len(values) <= 2 and not animation.key_times:
            return []

        tav_elements, _ = self._tav.build_tav_list(
            values=values,
            key_times=animation.key_times,
            key_splines=animation.key_splines,
            duration_ms=animation.duration_ms,
            value_formatter=format_color_value,
        )

        return tav_elements
