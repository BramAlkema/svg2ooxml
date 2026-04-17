"""Base handler for animation types.

This module defines the abstract base class for all animation handlers.
Each handler specializes in converting specific animation types from SVG
to PowerPoint timing XML.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import NS_P, p_elem, p_sub
from svg2ooxml.ir.animation import BeginTriggerType

if TYPE_CHECKING:
    from svg2ooxml.common.units import UnitConverter
    from svg2ooxml.ir.animation import AnimationDefinition

    from ..tav_builder import TAVBuilder
    from ..value_processors import ValueProcessor
    from ..xml_builders import AnimationXMLBuilder

__all__ = ["AnimationHandler"]


class AnimationHandler(ABC):
    """Abstract base class for animation handlers.

    Each handler specializes in building PowerPoint XML for specific
    animation types (opacity, color, transform, numeric, motion, set).

    Handlers receive dependencies via constructor injection and return
    lxml elements from ``build()`` — the writer serializes once at the end.
    """

    def __init__(
        self,
        xml_builder: AnimationXMLBuilder,
        value_processor: ValueProcessor,
        tav_builder: TAVBuilder,
        unit_converter: UnitConverter,
    ):
        self._xml = xml_builder
        self._processor = value_processor
        self._tav = tav_builder
        self._units = unit_converter

    @abstractmethod
    def can_handle(self, animation: AnimationDefinition) -> bool:
        """Return ``True`` if this handler can process *animation*."""
        ...

    @abstractmethod
    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element | None:
        """Build a ``<p:par>`` element for *animation*, or ``None`` to skip."""
        ...

    def _build_discrete_set_sequence(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
        formatted_values: list[str],
    ) -> etree._Element:
        """Build timed ``<p:set>`` segments for ``calcMode="discrete"``.

        PPT's ``<p:anim calcmode="discrete">`` only works on
        ``style.visibility``. For all other attributes, we emit one
        ``<p:set>`` per keyframe value.
        """
        key_times = animation.key_times
        n = len(formatted_values)

        resolved = self._tav.resolve_key_times(formatted_values, key_times)
        if not resolved:
            resolved = [i / max(n - 1, 1) for i in range(n)]

        set_elements: list[etree._Element] = []
        current_id = behavior_id

        for i, val in enumerate(formatted_values):
            delay_ms = int(round(resolved[i] * animation.duration_ms))

            set_elem = p_elem("set")
            cBhvr = self._xml.build_behavior_core_elem(
                behavior_id=current_id,
                duration_ms=1,
                target_shape=animation.element_id,
                attr_name_list=[ppt_attribute],
                fill_mode=animation.fill_mode,
            )
            set_elem.append(cBhvr)

            ctn = cBhvr.find(f"{{{NS_P}}}cTn")
            if ctn is not None:
                st_cond = p_sub(ctn, "stCondLst")
                p_sub(st_cond, "cond", delay=str(delay_ms))

            to_elem = p_sub(set_elem, "to")
            p_sub(to_elem, "strVal", val=val)

            set_elements.append(set_elem)
            current_id += 1

        return self._xml.build_par_container_with_children_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_elements=set_elements,
            preset_class="emph",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
        )

    @staticmethod
    def _simple_oracle_gate(animation: AnimationDefinition) -> bool:
        """Return True when the animation is simple enough for an oracle template.

        Oracle templates emit a single ``<p:cond delay>`` and carry no
        ``additive``, ``repeatCount``, or event-based triggers.
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
