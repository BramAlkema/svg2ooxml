"""Opacity animation handler.

Generates PowerPoint ``<p:animEffect>`` elements with fade filter for
opacity, fill-opacity, and stroke-opacity animations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.animation.constants import FADE_ATTRIBUTES
from svg2ooxml.drawingml.animation.handlers.base import AnimationHandler
from svg2ooxml.drawingml.animation.oracle import default_oracle
from svg2ooxml.drawingml.animation.timing_utils import sample_spline_keyframes
from svg2ooxml.drawingml.animation.value_formatters import format_numeric_value
from svg2ooxml.drawingml.xml_builder import p_elem, p_sub
from svg2ooxml.ir.animation import AnimationType, BeginTriggerType, CalcMode

if TYPE_CHECKING:
    from svg2ooxml.drawingml.animation.native_fragment import NativeFragment
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
    ) -> NativeFragment | None:
        """Build opacity animation using fade or generic property animation."""
        if self._is_symmetric_opacity_pulse(animation):
            return self._native_fragment(
                self._build_transparency_pulse_animation(
                    animation, par_id, behavior_id
                ),
                source="builder",
                strategy="opacity-pulse-transparency-effect",
                oracle_family="emph/transparency",
            )

        fade_effect = self._build_authored_fade_effect(
            animation, par_id, behavior_id
        )
        if fade_effect is not None:
            par, oracle_slot = fade_effect
            return self._native_fragment(
                par,
                source="oracle",
                strategy="opacity-authored-fade",
                oracle_slot=oracle_slot,
            )

        # For partial opacity (not 0→1 or 1→0 fades), route through the
        # verified emph/transparency oracle slot. The <p:anim> on
        # style.opacity via TAV is a dead path (anim-style-opacity-tavlst).
        if (
            animation.target_attribute == "opacity"
            and len(animation.values) >= 2
            and animation.repeat_count in (None, 1, "1")
            and not animation.end_triggers
            and self._authored_fade_begin_triggers_are_simple(animation)
            and animation.calc_mode not in {CalcMode.DISCRETE, CalcMode.SPLINE}
            and not animation.key_splines
        ):
            target_opacity = self._processor.parse_opacity(animation.values[-1])
            return self._native_fragment(
                default_oracle().instantiate(
                    "emph/transparency",
                    shape_id=animation.element_id,
                    par_id=par_id,
                    duration_ms=animation.duration_ms,
                    delay_ms=animation.begin_ms,
                    SET_BEHAVIOR_ID=behavior_id,
                    EFFECT_BEHAVIOR_ID=behavior_id * 10 + 1,
                    TARGET_OPACITY=target_opacity,
                    INNER_FILL=(
                        "hold" if animation.fill_mode == "freeze" else "remove"
                    ),
                ),
                source="oracle",
                strategy="opacity-partial-transparency",
                oracle_slot="emph/transparency",
            )

        return self._native_fragment(
            self._build_property_animation(animation, par_id, behavior_id),
            source="builder",
            strategy="opacity-property-animation",
            target_attribute=animation.target_attribute,
        )

    def _build_authored_fade_effect(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> tuple[etree._Element, str] | None:
        if animation.calc_mode in {CalcMode.DISCRETE, CalcMode.SPLINE}:
            return None
        if animation.key_splines:
            return None
        if not self._authored_fade_begin_triggers_are_simple(animation):
            return None
        fade_params = self._resolve_authored_fade(animation)
        if fade_params is None:
            return None

        transition, _ = fade_params
        if transition == "in":
            return (
                default_oracle().instantiate(
                    "entr/fade",
                    shape_id=animation.element_id,
                    par_id=par_id,
                    duration_ms=animation.duration_ms,
                    delay_ms=animation.begin_ms,
                    SET_BEHAVIOR_ID=behavior_id,
                    EFFECT_BEHAVIOR_ID=behavior_id * 10 + 1,
                ),
                "entr/fade",
            )
        return (
            default_oracle().instantiate(
                "exit/fade",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=animation.duration_ms,
                delay_ms=animation.begin_ms,
                SET_BEHAVIOR_ID=behavior_id,
                EFFECT_BEHAVIOR_ID=behavior_id * 10 + 1,
                SET_DELAY_MS=max(1, animation.duration_ms - 1),
            ),
            "exit/fade",
        )

    @staticmethod
    def _authored_fade_begin_triggers_are_simple(
        animation: AnimationDefinition,
    ) -> bool:
        """Only route through the oracle template for trivial start conditions.

        The static template only emits a single ``<p:cond delay=.../>``, so any
        non-time-offset begin trigger (event, element-begin reference, click)
        must fall through to the property-animation code path which can inject
        a full ``<p:stCondLst>`` via ``_append_begin_conditions``.
        """
        triggers = animation.begin_triggers
        if not triggers:
            return True
        if len(triggers) > 1:
            return False
        return triggers[0].trigger_type == BeginTriggerType.TIME_OFFSET

    def _build_transparency_pulse_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element:
        half_duration_ms = max(1, int(round(animation.duration_ms / 2.0)))
        base_opacity = self._format_effect_opacity(animation.values[0])
        peak_opacity = self._format_effect_opacity(animation.values[1])
        effect_behavior_id = behavior_id * 10 + 1

        outer_par = p_elem("par")
        outer_ctn = p_sub(
            outer_par,
            "cTn",
            id=str(par_id),
            dur=str(animation.duration_ms),
            fill="hold",
            nodeType="clickEffect",
            grpId=str(par_id),
            presetID="9",
            presetClass="emph",
            presetSubtype="0",
        )
        self._apply_repeat_count(outer_ctn, animation.repeat_count)

        st_cond_lst = p_sub(outer_ctn, "stCondLst")
        if animation.begin_triggers:
            self._xml._append_begin_conditions(
                st_cond_lst=st_cond_lst,
                begin_triggers=animation.begin_triggers,
                fallback_delay_ms=animation.begin_ms,
                default_target_shape=animation.element_id,
            )
        else:
            p_sub(st_cond_lst, "cond", delay=str(animation.begin_ms))

        child_tn_lst = p_sub(outer_ctn, "childTnLst")

        set_elem = p_sub(child_tn_lst, "set")
        set_cbhvr = p_sub(set_elem, "cBhvr")
        p_sub(
            set_cbhvr,
            "cTn",
            id=str(behavior_id),
            dur=str(animation.duration_ms),
            fill="hold",
            nodeType="withEffect",
        )
        tgt_el = p_sub(set_cbhvr, "tgtEl")
        p_sub(tgt_el, "spTgt", spid=animation.element_id)
        attr_name_lst = p_sub(set_cbhvr, "attrNameLst")
        attr_name = p_sub(attr_name_lst, "attrName")
        attr_name.text = "style.opacity"
        to_elem = p_sub(set_elem, "to")
        p_sub(to_elem, "strVal", val=base_opacity)

        anim_effect = p_sub(
            child_tn_lst,
            "animEffect",
            filter="image",
            prLst=f"opacity: {peak_opacity}",
        )
        effect_cbhvr = p_sub(anim_effect, "cBhvr", rctx="IE")
        p_sub(
            effect_cbhvr,
            "cTn",
            id=str(effect_behavior_id),
            dur=str(half_duration_ms),
            fill="remove",
            nodeType="withEffect",
            autoRev="1",
        )
        effect_tgt = p_sub(effect_cbhvr, "tgtEl")
        p_sub(effect_tgt, "spTgt", spid=animation.element_id)

        return outer_par

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
        elif animation.calc_mode == CalcMode.SPLINE and animation.key_splines:
            sampled_values, sampled_times = sample_spline_keyframes(
                values=values,
                key_times=key_times,
                key_splines=animation.key_splines,
                attribute_name=animation.target_attribute,
            )
            tav_elements, _ = self._tav.build_tav_list(
                values=sampled_values,
                key_times=sampled_times,
                key_splines=None,
                duration_ms=animation.duration_ms,
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
            effect_group_id=par_id,
        )

    def _compute_target_opacity(self, animation: AnimationDefinition) -> str:
        """Compute target opacity value for fade effect."""
        if animation.values:
            return self._processor.parse_opacity(animation.values[-1])
        default = "1" if animation.fill_mode == "freeze" else "0"
        return self._processor.parse_opacity(default)

    def _resolve_authored_fade(
        self, animation: AnimationDefinition
    ) -> tuple[str, str] | None:
        if animation.target_attribute != "opacity":
            return None
        if len(animation.values) != 2 or animation.key_times:
            return None
        if animation.repeat_count not in (None, 1, "1"):
            return None

        start_opacity = self._opacity_float(animation.values[0])
        end_opacity = self._opacity_float(animation.values[-1])
        if start_opacity <= 0.0 and end_opacity >= 0.999:
            return ("in", "entr")
        if end_opacity <= 0.0 and start_opacity >= 0.999:
            return ("out", "exit")

        return None

    @staticmethod
    def _map_opacity_attribute(attribute: str) -> str:
        return {
            "fill-opacity": "fill.opacity",
            "stroke-opacity": "stroke.opacity",
        }.get(attribute, "style.opacity")

    def _should_use_property_animation(self, animation: AnimationDefinition) -> bool:
        if animation.target_attribute != "opacity":
            return True
        if animation.calc_mode in {CalcMode.DISCRETE, CalcMode.SPLINE}:
            return True
        if animation.key_splines:
            return True
        if len(animation.values) > 2 or animation.key_times:
            return True
        if animation.repeat_count not in (None, 1, "1"):
            return True
        if not animation.values:
            return False
        if self._resolve_authored_fade(animation) is not None:
            return False
        try:
            start_opacity = float(animation.values[0])
        except (TypeError, ValueError):
            start_opacity = 1.0
        if start_opacity > 0.0:
            return True
        return False

    @staticmethod
    def _opacity_float(value: str) -> float:
        try:
            opacity = float(value)
        except (TypeError, ValueError):
            return 1.0
        if opacity > 1.0:
            opacity = opacity / 100.0
        return max(0.0, min(1.0, opacity))

    @classmethod
    def _format_effect_opacity(cls, value: str) -> str:
        opacity = cls._opacity_float(value)
        return f"{opacity:.4f}".rstrip("0").rstrip(".")

    @classmethod
    def _is_symmetric_opacity_pulse(cls, animation: AnimationDefinition) -> bool:
        if animation.target_attribute != "opacity":
            return False
        if len(animation.values) != 3:
            return False
        if animation.calc_mode == CalcMode.DISCRETE:
            return False
        if animation.key_splines:
            return False
        if animation.key_times and [round(t, 6) for t in animation.key_times] != [
            0.0,
            0.5,
            1.0,
        ]:
            return False
        start = cls._opacity_float(animation.values[0])
        peak = cls._opacity_float(animation.values[1])
        end = cls._opacity_float(animation.values[2])
        return abs(start - end) <= 1e-6 and abs(start - peak) > 1e-6

    @staticmethod
    def _apply_repeat_count(
        ctn: etree._Element,
        repeat_count: int | str | None,
    ) -> None:
        if repeat_count == "indefinite":
            ctn.set("repeatCount", "indefinite")
            return

        if repeat_count is None:
            return

        try:
            count = int(repeat_count)
        except (TypeError, ValueError):
            return

        if count > 1:
            ctn.set("repeatCount", str(count * 1000))
