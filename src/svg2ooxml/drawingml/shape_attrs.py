"""Common DrawingML shape attribute helpers."""

from __future__ import annotations

import html

from svg2ooxml.common.conversions.angles import degrees_to_ppt


def descr_attr(metadata) -> str:
    """Return ` descr="..."` attribute string if element has a description."""
    if not isinstance(metadata, dict):
        return ""
    desc = metadata.get("description")
    if not desc:
        return ""
    return f' descr="{html.escape(str(desc), quote=True)}"'


def vert_attr(metadata) -> str:
    """Return ` vert="vert"` or ` vert="vert270"` for vertical writing mode."""
    if not isinstance(metadata, dict):
        return ""
    wm = metadata.get("writing_mode")
    if wm in ("vert", "vert270"):
        return f' vert="{wm}"'
    return ""


def rot_attr(metadata) -> str:
    """Return ` rot="angle"` for text shape rotation (degrees × 60000)."""
    if not isinstance(metadata, dict):
        return ""
    deg = metadata.get("text_rotation_deg")
    try:
        degrees = float(deg)
    except (TypeError, ValueError):
        return ""
    if abs(degrees) > 0.01:
        ppt_angle = degrees_to_ppt(degrees)
        return f' rot="{ppt_angle}"'
    return ""


__all__ = ["descr_attr", "rot_attr", "vert_attr"]
