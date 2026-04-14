"""Set animation handler.

Generates PowerPoint ``<p:set>`` elements for discrete attribute changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.animation.constants import (
    ATTRIBUTE_NAME_MAP,
    COLOR_ATTRIBUTE_NAME_MAP,
    COLOR_ATTRIBUTES,
)
from svg2ooxml.drawingml.animation.handlers.base import AnimationHandler
from svg2ooxml.drawingml.animation.oracle import default_oracle
from svg2ooxml.drawingml.xml_builder import NS_P, a_sub, p_elem, p_sub
from svg2ooxml.ir.animation import AnimationType, BeginTriggerType

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

        if ppt_attribute == "style.visibility":
            return self._build_visibility_effect(
                animation=animation,
                par_id=par_id,
                behavior_id=behavior_id,
                target_value=str(target_value).strip().lower(),
            )

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
            effect_group_id=par_id,
        )

    @staticmethod
    def _map_attribute_name(attribute: str) -> str:
        """Map SVG attribute name to PowerPoint attribute name."""
        if attribute in COLOR_ATTRIBUTES:
            return COLOR_ATTRIBUTE_NAME_MAP.get(attribute, attribute)
        return ATTRIBUTE_NAME_MAP.get(attribute, attribute)

    @staticmethod
    def _visibility_uses_oracle(animation: AnimationDefinition) -> bool:
        """Gate the ``entr/appear`` oracle path to simple start conditions.

        The template only emits a single time-offset ``<p:cond>`` and no
        additive / repeat modifiers. Anything more complex falls through to
        the imperative ``<p:animEffect>`` path so the full trigger grammar
        stays available.
        """
        if (animation.additive or "replace").lower() == "sum":
            return False
        if animation.repeat_count not in (None, 1, "1"):
            return False
        triggers = animation.begin_triggers
        if triggers:
            if len(triggers) > 1:
                return False
            if triggers[0].trigger_type != BeginTriggerType.TIME_OFFSET:
                return False
        return True

    def _build_visibility_effect(
        self,
        *,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        target_value: str,
    ) -> etree._Element:
        transition = "in" if target_value == "visible" else "out"
        preset_id = 1 if transition == "in" else 10
        preset_class = "entr" if transition == "in" else "exit"
        duration_ms = max(1, animation.duration_ms)
        effect_ctn_id = par_id * 10

        if transition == "in" and self._visibility_uses_oracle(animation):
            effect_par = default_oracle().instantiate(
                "entr/appear",
                shape_id=animation.element_id,
                par_id=effect_ctn_id,
                duration_ms=duration_ms,
                delay_ms=0,
                BEHAVIOR_ID=behavior_id,
            )
            return self._xml.build_delayed_child_par(
                par_id=par_id,
                delay_ms=animation.begin_ms,
                duration_ms=duration_ms,
                child_element=effect_par,
            )

        anim_effect = p_elem("animEffect")
        anim_effect.set("transition", transition)
        anim_effect.set("filter", "fade")
        anim_effect.append(
            self._xml.build_behavior_core_elem(
                behavior_id=behavior_id,
                duration_ms=duration_ms,
                target_shape=animation.element_id,
                additive=animation.additive,
                fill_mode=animation.fill_mode,
                repeat_count=animation.repeat_count,
            )
        )

        set_elem = self._xml.build_set_elem(
            behavior_id=behavior_id + 1,
            duration_ms=1,
            target_shape=animation.element_id,
            ppt_attribute="style.visibility",
            fill_mode="freeze",
            repeat_count=1,
        )
        cond = set_elem.find(f".//{{{NS_P}}}cond")
        if cond is not None:
            set_delay = 0 if transition == "in" else max(duration_ms - 1, 0)
            cond.set("delay", str(set_delay))
        to_elem = p_sub(set_elem, "to")
        p_sub(to_elem, "strVal", val=target_value)

        effect_par = self._xml.build_par_container_with_children_elem(
            par_id=effect_ctn_id,
            duration_ms=duration_ms,
            delay_ms=0,
            child_elements=[set_elem, anim_effect],
            preset_id=preset_id,
            preset_class=preset_class,
            preset_subtype=0,
            node_type="clickEffect",
            begin_triggers=None,
            default_target_shape=animation.element_id,
            effect_group_id=effect_ctn_id,
        )

        if animation.begin_triggers:
            return self._xml.build_par_container_with_children_elem(
                par_id=par_id,
                duration_ms=duration_ms,
                delay_ms=animation.begin_ms,
                child_elements=[effect_par],
                begin_triggers=animation.begin_triggers,
                default_target_shape=animation.element_id,
            )

        return self._xml.build_delayed_child_par(
            par_id=par_id,
            delay_ms=animation.begin_ms,
            duration_ms=duration_ms,
            child_element=effect_par,
        )
