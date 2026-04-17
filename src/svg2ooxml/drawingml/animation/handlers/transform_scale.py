"""Scale-specific transform animation builders.

Extracted from ``transform.py`` — module-level functions that build
``<p:animScale>`` and companion origin-motion elements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.common.conversions.scale import scale_to_ppt
from svg2ooxml.drawingml.xml_builder import p_elem, p_sub

if TYPE_CHECKING:
    from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = [
    "build_scale_element",
    "build_scale_origin_motion",
]


def build_scale_element(
    xml: AnimationXMLBuilder,
    animation: AnimationDefinition,
    behavior_id: int,
    scale_pairs: list[tuple[float, float]],
) -> etree._Element | None:
    """Build ``<p:animScale>`` with from/to derived from *scale_pairs*."""
    if not scale_pairs:
        return None

    from_sx, from_sy = scale_pairs[0]
    to_sx, to_sy = scale_pairs[-1]

    anim_scale = p_elem("animScale")

    cBhvr = xml.build_behavior_core_elem(
        behavior_id=behavior_id,
        duration_ms=animation.duration_ms,
        target_shape=animation.element_id,
        additive=animation.additive,
        fill_mode=animation.fill_mode,
        repeat_count=animation.repeat_count,
    )
    anim_scale.append(cBhvr)

    p_sub(
        anim_scale,
        "from",
        x=str(scale_to_ppt(from_sx)),
        y=str(scale_to_ppt(from_sy)),
    )
    p_sub(
        anim_scale,
        "to",
        x=str(scale_to_ppt(to_sx)),
        y=str(scale_to_ppt(to_sy)),
    )

    return anim_scale


def build_scale_origin_motion(
    xml: AnimationXMLBuilder,
    animation: AnimationDefinition,
    behavior_id: int,
    scale_pairs: list[tuple[float, float]],
    viewport_px: tuple[float, float],
    format_coord: object,  # Callable[[float], str]
) -> etree._Element | None:
    """Compensate for SVG scaling around the origin.

    PowerPoint animScale grows around the shape center.  SVG scale transforms
    grow around the current user-space origin, so the final SVG center is
    offset by ``center * (scale - 1)`` from the unanimated rendered center.
    Emit a companion motion path when we know that center.
    """
    if len(scale_pairs) < 2:
        return None
    if animation.element_center_px is None:
        return None

    to_sx, to_sy = scale_pairs[-1]
    center_x, center_y = animation.element_center_px
    delta_x = center_x * (to_sx - 1.0)
    delta_y = center_y * (to_sy - 1.0)
    if abs(delta_x) <= 1e-6 and abs(delta_y) <= 1e-6:
        return None

    viewport_w, viewport_h = viewport_px
    path = (
        f"M 0 0 L {format_coord(delta_x / viewport_w)} "  # type: ignore[operator]
        f"{format_coord(delta_y / viewport_h)} E"  # type: ignore[operator]
    )

    anim_motion = p_elem(
        "animMotion",
        origin="layout",
        path=path,
        pathEditMode="relative",
        rAng="0",
        ptsTypes="AA",
    )
    cBhvr = xml.build_behavior_core_elem(
        behavior_id=behavior_id,
        duration_ms=animation.duration_ms,
        target_shape=animation.element_id,
        attr_name_list=["ppt_x", "ppt_y"],
        additive=animation.additive,
        fill_mode=animation.fill_mode,
        repeat_count=animation.repeat_count,
    )
    anim_motion.append(cBhvr)
    p_sub(anim_motion, "rCtr", x="0", y="0")
    return anim_motion
