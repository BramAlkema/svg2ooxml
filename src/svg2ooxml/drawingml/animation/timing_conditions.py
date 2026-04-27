"""Start and end condition builders for PowerPoint timing XML."""

from __future__ import annotations

from collections.abc import Sequence

from lxml import etree

from svg2ooxml.drawingml.xml_builder import p_sub
from svg2ooxml.ir.animation import BeginTrigger, BeginTriggerType

from .timing_values import format_delay_ms

__all__ = [
    "append_begin_conditions",
    "append_delay_condition",
    "append_end_conditions",
    "append_trigger_conditions",
]


def append_delay_condition(parent: etree._Element, delay_ms: int | float) -> etree._Element:
    """Append a simple non-negative delay condition."""
    return p_sub(parent, "cond", delay=format_delay_ms(delay_ms))


def append_begin_conditions(
    *,
    st_cond_lst: etree._Element,
    begin_triggers: Sequence[BeginTrigger],
    fallback_delay_ms: int,
    default_target_shape: str | None,
) -> None:
    """Append start conditions, falling back to a simple delay when needed."""
    created = append_trigger_conditions(
        st_cond_lst,
        triggers=begin_triggers,
        default_target_shape=default_target_shape,
    )
    if created == 0:
        append_delay_condition(st_cond_lst, fallback_delay_ms)


def append_end_conditions(
    *,
    end_cond_lst: etree._Element,
    end_triggers: Sequence[BeginTrigger],
    default_target_shape: str | None,
) -> None:
    """Append end conditions, removing the empty list if none are representable."""
    created = append_trigger_conditions(
        end_cond_lst,
        triggers=end_triggers,
        default_target_shape=default_target_shape,
    )
    if created == 0:
        parent = end_cond_lst.getparent()
        if parent is not None:
            parent.remove(end_cond_lst)


def append_trigger_conditions(
    parent: etree._Element,
    *,
    triggers: Sequence[BeginTrigger],
    default_target_shape: str | None,
) -> int:
    """Append native-compatible trigger conditions and return the count created."""
    created = 0
    for trigger in triggers:
        delay_ms = _trigger_delay_ms(trigger)
        trigger_type = trigger.trigger_type

        if trigger_type == BeginTriggerType.TIME_OFFSET:
            append_delay_condition(parent, delay_ms)
            created += 1
            continue

        if trigger_type == BeginTriggerType.CLICK:
            cond = p_sub(parent, "cond", evt="onClick", delay=format_delay_ms(delay_ms))
            _append_shape_target(
                cond,
                trigger.target_element_id or default_target_shape,
            )
            created += 1
            continue

        if trigger_type == BeginTriggerType.ELEMENT_BEGIN:
            _append_element_event(parent, evt="onBegin", trigger=trigger, delay_ms=delay_ms)
            created += 1
            continue

        if trigger_type == BeginTriggerType.ELEMENT_END:
            _append_element_event(parent, evt="onEnd", trigger=trigger, delay_ms=delay_ms)
            created += 1

    return created


def _trigger_delay_ms(trigger: BeginTrigger) -> int:
    return int(format_delay_ms(trigger.delay_seconds * 1000))


def _append_element_event(
    parent: etree._Element,
    *,
    evt: str,
    trigger: BeginTrigger,
    delay_ms: int,
) -> None:
    cond = p_sub(parent, "cond", evt=evt, delay=format_delay_ms(delay_ms))
    _append_shape_target(cond, trigger.target_element_id)


def _append_shape_target(cond: etree._Element, shape_id: str | None) -> None:
    if not shape_id:
        return
    tgt_el = p_sub(cond, "tgtEl")
    p_sub(tgt_el, "spTgt", spid=shape_id)
