"""Dispatch sampled center-motion composition by IR element type."""

from __future__ import annotations

from svg2ooxml.core.export.sampled_center_motion_group import (
    _build_group_like_center_motion,
)
from svg2ooxml.core.export.sampled_center_motion_shapes import (
    _build_circle_scale_center_motion,
    _build_image_scale_center_motion,
)
from svg2ooxml.core.export.sampled_center_motion_types import (
    AnimationMember,
    _SampledCenterMotionComposition,
)


def _build_sampled_center_motion_composition(
    *,
    element: object,
    current_center: tuple[float, float],
    members: list[AnimationMember],
) -> _SampledCenterMotionComposition | None:
    from svg2ooxml.ir.scene import Group, Image
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Circle, Polygon, Polyline

    if isinstance(element, Circle):
        return _build_circle_scale_center_motion(
            current_center=current_center,
            members=members,
        )

    if isinstance(element, Image):
        return _build_image_scale_center_motion(
            element=element,
            members=members,
        )

    if isinstance(element, (Group, IRPath, Polyline, Polygon)):
        return _build_group_like_center_motion(
            current_center=current_center,
            members=members,
        )

    return None


__all__ = ["_build_sampled_center_motion_composition"]
