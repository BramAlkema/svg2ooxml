"""Base handler for animation types.

This module defines the abstract base class for all animation handlers.
Each handler specializes in converting specific animation types from SVG
to PowerPoint timing XML.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Mapping

from lxml import etree

from svg2ooxml.drawingml.xml_builder import NS_P, p_elem, p_sub
from svg2ooxml.ir.animation import BeginTriggerType

if TYPE_CHECKING:
    from svg2ooxml.common.units import UnitConverter
    from svg2ooxml.ir.animation import AnimationDefinition

    from ..native_fragment import NativeFragment
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
    ) -> etree._Element | NativeFragment | None:
        """Build a native fragment for *animation*, or ``None`` to skip.

        Legacy handlers may still return a raw ``<p:par>`` element. The writer
        wraps that into a :class:`NativeFragment` centrally.
        """
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

        set_children: list[etree._Element] = []
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

            to_elem = p_sub(set_elem, "to")
            p_sub(to_elem, "strVal", val=val)

            set_children.append(
                self._xml.build_delayed_child_par(
                    par_id=current_id + 1,
                    delay_ms=delay_ms,
                    duration_ms=1,
                    child_element=set_elem,
                )
            )
            current_id += 2

        return self._xml.build_par_container_with_children_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_elements=set_children,
            preset_class="emph",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
        )

    def _native_fragment(
        self,
        par: etree._Element,
        *,
        source: str,
        strategy: str,
        metadata: Mapping[str, object] | None = None,
        **extra_metadata: object,
    ) -> "NativeFragment":
        """Wrap a built ``<p:par>`` with explicit emission provenance."""
        from ..native_fragment import NativeFragment

        fragment_metadata = dict(metadata or {})
        fragment_metadata.update(extra_metadata)
        return NativeFragment.from_legacy_par(
            par,
            source=source,
            strategy=strategy,
            metadata=fragment_metadata,
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
