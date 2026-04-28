"""Stroke dash conversion helpers for DrawingML."""

from __future__ import annotations

from svg2ooxml.common.dash_patterns import normalize_dash_array
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub


def _dash_elem(
    dash_array: list[float] | None,
    stroke_width: float = 1.0,
    *,
    dash_offset: float = 0.0,
    ppt_compat: bool = False,
):
    """Create a DrawingML custom dash pattern element."""
    if not dash_array:
        return None
    values = normalize_dash_array(dash_array)
    if not values:
        return None

    if dash_offset and values:
        values = _apply_dash_offset(values, dash_offset)

    width = max(stroke_width, 0.01)

    cust = a_elem("custDash")
    for i in range(0, len(values), 2):
        dash_px = values[i]
        space_px = values[i + 1] if i + 1 < len(values) else 0
        if ppt_compat:
            d_val = max(1, int(round(dash_px * 75000)))
            sp_val = max(1, int(round(space_px * 75000)))
        else:
            d_val = max(1, int(round(dash_px / width * 100000)))
            sp_val = max(1, int(round(space_px / width * 100000)))
        a_sub(cust, "ds", d=d_val, sp=sp_val)

    return cust if len(cust) > 0 else None


def _apply_dash_offset(values: list[float], offset: float) -> list[float]:
    """Rotate a dash/gap array by *offset* user units."""
    pattern_length = sum(values)
    if pattern_length <= 0:
        return values

    offset = offset % pattern_length
    if offset < 1e-9:
        return values

    consumed = 0.0
    split_idx = 0
    for i, value in enumerate(values):
        if consumed + value > offset + 1e-9:
            split_idx = i
            break
        consumed += value
    else:
        return values

    into = offset - consumed
    remainder = values[split_idx] - into

    after = list(values[split_idx + 1 :])
    before = list(values[:split_idx])
    rotated = [remainder] + after + before + [into]

    if split_idx % 2 == 1:
        rotated = [0.0] + rotated

    if len(rotated) % 2 == 1:
        rotated.append(0.0)

    return rotated


__all__ = ["_apply_dash_offset", "_dash_elem"]
