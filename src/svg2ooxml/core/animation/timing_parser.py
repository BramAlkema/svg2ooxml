"""Timing extraction helpers for SMIL animation parsing."""

from __future__ import annotations

import re

from svg2ooxml.common.time import parse_time_value
from svg2ooxml.ir.animation import (
    AnimationTiming,
    AnimationType,
    BeginTrigger,
    BeginTriggerType,
    CalcMode,
    FillMode,
)

# ------------------------------------------------------------------ #
# Compiled regex patterns (moved from SMILParser class attributes)   #
# ------------------------------------------------------------------ #
_TIME_OFFSET_RE = re.compile(
    r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:ms|s|min|h)?$",
    re.IGNORECASE,
)
_ELEMENT_EVENT_RE = re.compile(
    r"^([A-Za-z_][\w.\-]*)\.([A-Za-z_][\w.\-]*)\s*([+-].+)?$",
    re.IGNORECASE,
)
_REPEAT_EVENT_RE = re.compile(
    r"^([A-Za-z_][\w.\-]*)\.repeat\(([^)]+)\)\s*([+-].+)?$",
    re.IGNORECASE,
)
_ACCESS_KEY_RE = re.compile(
    r"^accessKey\(([^)]+)\)\s*([+-].+)?$",
    re.IGNORECASE,
)
_WALLCLOCK_RE = re.compile(
    r"^wallclock\(([^)]+)\)\s*([+-].+)?$",
    re.IGNORECASE,
)
_CLICK_OFFSET_RE = re.compile(
    r"^click\s*([+-].+)$",
    re.IGNORECASE,
)


# ------------------------------------------------------------------ #
# Module-level functions                                             #
# ------------------------------------------------------------------ #


def parse_timing(
    element,
    *,
    animation_summary,
    record_degradation,
) -> AnimationTiming:
    begin, begin_triggers = parse_begin(
        element.get("begin"),
        animation_summary=animation_summary,
        record_degradation=record_degradation,
    )
    end_triggers = parse_end(
        element.get("end"),
        animation_summary=animation_summary,
        record_degradation=record_degradation,
    )
    dur_value = element.get("dur", "1s")
    duration = float("inf") if dur_value == "indefinite" else parse_time_value(dur_value)
    repeat_duration = _parse_optional_duration(element.get("repeatDur"))

    repeat_attr = element.get("repeatCount", "1")
    if repeat_attr == "indefinite":
        repeat_count: int | str = "indefinite"
    else:
        try:
            repeat_count = int(float(repeat_attr))
        except (ValueError, TypeError):
            repeat_count = 1

    fill_attr = element.get("fill", "remove")
    fill_mode = FillMode.FREEZE if fill_attr == "freeze" else FillMode.REMOVE

    return AnimationTiming(
        begin=begin,
        duration=duration,
        repeat_count=repeat_count,
        repeat_duration=repeat_duration,
        fill_mode=fill_mode,
        begin_triggers=begin_triggers,
        end_triggers=end_triggers,
    )


def _parse_optional_duration(value: str | None) -> float | None:
    if not value or value == "indefinite":
        return None
    return parse_time_value(value)


def parse_begin(
    begin_attr: str | None,
    *,
    animation_summary,
    record_degradation,
) -> tuple[float, list[BeginTrigger] | None]:
    """Parse SMIL begin expression(s) into fallback seconds and trigger metadata."""
    if begin_attr is None:
        return (0.0, [BeginTrigger(trigger_type=BeginTriggerType.TIME_OFFSET, delay_seconds=0.0)])

    begin_text = begin_attr.strip()
    if not begin_text:
        return (0.0, [BeginTrigger(trigger_type=BeginTriggerType.TIME_OFFSET, delay_seconds=0.0)])

    tokens = [token.strip() for token in begin_text.split(";") if token.strip()]
    parsed: list[BeginTrigger] = []
    for token in tokens:
        trigger = parse_begin_token(token, animation_summary=animation_summary, record_degradation=record_degradation)
        if trigger is None:
            animation_summary.add_warning(f"Invalid begin expression: {token}")
            record_degradation("begin_expression_invalid")
            continue
        parsed.append(trigger)

    if not parsed:
        record_degradation("begin_fallback_default_zero")
        return (0.0, [BeginTrigger(trigger_type=BeginTriggerType.TIME_OFFSET, delay_seconds=0.0)])

    # Backward-compatible numeric begin fallback used by existing timing helpers.
    begin_seconds = 0.0
    for trigger in parsed:
        if trigger.trigger_type == BeginTriggerType.TIME_OFFSET and trigger.target_element_id is None:
            begin_seconds = trigger.delay_seconds
            break

    return (begin_seconds, parsed)


def parse_end(
    end_attr: str | None,
    *,
    animation_summary,
    record_degradation,
) -> list[BeginTrigger] | None:
    """Parse SMIL end expressions for IR plumbing.

    The writer does not yet fully realize end conditions natively; this
    keeps them visible to later policy and emitter work.
    """
    if end_attr is None:
        return None

    end_text = end_attr.strip()
    if not end_text:
        return None

    parsed: list[BeginTrigger] = []
    for token in [part.strip() for part in end_text.split(";") if part.strip()]:
        trigger = parse_begin_token(token, animation_summary=animation_summary, record_degradation=record_degradation)
        if trigger is None:
            animation_summary.add_warning(f"Invalid end expression: {token}")
            record_degradation("end_expression_invalid")
            continue
        parsed.append(trigger)

    return parsed or None


def parse_begin_token(
    token: str,
    *,
    animation_summary,
    record_degradation,
) -> BeginTrigger | None:
    raw_token = token.strip()
    lowered = raw_token.lower()
    if not raw_token:
        return None
    if lowered == "indefinite":
        return BeginTrigger(trigger_type=BeginTriggerType.INDEFINITE)
    if lowered == "click":
        return BeginTrigger(trigger_type=BeginTriggerType.CLICK)
    click_offset_match = _CLICK_OFFSET_RE.match(lowered)
    if click_offset_match:
        offset_value = re.sub(r"\s+", "", click_offset_match.group(1).strip())
        if not _TIME_OFFSET_RE.match(offset_value):
            return None
        return BeginTrigger(
            trigger_type=BeginTriggerType.CLICK,
            delay_seconds=parse_time_value(offset_value),
        )
    if _TIME_OFFSET_RE.match(lowered):
        return BeginTrigger(
            trigger_type=BeginTriggerType.TIME_OFFSET,
            delay_seconds=parse_time_value(lowered),
        )

    repeat_match = _REPEAT_EVENT_RE.match(raw_token)
    if repeat_match:
        target_element_id, repeat_iteration, offset_expr = repeat_match.groups()
        delay_seconds = _parse_optional_offset_seconds(offset_expr)
        if delay_seconds is None:
            return None
        repeat_iteration = repeat_iteration.strip()
        return BeginTrigger(
            trigger_type=BeginTriggerType.ELEMENT_REPEAT,
            delay_seconds=delay_seconds,
            target_element_id=target_element_id,
            event_name="repeat",
            repeat_iteration=(
                int(repeat_iteration)
                if repeat_iteration.isdigit()
                else repeat_iteration
            ),
        )

    access_key_match = _ACCESS_KEY_RE.match(raw_token)
    if access_key_match:
        access_key, offset_expr = access_key_match.groups()
        delay_seconds = _parse_optional_offset_seconds(offset_expr)
        if delay_seconds is None:
            return None
        return BeginTrigger(
            trigger_type=BeginTriggerType.ACCESS_KEY,
            delay_seconds=delay_seconds,
            access_key=access_key.strip(),
        )

    wallclock_match = _WALLCLOCK_RE.match(raw_token)
    if wallclock_match:
        wallclock_value, offset_expr = wallclock_match.groups()
        delay_seconds = _parse_optional_offset_seconds(offset_expr)
        if delay_seconds is None:
            return None
        return BeginTrigger(
            trigger_type=BeginTriggerType.WALLCLOCK,
            delay_seconds=delay_seconds,
            wallclock_value=wallclock_value.strip(),
        )

    match = _ELEMENT_EVENT_RE.match(raw_token)
    if not match:
        return None

    target_element_id, event_name, offset_expr = match.groups()
    delay_seconds = _parse_optional_offset_seconds(offset_expr)
    if delay_seconds is None:
        return None

    event_name = event_name.lower()
    if event_name == "click":
        trigger_type = BeginTriggerType.CLICK
    elif event_name == "begin":
        trigger_type = BeginTriggerType.ELEMENT_BEGIN
    elif event_name == "end":
        trigger_type = BeginTriggerType.ELEMENT_END
    else:
        trigger_type = BeginTriggerType.EVENT

    return BeginTrigger(
        trigger_type=trigger_type,
        delay_seconds=delay_seconds,
        target_element_id=target_element_id,
        event_name=event_name,
    )


def _parse_optional_offset_seconds(offset_expr: str | None) -> float | None:
    if not offset_expr:
        return 0.0
    offset_value = re.sub(r"\s+", "", offset_expr.strip())
    if not _TIME_OFFSET_RE.match(offset_value):
        return None
    return parse_time_value(offset_value)


def parse_key_times(
    element,
    *,
    animation_summary,
    record_degradation,
) -> list[float] | None:
    attr = element.get("keyTimes")
    if not attr:
        return None

    try:
        values = [float(value.strip()) for value in attr.split(";") if value.strip()]
    except (ValueError, TypeError):
        animation_summary.add_warning("Invalid keyTimes format")
        record_degradation("key_times_invalid_format")
        return None

    if not all(0.0 <= value <= 1.0 for value in values):
        animation_summary.add_warning("keyTimes values outside [0,1] range")
        record_degradation("key_times_out_of_range")
        return None
    if values != sorted(values):
        animation_summary.add_warning("keyTimes must be in ascending order")
        record_degradation("key_times_not_ascending")
        return None

    return values or None


def parse_key_points(
    element,
    animation_type: AnimationType,
    *,
    animation_summary,
    record_degradation,
) -> list[float] | None:
    attr = element.get("keyPoints")
    if not attr:
        return None

    try:
        values = [float(value.strip()) for value in attr.split(";") if value.strip()]
    except (ValueError, TypeError):
        animation_summary.add_warning("Invalid keyPoints format")
        record_degradation("key_points_invalid_format")
        return None

    if not all(0.0 <= value <= 1.0 for value in values):
        animation_summary.add_warning("keyPoints values outside [0,1] range")
        record_degradation("key_points_out_of_range")
        return None

    if animation_type != AnimationType.ANIMATE_MOTION:
        animation_summary.add_warning(
            "Ignoring keyPoints because animation is not animateMotion"
        )
        record_degradation("key_points_non_motion")
        return None

    return values or None


def parse_key_splines(
    element,
    *,
    animation_summary,
    record_degradation,
) -> list[list[float]] | None:
    attr = element.get("keySplines")
    if not attr:
        return None

    try:
        groups = [group.strip() for group in attr.split(";") if group.strip()]
        splines: list[list[float]] = []
        for group in groups:
            numbers = [float(value.strip()) for value in re.split(r"[,\s]+", group) if value.strip()]
            if len(numbers) != 4 or not all(0.0 <= number <= 1.0 for number in numbers):
                raise ValueError
            splines.append(numbers)
    except (ValueError, TypeError):
        animation_summary.add_warning("Invalid keySplines format")
        record_degradation("key_splines_invalid_format")
        return None

    return splines or None


def parse_calc_mode(
    element,
    animation_type: AnimationType,
) -> CalcMode:
    attr = (element.get("calcMode") or "").strip().lower()
    mapping = {
        "linear": CalcMode.LINEAR,
        "discrete": CalcMode.DISCRETE,
        "paced": CalcMode.PACED,
        "spline": CalcMode.SPLINE,
    }
    if not attr:
        if animation_type == AnimationType.ANIMATE_MOTION:
            return CalcMode.PACED
        return CalcMode.LINEAR
    return mapping.get(attr, CalcMode.LINEAR)
