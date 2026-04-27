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
from svg2ooxml.drawingml.xml_builder import a_sub, p_elem, p_sub
from svg2ooxml.ir.animation import AnimationDefinition, AnimationType

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["SetAnimationHandler"]

_VISIBILITY_EFFECT_ATTR = "svg2ooxml_visibility_effect"
_BLINK_EFFECT = "blink"
_NOOP_ANCHOR_EFFECT = "noop_anchor"


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

        if ppt_attribute == "style.fontWeight" and self._visibility_uses_oracle(animation):
            return default_oracle().instantiate(
                "emph/bold",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=animation.duration_ms,
                delay_ms=animation.begin_ms,
                BEHAVIOR_ID=behavior_id,
            )

        if ppt_attribute == "style.textDecorationUnderline" and self._visibility_uses_oracle(animation):
            return default_oracle().instantiate(
                "emph/underline",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=animation.duration_ms,
                delay_ms=animation.begin_ms,
                BEHAVIOR_ID=behavior_id,
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
        return AnimationHandler._simple_oracle_gate(animation)

    def _build_visibility_effect(
        self,
        *,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        target_value: str,
    ) -> etree._Element:
        if self._uses_visibility_noop_anchor(animation):
            return self._build_visibility_noop_anchor(
                animation=animation,
                par_id=par_id,
                behavior_id=behavior_id,
                target_value=target_value,
            )

        if self._uses_blink_oracle(animation):
            return default_oracle().instantiate(
                "emph/blink",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=max(1, animation.duration_ms),
                delay_ms=animation.begin_ms,
                BEHAVIOR_ID=behavior_id,
            )

        transition = "in" if target_value == "visible" else "out"
        preset_id = 1 if transition == "in" else 10
        preset_class = "entr" if transition == "in" else "exit"
        duration_ms = max(1, animation.duration_ms)
        effect_ctn_id = par_id * 10

        if transition == "in" and self._visibility_uses_oracle(animation):
            # Return the oracle effect par directly. The preset 1 Appear
            # template has no ``dur`` on its outer cTn, so the fill="hold"
            # visibility set persists for the rest of the slideshow. Wrapping
            # in ``build_delayed_child_par`` would re-introduce a bounded
            # outer ``dur`` and cause PowerPoint to revert the visibility
            # once the wrapper expires. The template's own ``<p:cond>``
            # carries the start delay instead.
            return default_oracle().instantiate(
                "entr/appear",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=duration_ms,
                delay_ms=animation.begin_ms,
                BEHAVIOR_ID=behavior_id,
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
        set_delay = 0 if transition == "in" else max(duration_ms - 1, 0)
        delayed_set = self._xml.build_delayed_child_par(
            par_id=behavior_id + 2,
            delay_ms=set_delay,
            duration_ms=1,
            child_element=set_elem,
        )
        to_elem = p_sub(set_elem, "to")
        p_sub(to_elem, "strVal", val=target_value)

        effect_par = self._xml.build_par_container_with_children_elem(
            par_id=effect_ctn_id,
            duration_ms=duration_ms,
            delay_ms=0,
            child_elements=[delayed_set, anim_effect],
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

    def _build_visibility_noop_anchor(
        self,
        *,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        target_value: str,
    ) -> etree._Element:
        set_elem = self._xml.build_set_elem(
            behavior_id=behavior_id,
            duration_ms=max(1, animation.duration_ms),
            target_shape=animation.element_id,
            ppt_attribute="style.visibility",
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        to_elem = p_sub(set_elem, "to")
        p_sub(to_elem, "strVal", val=target_value)
        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=max(1, animation.duration_ms),
            delay_ms=animation.begin_ms,
            child_element=set_elem,
            preset_id=1 if target_value == "visible" else 10,
            preset_class="entr" if target_value == "visible" else "exit",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
            repeat_count=animation.repeat_count,
        )

    @classmethod
    def _uses_blink_oracle(cls, animation: AnimationDefinition) -> bool:
        return (
            animation.raw_attributes.get(_VISIBILITY_EFFECT_ATTR) == _BLINK_EFFECT
            and cls._visibility_uses_oracle(animation)
        )

    @staticmethod
    def _uses_visibility_noop_anchor(animation: AnimationDefinition) -> bool:
        return animation.raw_attributes.get(_VISIBILITY_EFFECT_ATTR) == _NOOP_ANCHOR_EFFECT
