"""Shared stop and identifier conversion helpers for resvg gradients."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from svg2ooxml.color.adapters import color_object_to_hex
from svg2ooxml.ir.paint import GradientStop as IRGradientStop

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.painting.gradients import GradientStop


def gradient_stops_to_ir(stops: Iterable[GradientStop]) -> list[IRGradientStop]:
    """Convert resvg gradient stops to IR stops, ensuring the IR minimum length."""

    ir_stops = [
        IRGradientStop(
            offset=_clamp(stop.offset, 0.0, 1.0),
            rgb=_color_to_hex(stop.color),
            opacity=stop.color.a,
        )
        for stop in stops
    ]

    if not ir_stops:
        return [
            IRGradientStop(offset=0.0, rgb="000000", opacity=1.0),
            IRGradientStop(offset=1.0, rgb="FFFFFF", opacity=1.0),
        ]
    if len(ir_stops) == 1:
        ir_stops.append(ir_stops[0])
    return ir_stops


def gradient_id_or_none(href: str | None) -> str | None:
    """Normalize empty gradient references to ``None``."""

    return href if href and href.strip() else None


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value to the inclusive range ``[min_val, max_val]``."""

    return max(min_val, min(max_val, value))


def _color_to_hex(color: Any) -> str:
    """Convert a resvg color object to an uppercase ``RRGGBB`` value."""

    return color_object_to_hex(color, scale="auto") or "000000"


__all__ = [
    "_clamp",
    "_color_to_hex",
    "gradient_id_or_none",
    "gradient_stops_to_ir",
]
