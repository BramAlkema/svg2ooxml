"""Numeric animation handler.

Generates PowerPoint ``<p:anim>`` elements with TAV keyframes for
x, y, width, height, stroke-width, rotate, and other numeric attributes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import p_elem
from svg2ooxml.ir.animation import AnimationType, CalcMode

from ..constants import ATTRIBUTE_NAME_MAP, COLOR_ATTRIBUTES, FADE_ATTRIBUTES
from ..timing_utils import compute_paced_key_times
from ..value_formatters import format_numeric_value
from .base import AnimationHandler

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["NumericAnimationHandler"]


class NumericAnimationHandler(AnimationHandler):
    """Handler for numeric animations (position, size, rotation, etc.)."""

    def can_handle(self, animation: AnimationDefinition) -> bool:
        if animation.animation_type != AnimationType.ANIMATE:
            return False
        attr = animation.target_attribute
        if attr in FADE_ATTRIBUTES:
            return False
        if attr in COLOR_ATTRIBUTES:
            return False
        return True

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element | None:
        """Build ``<p:par>`` containing ``<p:anim>`` with TAV keyframes."""
        ppt_attribute = self._map_attribute_name(animation.target_attribute)

        # Build <p:anim>
        anim = p_elem("anim")

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
        anim.append(cBhvr)

        # Build TAV list
        tav_elements = self._build_tav_list(animation, ppt_attribute)
        tav_lst = self._xml.build_tav_list_container(tav_elements)
        anim.append(tav_lst)

        # Wrap in <p:par>
        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=anim,
            preset_id=32,
            preset_class="emph",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
        )

    def _map_attribute_name(self, attribute: str) -> str:
        """Map SVG attribute name to PowerPoint attribute name."""
        return ATTRIBUTE_NAME_MAP.get(attribute, attribute)

    def _normalize_value(self, ppt_attribute: str, value: str) -> str:
        """Normalize numeric value based on attribute type."""
        return self._processor.normalize_numeric_value(
            ppt_attribute, value, unit_converter=self._units
        )

    def _build_tav_list(
        self,
        animation: AnimationDefinition,
        ppt_attribute: str,
    ) -> list[etree._Element]:
        """Build TAV elements for this animation.

        For multi-keyframe (>2 values or explicit key_times), delegates
        to TAVBuilder. For simple 2-value animations, creates from/to
        TAV entries at tm=0 and tm=100000.
        """
        values = animation.values
        key_times = animation.key_times
        normalized = [self._normalize_value(ppt_attribute, v) for v in values]

        # Paced calcMode: compute keyTimes from inter-value distances
        if animation.calc_mode == CalcMode.PACED and len(values) > 2:
            try:
                floats = [float(v) for v in values]
                paced_times = compute_paced_key_times(floats)
                if paced_times is not None:
                    key_times = paced_times
            except (ValueError, TypeError):
                pass  # Fall through to default behavior

        if animation.calc_mode == CalcMode.DISCRETE and (len(values) > 1 or key_times):
            return self._tav.build_discrete_tav_list(
                values=normalized,
                key_times=key_times,
                value_formatter=format_numeric_value,
            )

        # Multi-keyframe: delegate to TAVBuilder with normalized values
        if len(values) > 2 or key_times:
            tav_elements, _ = self._tav.build_tav_list(
                values=normalized,
                key_times=key_times,
                key_splines=animation.key_splines,
                duration_ms=animation.duration_ms,
                value_formatter=format_numeric_value,
            )
            return tav_elements

        # Simple from/to: create two TAV entries
        from_value = self._normalize_value(ppt_attribute, values[0])
        to_value = self._normalize_value(ppt_attribute, values[-1])

        from_tav = self._xml.build_tav_element(
            tm=0,
            value_elem=format_numeric_value(from_value),
        )
        to_tav = self._xml.build_tav_element(
            tm=100000,
            value_elem=format_numeric_value(to_value),
        )
        return [from_tav, to_tav]
