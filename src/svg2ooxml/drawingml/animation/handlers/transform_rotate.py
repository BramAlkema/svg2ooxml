"""Rotate-specific transform animation builders.

Extracted from ``transform.py`` — module-level functions that build
``<p:animRot>``, multi-keyframe rotate sequences, and orbital motion paths.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.animation.timing_utils import compute_segment_durations_ms
from svg2ooxml.drawingml.xml_builder import p_elem, p_sub

if TYPE_CHECKING:
    from svg2ooxml.common.units import UnitConverter
    from svg2ooxml.drawingml.animation.value_processors import ValueProcessor
    from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = [
    "build_multi_keyframe_rotate",
    "build_orbital_motion_element",
    "build_rotate_element",
    "build_rotate_with_orbit",
    "compute_orbit_offset",
    "extract_rotation_center",
    "interpolate_angles",
]


def extract_rotation_center(
    parsed: list[tuple[float, float | None, float | None]],
) -> tuple[float, float] | None:
    """Return consistent (cx, cy) if all values share the same center."""
    cx, cy = None, None
    for _, vcx, vcy in parsed:
        if vcx is not None and vcy is not None:
            if cx is None:
                cx, cy = vcx, vcy
            elif abs(vcx - cx) > 1e-6 or abs(vcy - cy) > 1e-6:  # type: ignore[operator]
                # Varying centers across keyframes — use first
                return (cx, cy)  # type: ignore[return-value]
    if cx is not None and cy is not None:
        return (cx, cy)  # type: ignore[return-value]
    return None


def compute_orbit_offset(
    rotation_center: tuple[float, float] | None,
    element_center_px: tuple[float, float] | None,
) -> tuple[float, float] | None:
    """Return (dx, dy) offset from rotation center to shape center, or None."""
    if rotation_center is None or element_center_px is None:
        return None
    cx, cy = rotation_center
    sx, sy = element_center_px
    dx, dy = sx - cx, sy - cy
    # Skip if shape center ≈ rotation center (no orbit needed)
    if abs(dx) < 0.5 and abs(dy) < 0.5:
        return None
    return (dx, dy)


def build_rotate_element(
    xml: AnimationXMLBuilder,
    processor: ValueProcessor,
    animation: AnimationDefinition,
    behavior_id: int,
    angles: list[float],
) -> etree._Element | None:
    """Build a single ``<p:animRot>`` element."""
    if not angles:
        return None

    start_angle = angles[0]
    rotation_delta = processor.format_ppt_angle(angles[-1] - start_angle)

    anim_rot = p_elem("animRot", by=rotation_delta)

    cBhvr = xml.build_behavior_core_elem(
        behavior_id=behavior_id,
        duration_ms=animation.duration_ms,
        target_shape=animation.element_id,
        attr_name_list=["r"],
        additive=animation.additive,
        fill_mode=animation.fill_mode,
        repeat_count=animation.repeat_count,
    )
    anim_rot.append(cBhvr)

    return anim_rot


def build_rotate_with_orbit(
    xml: AnimationXMLBuilder,
    processor: ValueProcessor,
    units: UnitConverter,
    animation: AnimationDefinition,
    par_id: int,
    behavior_id: int,
    angles: list[float],
    orbit_offset: tuple[float, float],
    format_coord: Callable[[float], str],
    slide_size: tuple[int, int],
) -> etree._Element:
    """Build ``<p:par>`` with spin + orbital motion playing simultaneously."""
    delta_deg = angles[-1] - angles[0]
    rotation_delta = processor.format_ppt_angle(delta_deg)

    anim_rot = p_elem("animRot", by=rotation_delta)
    anim_rot.append(
        xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            attr_name_list=["r"],
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
    )

    anim_motion = build_orbital_motion_element(
        xml=xml,
        units=units,
        animation=animation,
        behavior_id=behavior_id + 2,
        angles=angles,
        orbit_offset=orbit_offset,
        format_coord=format_coord,
        slide_size=slide_size,
    )
    child_elements = [anim_rot]
    if anim_motion is not None:
        child_elements.append(anim_motion)
    return xml.build_par_container_with_children_elem(
        par_id=par_id,
        duration_ms=animation.duration_ms,
        delay_ms=animation.begin_ms,
        child_elements=child_elements,
        preset_id=8,
        preset_class="emph",
        preset_subtype=0,
        node_type="clickEffect",
        begin_triggers=animation.begin_triggers,
        default_target_shape=animation.element_id,
        effect_group_id=par_id,
        repeat_count=animation.repeat_count,
    )


def build_orbital_motion_element(
    xml: AnimationXMLBuilder,
    units: UnitConverter,
    animation: AnimationDefinition,
    behavior_id: int,
    angles: list[float],
    orbit_offset: tuple[float, float],
    format_coord: Callable[[float], str],
    slide_size: tuple[int, int],
) -> etree._Element | None:
    """Build ``<p:animMotion>`` for the circular orbit around a rotation center.

    *orbit_offset* is (dx, dy) from rotation center to shape center in px.
    *angles* are the full keyframe angle sequence (may be 2+ values).
    """
    slide_w, slide_h = slide_size
    dx_px, dy_px = orbit_offset
    start_deg = angles[0]
    total_sweep = angles[-1] - start_deg

    # Build arc path with line segments
    n_steps = max(8, int(abs(total_sweep) / 45.0) * 2)
    if n_steps < 2:
        return None

    segments: list[str] = ["M 0 0"]
    for step in range(1, n_steps + 1):
        # For multi-keyframe, interpolate through all angles
        t = step / n_steps
        # Linear interpolation through the full angle sequence
        if (
            len(angles) > 2
            and animation.key_times
            and len(animation.key_times) == len(angles)
        ):
            theta_deg = interpolate_angles(angles, animation.key_times, t)
        else:
            theta_deg = start_deg + total_sweep * t
        theta_rad = math.radians(theta_deg) - math.radians(start_deg)
        cos_t, sin_t = math.cos(theta_rad), math.sin(theta_rad)
        mx_px = dx_px * (cos_t - 1) - dy_px * sin_t
        my_px = dx_px * sin_t + dy_px * (cos_t - 1)
        mx_emu = units.to_emu(mx_px, axis="x")
        my_emu = units.to_emu(my_px, axis="y")
        segments.append(
            f"L {format_coord(mx_emu / slide_w)} {format_coord(my_emu / slide_h)}"
        )

    path = " ".join(segments) + " E"
    pts_types = "A" * (n_steps + 1)

    anim_motion = p_elem(
        "animMotion",
        origin="layout",
        path=path,
        pathEditMode="relative",
        rAng="0",
        ptsTypes=pts_types,
    )
    cBhvr = xml.build_behavior_core_elem(
        behavior_id=behavior_id,
        duration_ms=animation.duration_ms,
        target_shape=animation.element_id,
        additive=animation.additive,
        fill_mode=animation.fill_mode,
        repeat_count=animation.repeat_count,
    )
    anim_motion.append(cBhvr)
    p_sub(anim_motion, "rCtr", x="0", y="0")
    return anim_motion


def interpolate_angles(
    angles: list[float],
    key_times: list[float],
    t: float,
) -> float:
    """Linearly interpolate through keyframed angles at normalised time *t*."""
    if t <= 0.0:
        return angles[0]
    if t >= 1.0:
        return angles[-1]
    for i in range(len(key_times) - 1):
        if t <= key_times[i + 1]:
            seg_t = (t - key_times[i]) / max(1e-9, key_times[i + 1] - key_times[i])
            return angles[i] + (angles[i + 1] - angles[i]) * seg_t
    return angles[-1]


def build_multi_keyframe_rotate(
    xml: AnimationXMLBuilder,
    processor: ValueProcessor,
    units: UnitConverter,
    animation: AnimationDefinition,
    par_id: int,
    behavior_id: int,
    angles: list[float],
    format_coord: Callable[[float], str],
    slide_size: tuple[int, int],
    *,
    rotation_center: tuple[float, float] | None = None,
) -> etree._Element:
    """Build a ``<p:par>`` with sequenced ``<p:animRot>`` segments.

    Splits N angles into N-1 segments so that multi-keyframe rotations
    like ``0 -> 360 -> 0`` produce two visible rotation steps instead of
    collapsing to ``by="0"``.
    """
    n_segments = len(angles) - 1
    total_ms = animation.duration_ms

    seg_durations = compute_segment_durations_ms(
        total_ms=total_ms,
        n_values=len(angles),
        key_times=(
            animation.key_times
            if animation.key_times and len(animation.key_times) == len(angles)
            else None
        ),
    )

    child_elements: list[etree._Element] = []
    bid = behavior_id
    delay_acc = 0

    for i in range(n_segments):
        delta_deg = angles[i + 1] - angles[i]
        rotation_delta = processor.format_ppt_angle(delta_deg)
        seg_dur = seg_durations[i]

        anim_rot = p_elem("animRot", by=rotation_delta)
        seg_fill = animation.fill_mode if i == n_segments - 1 else "hold"
        cBhvr = xml.build_behavior_core_elem(
            behavior_id=bid,
            duration_ms=seg_dur,
            target_shape=animation.element_id,
            attr_name_list=["r"],
            additive=animation.additive,
            fill_mode=seg_fill,
            repeat_count=None,
        )
        anim_rot.append(cBhvr)

        child_elements.append(
            xml.build_delayed_child_par(
                par_id=bid + 1,
                delay_ms=delay_acc,
                duration_ms=seg_dur,
                child_element=anim_rot,
            )
        )
        delay_acc += seg_dur
        bid += 2

    # Add orbital motion if rotation center != shape center
    orbit_offset = compute_orbit_offset(
        rotation_center,
        animation.element_center_px,
    )
    if orbit_offset is not None:
        orbit_motion = build_orbital_motion_element(
            xml=xml,
            units=units,
            animation=animation,
            behavior_id=bid,
            angles=angles,
            orbit_offset=orbit_offset,
            format_coord=format_coord,
            slide_size=slide_size,
        )
        if orbit_motion is not None:
            child_elements.append(
                xml.build_delayed_child_par(
                    par_id=bid + 1,
                    delay_ms=0,
                    duration_ms=total_ms,
                    child_element=orbit_motion,
                )
            )

    return xml.build_par_container_with_children_elem(
        par_id=par_id,
        duration_ms=total_ms,
        delay_ms=animation.begin_ms,
        child_elements=child_elements,
        preset_id=8,
        preset_class="emph",
        preset_subtype=0,
        node_type="clickEffect",
        begin_triggers=animation.begin_triggers,
        default_target_shape=animation.element_id,
        effect_group_id=par_id,
        repeat_count=animation.repeat_count,
    )
