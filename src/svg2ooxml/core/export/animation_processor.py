"""Animation serialization helpers, enrichment, and sampled center motion composition."""

from __future__ import annotations

from dataclasses import replace

from svg2ooxml.common.conversions.opacity import parse_authored_opacity
from svg2ooxml.core.export.animation_metadata import _build_animation_metadata
from svg2ooxml.core.export.animation_predicates import (
    _is_polyline_segment_fade_animation,
    _is_simple_line_endpoint_animation,
    _is_simple_motion_sampling_candidate,
    _is_simple_origin_rotate_animation,
    _parse_rotate_bounds,
    _sampled_motion_group_key,
    _simple_position_axis,
    _timing_group_key,
)
from svg2ooxml.core.export.motion_geometry import _infer_element_heading_deg
from svg2ooxml.core.export.repeat_triggers import _expand_deterministic_repeat_triggers
from svg2ooxml.core.export.sampled_center_motion import (
    _compose_sampled_center_motions,
)
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationType,
    CalcMode,
    TransformType,
)

__all__ = [
    "_build_animation_metadata",
    "_compose_sampled_center_motions",
    "_enrich_animations_with_element_centers",
    "_expand_deterministic_repeat_triggers",
    "_is_polyline_segment_fade_animation",
    "_is_simple_line_endpoint_animation",
    "_is_simple_motion_sampling_candidate",
    "_is_simple_origin_rotate_animation",
    "_lower_safe_group_transform_targets_with_animated_descendants",
    "_parse_rotate_bounds",
    "_prepare_scene_for_native_opacity_effects",
    "_sampled_motion_group_key",
    "_simple_position_axis",
    "_timing_group_key",
]

# ---------------------------------------------------------------------------
# Element enrichment
# ---------------------------------------------------------------------------


def _enrich_animations_with_element_centers(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Populate geometry-derived animation metadata from scene graph bounds.

    This is needed so the rotate handler can compute orbital motion paths when
    the SVG rotation center (cx, cy) differs from the shape center, and so
    motion paths can be shifted into the absolute ``ppt_x``/``ppt_y`` space
    that PowerPoint stores in ``<p:animMotion path="...">``.
    """
    from dataclasses import replace as _replace

    from svg2ooxml.ir.scene import Group
    from svg2ooxml.ir.text import TextFrame

    bbox_map: dict[str, tuple[float, float, float, float]] = {}
    center_map: dict[str, tuple[float, float]] = {}
    heading_map: dict[str, float] = {}
    text_origin_map: dict[str, tuple[float, float]] = {}

    def _walk(elements: list) -> None:
        for el in elements:
            meta = getattr(el, "metadata", None)
            bbox = getattr(el, "bbox", None)
            if isinstance(meta, dict):
                for eid in meta.get("element_ids", []):
                    if not isinstance(eid, str) or bbox is None:
                        continue
                    bbox_map.setdefault(
                        eid,
                        (bbox.x, bbox.y, bbox.width, bbox.height),
                    )
                    center_map.setdefault(
                        eid,
                        (bbox.x + bbox.width / 2.0, bbox.y + bbox.height / 2.0),
                    )
                    heading = _infer_element_heading_deg(el)
                    if heading is not None:
                        heading_map.setdefault(eid, heading)
                    if isinstance(el, TextFrame):
                        text_origin_map.setdefault(
                            eid,
                            (el.origin.x, el.origin.y),
                        )
            if isinstance(el, Group):
                _walk(getattr(el, "children", []))

    _walk(scene.elements)

    enriched = []
    viewport_size = None
    if getattr(scene, "width_px", None) and getattr(scene, "height_px", None):
        viewport_size = (float(scene.width_px), float(scene.height_px))
    for anim in animations:
        if (
            anim.transform_type in {TransformType.ROTATE, TransformType.SCALE}
            and anim.element_center_px is None
            and anim.element_id in center_map
        ):
            anim = _replace(anim, element_center_px=center_map[anim.element_id])
        if anim.element_heading_deg is None and anim.element_id in heading_map:
            anim = _replace(anim, element_heading_deg=heading_map[anim.element_id])
        if (
            anim.animation_type == AnimationType.ANIMATE_MOTION
            and anim.element_motion_offset_px is None
            and anim.element_id in bbox_map
        ):
            bbox_x, bbox_y, _, _ = bbox_map[anim.element_id]
            if anim.element_id in text_origin_map:
                origin_x, origin_y = text_origin_map[anim.element_id]
            elif anim.motion_space_matrix is not None:
                origin_x = anim.motion_space_matrix[4]
                origin_y = anim.motion_space_matrix[5]
            else:
                origin_x = 0.0
                origin_y = 0.0
            anim = _replace(
                anim,
                element_motion_offset_px=(bbox_x - origin_x, bbox_y - origin_y),
            )
        if anim.motion_viewport_px is None and viewport_size is not None:
            anim = _replace(anim, motion_viewport_px=viewport_size)
        enriched.append(anim)
    return enriched


def _lower_safe_group_transform_targets_with_animated_descendants(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Lower safe parent-group motion when descendants animate too.

    PowerPoint handles ``grpSp`` motion reliably only when the group is the
    sole animated target in that subtree. Once descendants also animate, the
    grouped playback becomes brittle and our descendant-mimic attempts have not
    held up empirically.

    Keep the fallback intentionally narrow: translate-only group motion can be
    cloned onto renderable leaf descendants while the group is flattened, but
    rotate/scale/matrix group transforms are dropped in mixed subtrees. This
    preserves descendant-local effects and avoids preserving an animated
    ``grpSp`` that PowerPoint renders incorrectly.
    """

    from svg2ooxml.ir.scene import Group

    group_leaf_ids: dict[str, tuple[str, ...]] = {}
    group_descendant_ids: dict[str, tuple[str, ...]] = {}

    def _element_ids(element: object) -> tuple[str, ...]:
        meta = getattr(element, "metadata", None)
        if not isinstance(meta, dict):
            return ()
        return tuple(
            dict.fromkeys(
                eid for eid in meta.get("element_ids", []) if isinstance(eid, str) and eid
            )
        )

    def _leaf_element_ids(element: object) -> tuple[str, ...]:
        if isinstance(element, Group):
            collected: list[str] = []
            for child in element.children:
                collected.extend(_leaf_element_ids(child))
            return tuple(dict.fromkeys(collected))
        return _element_ids(element)

    def _all_descendant_ids(element: object) -> tuple[str, ...]:
        collected: list[str] = []
        collected.extend(_element_ids(element))
        if isinstance(element, Group):
            for child in element.children:
                collected.extend(_all_descendant_ids(child))
        return tuple(dict.fromkeys(collected))

    def _walk(elements: list[object]) -> None:
        for element in elements:
            if not isinstance(element, Group):
                continue
            group_ids = _element_ids(element)
            if group_ids:
                leaf_ids = _leaf_element_ids(element)
                descendant_ids = _all_descendant_ids(element)
                for group_id in group_ids:
                    group_leaf_ids[group_id] = tuple(
                        eid for eid in leaf_ids if eid != group_id
                    )
                    group_descendant_ids[group_id] = tuple(
                        eid for eid in descendant_ids if eid != group_id
                    )
            _walk(list(getattr(element, "children", [])))

    _walk(list(scene.elements))

    if not group_descendant_ids:
        return animations

    animated_ids = {
        animation.element_id
        for animation in animations
        if isinstance(animation.element_id, str) and animation.element_id
    }

    mixed_group_ids = {
        group_id
        for group_id, descendant_ids in group_descendant_ids.items()
        if any(descendant_id in animated_ids for descendant_id in descendant_ids)
    }
    if not mixed_group_ids:
        return animations

    lowered: list[AnimationDefinition] = []
    for animation in animations:
        if (
            animation.animation_type != AnimationType.ANIMATE_TRANSFORM
            or animation.transform_type is None
            or animation.element_id not in mixed_group_ids
        ):
            lowered.append(animation)
            continue

        if animation.transform_type != TransformType.TRANSLATE:
            continue

        for leaf_id in group_leaf_ids.get(animation.element_id, ()):
            raw_attributes = dict(animation.raw_attributes)
            raw_attributes["svg2ooxml_group_transform_split"] = animation.element_id
            raw_attributes["svg2ooxml_group_transform_expanded"] = animation.element_id
            clone_animation_id = (
                f"{animation.animation_id}__{leaf_id}"
                if isinstance(animation.animation_id, str) and animation.animation_id
                else None
            )
            lowered.append(
                replace(
                    animation,
                    element_id=leaf_id,
                    animation_id=clone_animation_id,
                    raw_attributes=raw_attributes,
                )
            )
    return lowered


def _prepare_scene_for_native_opacity_effects(
    scene: IRScene,
    animations: list[AnimationDefinition],
) -> None:
    """Remove baked static alpha for targets driven by native opacity effects."""
    from dataclasses import replace as _replace

    from svg2ooxml.ir.paint import LinearGradientPaint, RadialGradientPaint, SolidPaint
    from svg2ooxml.ir.scene import Group

    target_ids = {
        animation.element_id
        for animation in animations
        if _needs_unbaked_native_opacity_effect(animation)
    }
    if not target_ids:
        return

    def _reset_paint_alpha(paint: object, baked_opacity: float) -> object:
        if isinstance(paint, SolidPaint):
            if abs(float(paint.opacity) - baked_opacity) <= 1e-6:
                return _replace(paint, opacity=1.0)
            return paint
        if isinstance(paint, (LinearGradientPaint, RadialGradientPaint)):
            if paint.stops and all(abs(float(stop.opacity) - baked_opacity) <= 1e-6 for stop in paint.stops):
                return _replace(
                    paint,
                    stops=[
                        _replace(stop, opacity=1.0)
                        for stop in paint.stops
                    ],
                )
        return paint

    def _walk(elements: list[object]) -> list[object]:
        updated_elements: list[object] = []
        for element in elements:
            if isinstance(element, Group):
                updated_elements.append(
                    _replace(element, children=_walk(list(element.children)))
                )
                continue

            metadata = getattr(element, "metadata", None)
            element_ids = (
                [eid for eid in metadata.get("element_ids", []) if isinstance(eid, str)]
                if isinstance(metadata, dict)
                else []
            )
            if not any(element_id in target_ids for element_id in element_ids):
                updated_elements.append(element)
                continue

            baked_opacity = float(getattr(element, "opacity", 1.0))
            kwargs: dict[str, object] = {}
            fill = getattr(element, "fill", None)
            if fill is not None:
                reset_fill = _reset_paint_alpha(fill, baked_opacity)
                if reset_fill is not fill:
                    kwargs["fill"] = reset_fill
            stroke = getattr(element, "stroke", None)
            if stroke is not None and getattr(stroke, "paint", None) is not None:
                reset_stroke_paint = _reset_paint_alpha(stroke.paint, baked_opacity)
                if reset_stroke_paint is not stroke.paint or abs(float(stroke.opacity) - baked_opacity) <= 1e-6:
                    kwargs["stroke"] = _replace(
                        stroke,
                        paint=reset_stroke_paint,
                        opacity=(1.0 if abs(float(stroke.opacity) - baked_opacity) <= 1e-6 else stroke.opacity),
                    )
            if abs(baked_opacity - 1.0) > 1e-6:
                kwargs["opacity"] = 1.0
            updated_elements.append(_replace(element, **kwargs) if kwargs else element)
        return updated_elements

    scene.elements = _walk(list(scene.elements))


def _needs_unbaked_native_opacity_effect(animation: AnimationDefinition) -> bool:
    if animation.animation_type != AnimationType.ANIMATE:
        return False
    if animation.target_attribute != "opacity":
        return False

    values = animation.values
    if len(values) == 2 and animation.repeat_count in (None, 1, "1") and not animation.key_times:
        start = _opacity_float(values[0])
        end = _opacity_float(values[-1])
        return (start <= 0.0 and end >= 0.999) or (end <= 0.0 and start >= 0.999)

    if len(values) != 3:
        return False
    if animation.calc_mode == CalcMode.DISCRETE:
        return False
    if animation.key_splines:
        return False
    if animation.key_times and [round(value, 6) for value in animation.key_times] != [0.0, 0.5, 1.0]:
        return False

    start = _opacity_float(values[0])
    peak = _opacity_float(values[1])
    end = _opacity_float(values[2])
    return abs(start - end) <= 1e-6 and start <= 0.0 and peak > start


def _opacity_float(value: str) -> float:
    return parse_authored_opacity(value)
