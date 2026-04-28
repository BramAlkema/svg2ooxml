"""Oracle-template routing for color animations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.animation.handlers.base import AnimationHandler
from svg2ooxml.drawingml.animation.oracle import default_oracle
from svg2ooxml.drawingml.animation.timing_values import format_duration_ms
from svg2ooxml.drawingml.xml_builder import NS_P
from svg2ooxml.ir.animation import CalcMode

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition

_TEXT_TARGET_TAGS = frozenset({"text", "tspan", "textpath"})
_TEXT_COLOR_ATTRIBUTES = frozenset({"fill.color", "style.color"})


class ColorOracleMixin:
    """Oracle-template helpers used by ``ColorAnimationHandler``."""

    @staticmethod
    def _should_use_oracle_template(
        animation: AnimationDefinition,
        ppt_attribute: str,
    ) -> bool:
        if not AnimationHandler._simple_oracle_gate(animation):
            return False
        if ppt_attribute == "style.color":
            return False
        if ppt_attribute == "fill.color" and ColorOracleMixin._is_text_target(
            animation
        ):
            return False
        return True

    @staticmethod
    def _target_tag(animation: AnimationDefinition) -> str:
        return animation.raw_attributes.get("svg2ooxml_target_tag", "").strip().lower()

    @classmethod
    def _is_text_target(cls, animation: AnimationDefinition) -> bool:
        return cls._target_tag(animation) in _TEXT_TARGET_TAGS

    @classmethod
    def _uses_text_color_semantics(
        cls,
        animation: AnimationDefinition,
        ppt_attribute: str,
    ) -> bool:
        return (
            cls._is_text_target(animation) and ppt_attribute in _TEXT_COLOR_ATTRIBUTES
        )

    def _normalize_color_identity(self, value: str) -> str:
        try:
            return self._processor.parse_color(value)
        except Exception:
            return value.strip().lower()

    def _should_use_color_pulse(
        self,
        animation: AnimationDefinition,
        ppt_attribute: str,
    ) -> bool:
        if not self._uses_text_color_semantics(animation, ppt_attribute):
            return False
        if not AnimationHandler._simple_oracle_gate(animation):
            return False
        if animation.calc_mode != CalcMode.LINEAR:
            return False
        if animation.key_times is not None or animation.key_splines is not None:
            return False
        if len(animation.values) != 3:
            return False
        start = self._normalize_color_identity(animation.values[0])
        pulse = self._normalize_color_identity(animation.values[1])
        end = self._normalize_color_identity(animation.values[2])
        return start == end and pulse != start

    def _should_use_simple_text_color_oracle(
        self,
        animation: AnimationDefinition,
        ppt_attribute: str,
    ) -> bool:
        return (
            self._uses_text_color_semantics(animation, ppt_attribute)
            and AnimationHandler._simple_oracle_gate(animation)
            and animation.calc_mode != CalcMode.DISCRETE
            and len(animation.values) <= 2
            and animation.key_times is None
        )

    def _build_simple_text_color_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element:
        return default_oracle().instantiate(
            "emph/text_color",
            shape_id=animation.element_id,
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            BEHAVIOR_ID=behavior_id,
            TO_COLOR=self._processor.parse_color(animation.values[-1]),
            INNER_FILL=_inner_fill(animation),
        )

    def _build_color_pulse_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element:
        half_duration_ms = max(1, int(round(animation.duration_ms / 2.0)))
        par = default_oracle().instantiate(
            "emph/color_pulse",
            shape_id=animation.element_id,
            par_id=par_id,
            duration_ms=half_duration_ms,
            delay_ms=animation.begin_ms,
            STYLE_CLR_BEHAVIOR_ID=behavior_id,
            FILL_CLR_BEHAVIOR_ID=behavior_id + 1,
            FILL_TYPE_BEHAVIOR_ID=behavior_id + 2,
            FILL_ON_BEHAVIOR_ID=behavior_id + 3,
            TO_COLOR=self._processor.parse_color(animation.values[1]),
            INNER_FILL="remove",
        )
        outer_ctn = par.find(f"{{{NS_P}}}cTn")
        if outer_ctn is not None:
            outer_ctn.set("dur", format_duration_ms(animation.duration_ms))
        return par

    def _build_oracle_template_color_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
    ) -> etree._Element:
        oracle = default_oracle()
        to_color = self._processor.parse_color(animation.values[-1])
        inner_fill = _inner_fill(animation)

        if ppt_attribute == "fill.color":
            return oracle.instantiate(
                "emph/shape_fill_color",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=animation.duration_ms,
                delay_ms=animation.begin_ms,
                STYLE_CLR_BEHAVIOR_ID=behavior_id,
                FILL_CLR_BEHAVIOR_ID=behavior_id + 1,
                FILL_TYPE_BEHAVIOR_ID=behavior_id + 2,
                FILL_ON_BEHAVIOR_ID=behavior_id + 3,
                TO_COLOR=to_color,
                INNER_FILL=inner_fill,
            )
        if ppt_attribute == "style.color":
            return oracle.instantiate(
                "emph/text_color",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=animation.duration_ms,
                delay_ms=animation.begin_ms,
                BEHAVIOR_ID=behavior_id,
                TO_COLOR=to_color,
                INNER_FILL=inner_fill,
            )
        if ppt_attribute == "stroke.color":
            return oracle.instantiate(
                "emph/stroke_color",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=animation.duration_ms,
                delay_ms=animation.begin_ms,
                CLR_BEHAVIOR_ID=behavior_id,
                SET_BEHAVIOR_ID=behavior_id + 1,
                TO_COLOR=to_color,
                INNER_FILL=inner_fill,
            )

        return oracle.instantiate(
            "emph/color",
            shape_id=animation.element_id,
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            BEHAVIOR_ID=behavior_id,
            FROM_COLOR=self._processor.parse_color(animation.values[0]),
            TO_COLOR=to_color,
            TARGET_ATTRIBUTE=ppt_attribute,
            INNER_FILL=inner_fill,
        )


def _inner_fill(animation: AnimationDefinition) -> str:
    return "hold" if animation.fill_mode == "freeze" else "remove"
