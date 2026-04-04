"""Numeric animation handler.

Generates PowerPoint ``<p:anim>`` elements with TAV keyframes for
x, y, width, height, stroke-width, rotate, and other numeric attributes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import p_elem, p_sub
from svg2ooxml.ir.animation import AnimationType, CalcMode

from ..constants import (
    ATTRIBUTE_NAME_MAP,
    COLOR_ATTRIBUTES,
    FADE_ATTRIBUTES,
    WIPE_ATTRIBUTES,
)
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

    # Attributes that map to <p:animScale> (size changes)
    _SCALE_ATTRS = {"ppt_h", "ppt_w", "height", "width", "w", "h", "rx", "ry"}
    # Attributes that map to <p:animMotion> (position changes)
    _MOTION_ATTRS = {"ppt_x", "ppt_y", "x", "y", "cx", "cy"}

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element | None:
        """Build ``<p:par>`` with the correct animation element type."""
        if animation.target_attribute in WIPE_ATTRIBUTES:
            return self._build_wipe_entrance(animation, par_id, behavior_id)

        ppt_attribute = self._map_attribute_name(animation.target_attribute)

        if (
            ppt_attribute in self._SCALE_ATTRS
            or animation.target_attribute in self._SCALE_ATTRS
        ):
            if len(animation.values) > 2 or animation.key_times:
                return self._build_generic_anim(
                    animation,
                    par_id,
                    behavior_id,
                    ppt_attribute,
                    preset_id=None,
                    preset_class="emph",
                )
            return self._build_scale_animation(
                animation, par_id, behavior_id, ppt_attribute
            )

        is_simple = len(animation.values) <= 2 and not animation.key_times
        if is_simple and (
            ppt_attribute in self._MOTION_ATTRS
            or animation.target_attribute in self._MOTION_ATTRS
        ):
            return self._build_position_animation(
                animation, par_id, behavior_id, ppt_attribute
            )

        return self._build_generic_anim(animation, par_id, behavior_id, ppt_attribute)

    def _build_scale_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
    ) -> etree._Element:
        """Build ``<p:animScale>`` for width/height changes."""
        values = animation.values
        from_val = float(self._normalize_value(ppt_attribute, values[0]))
        to_val = float(self._normalize_value(ppt_attribute, values[-1]))

        baseline = self._scale_baseline(from_val, to_val)
        from_x, from_y = self._scale_pair(ppt_attribute, from_val, baseline)
        to_x, to_y = self._scale_pair(ppt_attribute, to_val, baseline)

        animScale = p_elem("animScale")
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        animScale.append(cBhvr)
        p_sub(animScale, "from", x=str(from_x), y=str(from_y))
        p_sub(animScale, "to", x=str(to_x), y=str(to_y))

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=animScale,
            preset_id=6,  # Grow emphasis
            preset_class="emph",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
        )

    def _build_position_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
    ) -> etree._Element:
        """Build ``<p:animMotion>`` for x/y position changes."""
        values = animation.values
        from_val = float(self._normalize_value(ppt_attribute, values[0]))
        to_val = float(self._normalize_value(ppt_attribute, values[-1]))

        is_x = ppt_attribute in ("ppt_x", "x", "cx")
        # animMotion path uses relative coordinates (0-1 range of slide)
        # The values are in EMU, convert to slide-relative
        slide_dim = 9144000 if is_x else 6858000  # default slide size
        delta_rel = (to_val - from_val) / slide_dim

        if is_x:
            path = f"M 0 0 L {delta_rel:.6f} 0 E"
        else:
            path = f"M 0 0 L 0 {delta_rel:.6f} E"

        animMotion = p_elem("animMotion")
        animMotion.set("origin", "layout")
        animMotion.set("path", path)
        animMotion.set("pathEditMode", "relative")
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        animMotion.append(cBhvr)

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=animMotion,
            preset_id=0,  # Custom motion
            preset_class="path",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
        )

    def _build_generic_anim(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
        *,
        preset_id: int | None = 32,
        preset_class: str | None = "emph",
    ) -> etree._Element:
        """Build ``<p:anim>`` for other numeric properties (stroke-width, etc.)."""
        anim = p_elem("anim")
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

        tav_elements = self._build_tav_list(animation, ppt_attribute)
        tav_lst = self._xml.build_tav_list_container(tav_elements)
        anim.append(tav_lst)

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=anim,
            preset_id=preset_id,
            preset_class=preset_class,
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
        )

    @staticmethod
    def _scale_baseline(*values: float) -> float:
        for value in values:
            if abs(value) > 1e-6:
                return abs(value)
        return 1.0

    @classmethod
    def _scale_pair(
        cls,
        ppt_attribute: str,
        absolute_value: float,
        baseline: float,
    ) -> tuple[int, int]:
        scale_pct = (
            int(round((absolute_value / baseline) * 100000)) if baseline else 100000
        )
        is_height = ppt_attribute in ("ppt_h", "height", "h", "ry")
        x_pct = 100000 if is_height else scale_pct
        y_pct = scale_pct if is_height else 100000
        return (x_pct, y_pct)

    def _build_wipe_entrance(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element:
        """Build Wipe entrance animation for stroke-dashoffset (line drawing).

        SVG line-drawing effect animates stroke-dashoffset from path length
        to 0. PowerPoint Wipe (presetID=22) entrance with direction subtype
        produces a similar reveal effect.
        """
        # Determine wipe direction: dashoffset going to 0 = left-to-right wipe
        # Subtype 1=left, 2=top, 3=right, 4=bottom
        subtype = 1

        # Build a <p:set> to make shape visible + Wipe entrance
        set_elem = p_elem("set")
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=1,
            target_shape=animation.element_id,
            attr_name_list=["style.visibility"],
        )
        set_elem.append(cBhvr)
        to_elem = p_sub(set_elem, "to")
        p_sub(to_elem, "strVal", val="visible")

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=set_elem,
            preset_id=22,  # Wipe
            preset_class="entr",
            preset_subtype=subtype,
            node_type="withEffect",
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
