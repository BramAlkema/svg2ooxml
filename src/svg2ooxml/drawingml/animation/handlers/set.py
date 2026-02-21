"""Set animation handler.

Generates PowerPoint ``<p:set>`` elements for discrete attribute changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import a_sub, p_sub
from svg2ooxml.ir.animation import AnimationType

from ..constants import ATTRIBUTE_NAME_MAP, COLOR_ATTRIBUTE_NAME_MAP, COLOR_ATTRIBUTES
from .base import AnimationHandler

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["SetAnimationHandler"]


class SetAnimationHandler(AnimationHandler):
    """Handler for set animations (discrete attribute changes)."""

    def can_handle(self, animation: AnimationDefinition) -> bool:
        return animation.animation_type == AnimationType.SET

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element | None:
        """Build ``<p:par>`` containing ``<p:set>`` for this animation."""
        if not animation.values:
            return None

        target_value = animation.values[-1]
        target_attribute = animation.target_attribute
        ppt_attribute = self._map_attribute_name(target_attribute)
        is_color = target_attribute in COLOR_ATTRIBUTES

        # Build <p:set> with behavior core and target value
        set_elem = self._xml.build_set_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            ppt_attribute=ppt_attribute,
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )

        # Build <p:to> with value
        to_elem = p_sub(set_elem, "to")
        if is_color:
            hex_color = self._processor.parse_color(target_value)
            clr_val = p_sub(to_elem, "clrVal")
            a_sub(clr_val, "srgbClr", val=hex_color)
        else:
            normalized = self._processor.normalize_numeric_value(
                ppt_attribute, target_value, unit_converter=self._units
            )
            p_sub(to_elem, "strVal", val=normalized)

        # Wrap in <p:par> container — use appropriate preset for type
        if is_color:
            preset_id, preset_class = 7, "emph"  # Change Fill Color
        else:
            preset_id, preset_class = 1, "entr"  # Appear

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=set_elem,
            preset_id=preset_id,
            preset_class=preset_class,
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
        )

    @staticmethod
    def _map_attribute_name(attribute: str) -> str:
        """Map SVG attribute name to PowerPoint attribute name."""
        if attribute in COLOR_ATTRIBUTES:
            return COLOR_ATTRIBUTE_NAME_MAP.get(attribute, attribute)
        return ATTRIBUTE_NAME_MAP.get(attribute, attribute)
