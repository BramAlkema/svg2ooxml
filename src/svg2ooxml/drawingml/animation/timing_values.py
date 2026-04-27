"""Small value normalizers for PowerPoint timing XML."""

from __future__ import annotations

import math

from lxml import etree

__all__ = [
    "append_repeat_count",
    "format_delay_ms",
    "format_duration_ms",
    "repeat_count_value",
]

_MAX_PPT_MS = 2_147_483_647


def _coerce_ms(value: int | float, *, minimum: int) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return minimum

    if math.isnan(numeric):
        return minimum
    if math.isinf(numeric):
        return _MAX_PPT_MS if numeric > 0 else minimum
    return max(minimum, int(round(numeric)))


def format_delay_ms(value: int | float) -> str:
    """Return a non-negative millisecond delay for PPT timing conditions."""
    return str(_coerce_ms(value, minimum=0))


def format_duration_ms(value: int | float, *, minimum: int = 0) -> str:
    """Return a bounded millisecond duration for PPT timing containers."""
    return str(_coerce_ms(value, minimum=minimum))


def repeat_count_value(repeat_count: str | int | None) -> str | None:
    """Map SVG repeatCount to PowerPoint's repeatCount attribute value."""
    if repeat_count == "indefinite":
        return "indefinite"

    if repeat_count is None:
        return None

    try:
        count = int(repeat_count)
    except (TypeError, ValueError):
        return None

    if count > 1:
        return str(count * 1000)
    return None


def append_repeat_count(
    ctn: etree._Element,
    repeat_count: int | str | None,
) -> None:
    """Set repeatCount on *ctn* when SVG timing requests repeated playback."""
    ppt_repeat = repeat_count_value(repeat_count)
    if ppt_repeat is not None:
        ctn.set("repeatCount", ppt_repeat)
