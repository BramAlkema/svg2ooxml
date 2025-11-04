"""Generate PowerPoint animation timing XML from animation definitions.

DEPRECATED: This module is deprecated and will be removed in a future release.
Use `svg2ooxml.drawingml.animation.DrawingMLAnimationWriter` instead.

The new implementation provides:
- Modular handler-based architecture
- lxml-based XML generation (no string concatenation)
- Better testability and maintainability
- Improved performance

Migration:
    Old: from svg2ooxml.drawingml.animation_writer import DrawingMLAnimationWriter
    New: from svg2ooxml.drawingml.animation import DrawingMLAnimationWriter

API remains compatible.
"""

from __future__ import annotations

import warnings

# Emit deprecation warning when this module is imported
warnings.warn(
    "svg2ooxml.drawingml.animation_writer is deprecated. "
    "Use svg2ooxml.drawingml.animation instead.",
    DeprecationWarning,
    stacklevel=2,
)

import re
from typing import Any, Mapping, Sequence, TYPE_CHECKING
from xml.sax.saxutils import escape

from svg2ooxml.color.utils import color_to_hex
from svg2ooxml.common.interpolation import BezierEasing
from svg2ooxml.common.geometry.paths import PathParseError, parse_path_data
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationScene,
    AnimationType,
    FillMode,
    CalcMode,
    TransformType,
)
from svg2ooxml.common.units import UnitConverter

if TYPE_CHECKING:
    from svg2ooxml.core.tracing import ConversionTracer


_UNIT_CONVERTER = UnitConverter()

_FADE_ATTRIBUTES = {"opacity", "fill-opacity", "stroke-opacity"}
_COLOR_ATTRIBUTES = {
    "fill",
    "stroke",
    "stop-color",
    "stopcolor",
    "flood-color",
    "lighting-color",
}
_COLOR_ATTR_NAME_MAP = {
    "fill": "fillClr",
    "stroke": "lnClr",
    "stop-color": "fillClr",
    "stopcolor": "fillClr",
    "flood-color": "fillClr",
    "lighting-color": "fillClr",
}
_ATTRIBUTE_NAME_OVERRIDES = {
    "x": "ppt_x",
    "x1": "ppt_x",
    "x2": "ppt_x",
    "y": "ppt_y",
    "y1": "ppt_y",
    "y2": "ppt_y",
    "cx": "ppt_x",
    "cy": "ppt_y",
    "dx": "ppt_x",
    "dy": "ppt_y",
    "fx": "ppt_x",
    "fy": "ppt_y",
    "left": "ppt_x",
    "top": "ppt_y",
    "right": "ppt_x",
    "bottom": "ppt_y",
    "width": "ppt_w",
    "height": "ppt_h",
    "w": "ppt_w",
    "h": "ppt_h",
    "rx": "ppt_w",
    "ry": "ppt_h",
    "rotate": "ppt_angle",
    "rotation": "ppt_angle",
    "angle": "ppt_angle",
    "stroke-width": "ln_w",
}
_AXIS_MAP = {
    "ppt_x": "x",
    "ppt_y": "y",
    "ppt_w": "width",
    "ppt_h": "height",
    "ln_w": "width",
}
_ANGLE_ATTRIBUTES = {"angle", "rotation", "rotate", "ppt_angle"}
_SVG2_ANIMATION_NS = "http://svg2ooxml.dev/ns/animation"


class DrawingMLAnimationWriter:
    """Render a subset of animation definitions as DrawingML timing."""

    def __init__(self) -> None:
        self._id_counter = 1000  # Offset to avoid collisions with shape ids

    def build(
        self,
        animations: Sequence[AnimationDefinition],
        timeline: Sequence[AnimationScene],
        *,
        tracer: "ConversionTracer | None" = None,
        options: Mapping[str, Any] | None = None,
    ) -> str:
        """Return a <p:timing> fragment or an empty string when unsupported."""
        options = dict(options or {})
        fragments: list[str] = []
        last_skip_reason: str | None = None
        for animation in animations:
            fragment, fragment_meta = self._build_animation(animation, options)
            if fragment:
                fragments.append(fragment)
                if tracer is not None:
                    event_meta = {
                        "element_id": animation.element_id,
                        "animation_type": animation.animation_type.value,
                        "attribute": animation.target_attribute,
                        "fallback_mode": options.get("fallback_mode", "native"),
                    }
                    if fragment_meta and "max_spline_error" in fragment_meta:
                        event_meta["max_spline_error"] = fragment_meta["max_spline_error"]
                    tracer.record_stage_event(
                        stage="animation",
                        action="fragment_emitted",
                        metadata=event_meta,
                    )
            elif tracer is not None:
                metadata = {
                    "element_id": animation.element_id,
                    "animation_type": animation.animation_type.value,
                    "attribute": animation.target_attribute,
                    "fallback_mode": options.get("fallback_mode", "native"),
                }
                if fragment_meta:
                    metadata.update(fragment_meta)
                    if fragment_meta.get("reason"):
                        last_skip_reason = fragment_meta["reason"]
                tracer.record_stage_event(
                    stage="animation",
                    action="fragment_skipped",
                    metadata=metadata,
                )

        if not fragments:
            if tracer is not None and animations:
                metadata = {
                    "reason": "no_supported_animations",
                    "animation_count": len(animations),
                    "fallback_mode": options.get("fallback_mode", "native"),
                }
                if last_skip_reason:
                    metadata["skip_reason"] = last_skip_reason
                tracer.record_stage_event(
                    stage="animation",
                    action="fragment_bundle_skipped",
                    metadata=metadata,
                )
            return ""

        child_nodes = "\n".join(fragments)
        timing_id = self._next_id()

        if tracer is not None:
            tracer.record_stage_event(
                stage="animation",
                action="fragment_bundle_emitted",
                metadata={
                    "animation_count": len(fragments),
                    "timeline_frames": len(timeline),
                    "fallback_mode": options.get("fallback_mode", "native"),
                },
            )

        return (
            "    <p:timing>\n"
            "        <p:tnLst>\n"
            f'            <p:par>\n'
            f'                <p:cTn id="{timing_id}" dur="indefinite" restart="always">\n'
            "                    <p:childTnLst>\n"
            f"{child_nodes}\n"
            "                    </p:childTnLst>\n"
            "                </p:cTn>\n"
            "            </p:par>\n"
            "        </p:tnLst>\n"
            "    </p:timing>"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_animation(
        self,
        animation: AnimationDefinition,
        options: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        max_error = self._estimate_max_error(animation)
        skip_reason = self._policy_skip_reason(animation, options, max_error)
        if skip_reason:
            metadata: dict[str, Any] = {"reason": skip_reason}
            if max_error > 0:
                metadata["max_spline_error"] = round(max_error, 6)
            return "", metadata

        metadata: dict[str, Any] | None = None
        if max_error > 0:
            metadata = {"max_spline_error": round(max_error, 6)}

        fragment: str
        if animation.animation_type == AnimationType.SET:
            fragment = self._build_set_animation(animation, options)
        elif animation.animation_type == AnimationType.ANIMATE_COLOR:
            fragment = self._build_color_animation(animation, options)
        elif animation.animation_type == AnimationType.ANIMATE:
            fragment = self._build_property_animation(animation, options)
        elif animation.animation_type == AnimationType.ANIMATE_TRANSFORM:
            fragment = self._build_transform_animation(animation, options)
        elif animation.animation_type == AnimationType.ANIMATE_MOTION:
            fragment = self._build_motion_animation(animation, options)
        else:
            fragment = ""

        return fragment, metadata

    def _build_property_animation(self, animation: AnimationDefinition, options: Mapping[str, Any]) -> str:
        attribute = (animation.target_attribute or "").lower()
        if attribute in _FADE_ATTRIBUTES:
            return self._build_opacity_animation(animation)
        if attribute in _COLOR_ATTRIBUTES:
            return self._build_color_animation(animation, options)
        return self._build_numeric_animation(animation, options)

    def _build_opacity_animation(self, animation: AnimationDefinition) -> str:
        attribute = (animation.target_attribute or "").lower()
        if attribute not in _FADE_ATTRIBUTES:
            return ""

        duration_ms = self._seconds_to_ms(animation.timing.duration)
        if duration_ms is None:
            return ""

        delay_ms = self._seconds_to_ms(animation.timing.begin) or 0
        repeat_attr = self._repeat_attribute(animation)
        easing_attr = self._easing_attributes(animation)
        target_shape = animation.element_id
        target_opacity = self._target_opacity(animation)

        par_id, behavior_id = self._allocate_ids()

        return (
            f'                        <p:par>\n'
            f'                            <p:cTn id="{par_id}" dur="{duration_ms}" fill="hold">\n'
            f'                                <p:stCondLst>\n'
            f'                                    <p:cond delay="{delay_ms}"/>\n'
            f'                                </p:stCondLst>\n'
            f'                                <p:childTnLst>\n'
            f'                                    <a:animEffect>\n'
            f'                                        <a:cBhvr>\n'
            f'                                            <a:cTn id="{behavior_id}" dur="{duration_ms}" fill="hold"{repeat_attr}{easing_attr}/>\n'
            f'                                            <a:tgtEl>\n'
            f'                                                <a:spTgt spid="{target_shape}"/>\n'
            f'                                            </a:tgtEl>\n'
            f'                                        </a:cBhvr>\n'
            f'                                        <a:transition in="1" out="0"/>\n'
            f'                                        <a:filter>\n'
            f'                                            <a:fade opacity="{target_opacity}"/>\n'
            f'                                        </a:filter>\n'
            f'                                    </a:animEffect>\n'
            f'                                </p:childTnLst>\n'
            f'                            </p:cTn>\n'
            f'                        </p:par>'
        )

    def _build_transform_animation(self, animation: AnimationDefinition, options: Mapping[str, Any]) -> str:
        if animation.transform_type not in {
            TransformType.SCALE,
            TransformType.ROTATE,
            TransformType.TRANSLATE,
        }:
            return ""

        duration_ms = self._seconds_to_ms(animation.timing.duration)
        if duration_ms is None:
            return ""

        delay_ms = self._seconds_to_ms(animation.timing.begin) or 0
        repeat_attr = self._repeat_attribute(animation)
        easing_attr = self._easing_attributes(animation)
        par_id, behavior_id = self._allocate_ids()
        target_shape = animation.element_id

        if animation.transform_type == TransformType.SCALE:
            start = self._parse_scale_pair(animation.values[0] if animation.values else "1")
            end = self._parse_scale_pair(animation.values[-1] if animation.values else "1")
            tav_list, tav_needs_ns = self._build_scale_tav_list(animation, duration_ms)
            tav_block = (
                f'                                        <a:tavLst>\n'
                f'{tav_list}\n'
                f'                                        </a:tavLst>\n'
            ) if tav_list else ""
            anim_tag = "<a:animScale"
            if tav_needs_ns:
                anim_tag += f' xmlns:svg2="{_SVG2_ANIMATION_NS}"'
            anim_tag += ">"
            inner = (
                f'                                    {anim_tag}\n'
                f'                                        <a:cBhvr>\n'
                f'                                            <a:cTn id="{behavior_id}" dur="{duration_ms}" fill="hold"{repeat_attr}{easing_attr}/>\n'
                f'                                            <a:tgtEl>\n'
                f'                                                <a:spTgt spid="{target_shape}"/>\n'
                f'                                            </a:tgtEl>\n'
                f'                                        </a:cBhvr>\n'
                f'                                        <a:from>\n'
                f'                                            <a:pt x="{self._format_float(start[0])}" y="{self._format_float(start[1])}"/>\n'
                f'                                        </a:from>\n'
                f'                                        <a:to>\n'
                f'                                            <a:pt x="{self._format_float(end[0])}" y="{self._format_float(end[1])}"/>\n'
                f'                                        </a:to>\n'
                f'{tav_block}'
                f'                                    </a:animScale>'
            )
        elif animation.transform_type == TransformType.ROTATE:
            start_angle = self._parse_angle(animation.values[0] if animation.values else "0")
            end_angle = self._parse_angle(animation.values[-1] if animation.values else "0")
            rotation_delta = int(round((end_angle - start_angle) * 60000))
            tav_list, tav_needs_ns = self._build_rotate_tav_list(animation, duration_ms, start_angle)
            tav_block = (
                f'                                        <a:tavLst>\n'
                f'{tav_list}\n'
                f'                                        </a:tavLst>\n'
            ) if tav_list else ""
            anim_tag = "<a:animRot"
            if tav_needs_ns:
                anim_tag += f' xmlns:svg2="{_SVG2_ANIMATION_NS}"'
            anim_tag += ">"
            inner = (
                f'                                    {anim_tag}\n'
                f'                                        <a:cBhvr>\n'
                f'                                            <a:cTn id="{behavior_id}" dur="{duration_ms}" fill="hold"{repeat_attr}{easing_attr}/>\n'
                f'                                            <a:tgtEl>\n'
                f'                                                <a:spTgt spid="{target_shape}"/>\n'
                f'                                            </a:tgtEl>\n'
                f'                                        </a:cBhvr>\n'
                f'                                        <a:by val="{rotation_delta}"/>\n'
                f'{tav_block}'
                f'                                    </a:animRot>'
            )
        else:  # TRANSLATE
            start = self._parse_translation_pair(animation.values[0] if animation.values else "0 0")
            end = self._parse_translation_pair(animation.values[-1] if animation.values else "0 0")
            dx = self._px_to_emu(end[0] - start[0], axis="x")
            dy = self._px_to_emu(end[1] - start[1], axis="y")
            inner = (
                f'                                    <a:animMotion>\n'
                f'                                        <a:cBhvr>\n'
                f'                                            <a:cTn id="{behavior_id}" dur="{duration_ms}" fill="hold"{repeat_attr}{easing_attr}/>\n'
                f'                                            <a:tgtEl>\n'
                f'                                                <a:spTgt spid="{target_shape}"/>\n'
                f'                                            </a:tgtEl>\n'
                f'                                        </a:cBhvr>\n'
                f'                                        <a:by x="{dx}" y="{dy}"/>\n'
                f'                                    </a:animMotion>'
            )

        return (
            f'                        <p:par>\n'
            f'                            <p:cTn id="{par_id}" dur="{duration_ms}" fill="hold">\n'
            f'                                <p:stCondLst>\n'
            f'                                    <p:cond delay="{delay_ms}"/>\n'
            f'                                </p:stCondLst>\n'
            f'                                <p:childTnLst>\n'
            f'{inner}\n'
            f'                                </p:childTnLst>\n'
            f'                            </p:cTn>\n'
            f'                        </p:par>'
        )

    def _build_numeric_animation(self, animation: AnimationDefinition, options: Mapping[str, Any]) -> str:
        duration_ms = self._seconds_to_ms(animation.timing.duration)
        if duration_ms is None:
            return ""

        delay_ms = self._seconds_to_ms(animation.timing.begin) or 0
        repeat_attr = self._repeat_attribute(animation)
        easing_attr = self._easing_attributes(animation)
        par_id, behavior_id = self._allocate_ids()
        target_shape = animation.element_id
        attribute = self._attribute_name(animation.target_attribute)

        if not animation.values:
            return ""

        from_value = animation.values[0]
        to_value = animation.values[-1]

        normalized_from = self._normalize_numeric_value(attribute, from_value)
        normalized_to = self._normalize_numeric_value(attribute, to_value)

        from_block = (
            f'                                        <a:from>\n'
            f'                                            <a:val val="{self._escape_attr_value(normalized_from)}"/>\n'
            f'                                        </a:from>\n'
        )
        to_block = (
            f'                                        <a:to>\n'
            f'                                            <a:val val="{self._escape_attr_value(normalized_to)}"/>\n'
            f'                                        </a:to>\n'
        )

        tav_list, tav_needs_ns = self._build_numeric_tav_list(animation, duration_ms, attribute, options)
        tav_block = (
            f'                                        <a:tavLst>\n'
            f'{tav_list}\n'
            f'                                        </a:tavLst>\n'
        ) if tav_list else ""

        anim_tag = "<a:anim"
        if tav_needs_ns:
            anim_tag += f' xmlns:svg2="{_SVG2_ANIMATION_NS}"'
        anim_tag += ">"

        inner = (
            f'                                    {anim_tag}\n'
            f'                                        <a:cBhvr>\n'
            f'                                            <a:cTn id="{behavior_id}" dur="{duration_ms}" fill="hold"{repeat_attr}{easing_attr}/>\n'
            f'                                            <a:tgtEl>\n'
            f'                                                <a:spTgt spid="{target_shape}"/>\n'
            f'                                            </a:tgtEl>\n'
            f'                                            <a:attrNameLst>\n'
            f'                                                <a:attrName>{attribute}</a:attrName>\n'
            f'                                            </a:attrNameLst>\n'
            f'                                        </a:cBhvr>\n'
            f'{from_block}'
            f'{to_block}'
            f'{tav_block}'
            f'                                    </a:anim>'
        )

        return (
            f'                        <p:par>\n'
            f'                            <p:cTn id="{par_id}" dur="{duration_ms}" fill="hold">\n'
            f'                                <p:stCondLst>\n'
            f'                                    <p:cond delay="{delay_ms}"/>\n'
            f'                                </p:stCondLst>\n'
            f'                                <p:childTnLst>\n'
            f'{inner}\n'
            f'                                </p:childTnLst>\n'
            f'                            </p:cTn>\n'
            f'                        </p:par>'
        )

    def _build_color_animation(self, animation: AnimationDefinition, options: Mapping[str, Any]) -> str:
        duration_ms = self._seconds_to_ms(animation.timing.duration)
        if duration_ms is None:
            return ""

        delay_ms = self._seconds_to_ms(animation.timing.begin) or 0
        repeat_attr = self._repeat_attribute(animation)
        easing_attr = self._easing_attributes(animation)
        par_id, behavior_id = self._allocate_ids()
        target_shape = animation.element_id
        attribute = self._color_attribute_name(animation.target_attribute)

        if not animation.values:
            return ""

        from_value = animation.values[0]
        to_value = animation.values[-1]
        from_hex = self._to_hex_color(from_value)
        to_hex = self._to_hex_color(to_value)

        tav_list, tav_needs_ns = self._build_color_tav_list(animation, duration_ms, options)
        tav_block = (
            f'                                        <a:tavLst>\n'
            f'{tav_list}\n'
            f'                                        </a:tavLst>\n'
        ) if tav_list else ""

        anim_tag = "<a:animClr"
        if tav_needs_ns:
            anim_tag += f' xmlns:svg2="{_SVG2_ANIMATION_NS}"'
        anim_tag += ">"

        inner = (
            f'                                    {anim_tag}\n'
            f'                                        <a:cBhvr>\n'
            f'                                            <a:cTn id="{behavior_id}" dur="{duration_ms}" fill="hold"{repeat_attr}{easing_attr}/>\n'
            f'                                            <a:tgtEl>\n'
            f'                                                <a:spTgt spid="{target_shape}"/>\n'
            f'                                            </a:tgtEl>\n'
            f'                                            <a:attrNameLst>\n'
            f'                                                <a:attrName>{attribute}</a:attrName>\n'
            f'                                            </a:attrNameLst>\n'
            f'                                        </a:cBhvr>\n'
            f'                                        <a:from>\n'
            f'                                            <a:srgbClr val="{from_hex}"/>\n'
            f'                                        </a:from>\n'
            f'                                        <a:to>\n'
            f'                                            <a:srgbClr val="{to_hex}"/>\n'
            f'                                        </a:to>\n'
            f'{tav_block}'
            f'                                    </a:animClr>'
        )

        return (
            f'                        <p:par>\n'
            f'                            <p:cTn id="{par_id}" dur="{duration_ms}" fill="hold">\n'
            f'                                <p:stCondLst>\n'
            f'                                    <p:cond delay="{delay_ms}"/>\n'
            f'                                </p:stCondLst>\n'
            f'                                <p:childTnLst>\n'
            f'{inner}\n'
            f'                                </p:childTnLst>\n'
            f'                            </p:cTn>\n'
            f'                        </p:par>'
        )

    def _build_set_animation(self, animation: AnimationDefinition, options: Mapping[str, Any]) -> str:
        delay_ms = self._seconds_to_ms(animation.timing.begin) or 0
        duration_ms = self._seconds_to_ms(animation.timing.duration)
        if duration_ms is None or duration_ms <= 0:
            duration_ms = 1

        repeat_attr = self._repeat_attribute(animation)
        par_id, behavior_id = self._allocate_ids()
        target_shape = animation.element_id

        attribute = (animation.target_attribute or "").lower()
        attr_name = self._attribute_name(attribute)

        value = animation.values[-1] if animation.values else ""
        if attribute in _COLOR_ATTRIBUTES or animation.animation_type == AnimationType.ANIMATE_COLOR:
            value_block = (
                f'                                        <a:to>\n'
                f'                                            <a:srgbClr val="{self._to_hex_color(value)}"/>\n'
                f'                                        </a:to>\n'
            )
        else:
            normalized_value = self._normalize_numeric_value(attr_name, value)
            value_block = (
                f'                                        <a:to>\n'
                f'                                            <a:val val="{self._escape_attr_value(normalized_value)}"/>\n'
                f'                                        </a:to>\n'
            )

        inner = (
            f'                                    <a:set>\n'
            f'                                        <a:cBhvr>\n'
            f'                                            <a:cTn id="{behavior_id}" dur="{duration_ms}" fill="hold"{repeat_attr}/>\n'
            f'                                            <a:tgtEl>\n'
            f'                                                <a:spTgt spid="{target_shape}"/>\n'
            f'                                            </a:tgtEl>\n'
            f'                                            <a:attrNameLst>\n'
            f'                                                <a:attrName>{attr_name}</a:attrName>\n'
            f'                                            </a:attrNameLst>\n'
            f'                                        </a:cBhvr>\n'
            f'{value_block}'
            f'                                    </a:set>'
        )

        return (
            f'                        <p:par>\n'
            f'                            <p:cTn id="{par_id}" dur="{duration_ms}" fill="hold">\n'
            f'                                <p:stCondLst>\n'
            f'                                    <p:cond delay="{delay_ms}"/>\n'
            f'                                </p:stCondLst>\n'
            f'                                <p:childTnLst>\n'
            f'{inner}\n'
            f'                                </p:childTnLst>\n'
            f'                            </p:cTn>\n'
            f'                        </p:par>'
        )

    def _build_motion_animation(self, animation: AnimationDefinition, options: Mapping[str, Any]) -> str:
        path_value = animation.values[0] if animation.values else ""
        points = self._parse_motion_path_points(path_value)
        if len(points) < 2:
            return ""

        duration_ms = self._seconds_to_ms(animation.timing.duration)
        if duration_ms is None:
            return ""

        delay_ms = self._seconds_to_ms(animation.timing.begin) or 0
        repeat_attr = self._repeat_attribute(animation)
        easing_attr = self._easing_attributes(animation)
        par_id, behavior_id = self._allocate_ids()
        target_shape = animation.element_id

        point_entries = []
        for x, y in points:
            x_emu = self._px_to_emu(x, axis="x")
            y_emu = self._px_to_emu(y, axis="y")
            point_entries.append(f'                                        <a:pt x="{x_emu}" y="{y_emu}"/>')

        pt_lst = "\n".join(point_entries)

        return (
            f'                        <p:par>\n'
            f'                            <p:cTn id="{par_id}" dur="{duration_ms}" fill="hold">\n'
            f'                                <p:stCondLst>\n'
            f'                                    <p:cond delay="{delay_ms}"/>\n'
            f'                                </p:stCondLst>\n'
            f'                                <p:childTnLst>\n'
            f'                                    <a:animMotion>\n'
            f'                                        <a:cBhvr>\n'
            f'                                            <a:cTn id="{behavior_id}" dur="{duration_ms}" fill="hold"{repeat_attr}{easing_attr}/>\n'
            f'                                            <a:tgtEl>\n'
            f'                                                <a:spTgt spid="{target_shape}"/>\n'
            f'                                            </a:tgtEl>\n'
            f'                                        </a:cBhvr>\n'
            f'                                        <a:ptLst>\n'
            f'{pt_lst}\n'
            f'                                        </a:ptLst>\n'
            f'                                    </a:animMotion>\n'
            f'                                </p:childTnLst>\n'
            f'                            </p:cTn>\n'
            f'                        </p:par>'
        )

    def _seconds_to_ms(self, value: float) -> int | None:
        if value == float("inf"):
            return None
        milliseconds = int(round(max(0.0, value) * 1000))
        return milliseconds

    def _repeat_attribute(self, animation: AnimationDefinition) -> str:
        repeat = animation.timing.repeat_count
        if repeat == "indefinite":
            return ' repeatCount="indefinite"'
        try:
            repeat_int = int(repeat)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return ""
        if repeat_int <= 1:
            return ""
        return f' repeatCount="{repeat_int}"'

    def _target_opacity(self, animation: AnimationDefinition) -> str:
        if animation.values:
            return animation.values[-1]
        if animation.timing.fill_mode == FillMode.FREEZE:
            return "1"
        return "0"

    def _next_id(self) -> int:
        current = self._id_counter
        self._id_counter += 1
        return current

    def _allocate_ids(self) -> tuple[int, int]:
        par_id = self._next_id()
        behavior_id = self._next_id()
        return par_id, behavior_id

    def _easing_attributes(self, animation: AnimationDefinition) -> str:
        splines = animation.key_splines or []
        if not splines or not self._is_spline_mode(animation):
            return ""
        spline = splines[0]
        if len(spline) != 4:
            return ""
        _, y1, _, y2 = spline
        accel = self._clamp_percentage(y1)
        decel = self._clamp_percentage(1.0 - y2)
        parts: list[str] = []
        if accel > 0:
            parts.append(f' accel="{accel}"')
        if decel > 0:
            parts.append(f' decel="{decel}"')
        return "".join(parts)
    
    def _is_spline_mode(self, animation: AnimationDefinition) -> bool:
        calc_mode = animation.calc_mode
        if isinstance(calc_mode, CalcMode):
            return calc_mode == CalcMode.SPLINE
        if isinstance(calc_mode, str):
            return calc_mode.lower() == "spline"
        return False

    def _parse_scale_pair(self, value: str) -> tuple[float, float]:
        numbers = self._parse_numeric_list(value)
        if not numbers:
            return (1.0, 1.0)
        if len(numbers) == 1:
            return (numbers[0], numbers[0])
        return (numbers[0], numbers[1])

    def _parse_angle(self, value: str) -> float:
        numbers = self._parse_numeric_list(value)
        return numbers[0] if numbers else 0.0

    def _parse_translation_pair(self, value: str) -> tuple[float, float]:
        numbers = self._parse_numeric_list(value)
        if len(numbers) >= 2:
            return (numbers[0], numbers[1])
        if len(numbers) == 1:
            return (numbers[0], 0.0)
        return (0.0, 0.0)

    def _parse_numeric_list(self, value: str) -> list[float]:
        if not value:
            return []
        tokens = re.findall(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", value)
        result: list[float] = []
        for token in tokens:
            try:
                result.append(float(token))
            except ValueError:
                continue
        return result

    def _format_float(self, value: float) -> str:
        formatted = f"{value:.6f}"
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        return formatted or "0"

    def _clamp_percentage(self, value: float) -> int:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0
        numeric = max(0.0, min(1.0, numeric))
        return int(round(numeric * 100000))

    def _px_to_emu(self, value: float, *, axis: str | None = None) -> int:
        return int(round(_UNIT_CONVERTER.to_emu(value, axis=axis)))

    def _parse_motion_path_points(self, value: str) -> list[tuple[float, float]]:
        if not value:
            return []

        try:
            segments = parse_path_data(value)
        except PathParseError:
            return []

        if not segments:
            return []

        points: list[Point] = []
        first_segment = segments[0]
        points.append(first_segment.start)

        for segment in segments:
            if isinstance(segment, LineSegment):
                points.append(segment.end)
            elif isinstance(segment, BezierSegment):
                points.extend(self._sample_bezier(segment))

        return self._dedupe_points(points)

    def _dedupe_points(self, points: list[Point]) -> list[tuple[float, float]]:
        deduped: list[tuple[float, float]] = []
        for point in points:
            pair = (point.x, point.y)
            if not deduped or (abs(deduped[-1][0] - pair[0]) > 1e-6 or abs(deduped[-1][1] - pair[1]) > 1e-6):
                deduped.append(pair)
        return deduped

    def _sample_bezier(self, segment: BezierSegment, *, steps: int = 20) -> list[Point]:
        samples: list[Point] = []
        for index in range(1, steps + 1):
            t = index / steps
            samples.append(self._bezier_point(segment, t))
        return samples

    def _bezier_point(self, segment: BezierSegment, t: float) -> Point:
        mt = 1.0 - t
        x = (
            mt ** 3 * segment.start.x
            + 3 * mt ** 2 * t * segment.control1.x
            + 3 * mt * t ** 2 * segment.control2.x
            + t ** 3 * segment.end.x
        )
        y = (
            mt ** 3 * segment.start.y
            + 3 * mt ** 2 * t * segment.control1.y
            + 3 * mt * t ** 2 * segment.control2.y
            + t ** 3 * segment.end.y
        )
        return Point(x, y)

    def _normalize_numeric_value(self, attribute: str, value: str) -> str:
        attr = attribute.lower()
        axis = _AXIS_MAP.get(attr)
        stripped = value.strip()
        if not stripped:
            return value

        if attr in _ANGLE_ATTRIBUTES:
            number = self._parse_single_number(stripped)
            if number is None:
                return value
            return str(int(round(number * 60000)))

        if axis is not None:
            try:
                emu = _UNIT_CONVERTER.to_emu(stripped, axis=axis)
                return str(int(round(emu)))
            except Exception:
                return value

        return value

    def _parse_single_number(self, value: str) -> float | None:
        try:
            return float(value)
        except ValueError:
            match = re.match(r"^\s*([-+]?[0-9]*\.?[0-9]+)", value)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    return None
        return None

    def _resolve_key_times(self, values: Sequence[str], key_times: Sequence[float] | None) -> list[float]:
        if not values:
            return []
        if key_times is None or len(key_times) != len(values):
            steps = len(values) - 1
            if steps <= 0:
                return [0.0]
            return [index / steps for index in range(len(values))]
        return list(key_times)

    def _tav_metadata(
        self,
        index: int,
        key_times: Sequence[float],
        duration_ms: int,
        splines: Sequence[list[float]],
    ) -> tuple[str, bool, int, int]:
        if index == 0 or not splines or index - 1 >= len(splines) or index >= len(key_times):
            return ("", False, 0, 0)

        spline = splines[index - 1]
        accel_val, decel_val = self._segment_accel_decel(spline)
        segment_duration = max(
            0,
            int(round((key_times[index] - key_times[index - 1]) * duration_ms)),
        )

        metadata_parts: list[str] = []
        if accel_val > 0:
            metadata_parts.append(f'svg2:accel="{accel_val}"')
        if decel_val > 0:
            metadata_parts.append(f'svg2:decel="{decel_val}"')
        metadata_parts.append(f'svg2:spline="{self._format_spline(spline)}"')
        metadata_parts.append(f'svg2:segDur="{segment_duration}"')
        return (" " + " ".join(metadata_parts), True, accel_val, decel_val)

    def _build_numeric_tav_list(
        self,
        animation: AnimationDefinition,
        duration_ms: int,
        attribute: str,
        options: Mapping[str, Any],
    ) -> tuple[str, bool]:
        values = animation.values
        if not values or len(values) <= 2 and not animation.key_times:
            return ("", False)

        key_times = self._resolve_key_times(values, animation.key_times)

        entries: list[str] = []
        uses_ns = False
        splines = animation.key_splines or []
        for index, (time_fraction, raw_value) in enumerate(zip(key_times, values)):
            tm = int(round(max(0.0, min(1.0, time_fraction)) * duration_ms))
            normalized = self._normalize_numeric_value(attribute, raw_value)
            metadata, metadata_ns, accel_val, decel_val = self._tav_metadata(index, key_times, duration_ms, splines)
            if metadata_ns:
                uses_ns = True
            tav_pr = self._tav_pr_fragment(accel_val, decel_val)
            parts = [f'                                            <a:tav tm="{tm}"{metadata}>']
            if tav_pr:
                parts.append(f'                                                {tav_pr}')
            parts.append(
                f'                                                <a:val val="{self._escape_attr_value(normalized)}"/>'
            )
            parts.append('                                            </a:tav>')
            entries.append("\n".join(parts))
        return ("\n".join(entries), uses_ns)

    def _build_color_tav_list(
        self,
        animation: AnimationDefinition,
        duration_ms: int,
        options: Mapping[str, Any],
    ) -> tuple[str, bool]:
        values = animation.values
        if not values or len(values) <= 2 and not animation.key_times:
            return ("", False)

        key_times = self._resolve_key_times(values, animation.key_times)

        entries: list[str] = []
        uses_ns = False
        splines = animation.key_splines or []
        for index, (time_fraction, raw_value) in enumerate(zip(key_times, values)):
            tm = int(round(max(0.0, min(1.0, time_fraction)) * duration_ms))
            hex_value = self._to_hex_color(raw_value)
            metadata, metadata_ns, accel_val, decel_val = self._tav_metadata(index, key_times, duration_ms, splines)
            if metadata_ns:
                uses_ns = True
            tav_pr = self._tav_pr_fragment(accel_val, decel_val)
            parts = [f'                                            <a:tav tm="{tm}"{metadata}>']
            if tav_pr:
                parts.append(f'                                                {tav_pr}')
            parts.append(
                f'                                                <a:val>\n'
                f'                                                    <a:srgbClr val="{hex_value}"/>\n'
                f'                                                </a:val>'
            )
            parts.append('                                            </a:tav>')
            entries.append("\n".join(parts))
        return ("\n".join(entries), uses_ns)

    def _build_scale_tav_list(
        self,
        animation: AnimationDefinition,
        duration_ms: int,
    ) -> tuple[str, bool]:
        values = animation.values
        if not values or len(values) <= 2 and not animation.key_times:
            return ("", False)

        key_times = self._resolve_key_times(values, animation.key_times)
        entries: list[str] = []
        uses_ns = False
        splines = animation.key_splines or []

        for index, (time_fraction, raw_value) in enumerate(zip(key_times, values)):
            tm = int(round(max(0.0, min(1.0, time_fraction)) * duration_ms))
            scale_x, scale_y = self._parse_scale_pair(raw_value)
            metadata, metadata_ns, accel_val, decel_val = self._tav_metadata(index, key_times, duration_ms, splines)
            if metadata_ns:
                uses_ns = True
            tav_pr = self._tav_pr_fragment(accel_val, decel_val)
            parts = [f'                                            <a:tav tm="{tm}"{metadata}>']
            if tav_pr:
                parts.append(f'                                                {tav_pr}')
            parts.append(
                f'                                                <a:val>\n'
                f'                                                    <a:pt x="{self._format_float(scale_x)}" y="{self._format_float(scale_y)}"/>\n'
                f'                                                </a:val>'
            )
            parts.append('                                            </a:tav>')
            entries.append("\n".join(parts))

        return ("\n".join(entries), uses_ns)

    def _build_rotate_tav_list(
        self,
        animation: AnimationDefinition,
        duration_ms: int,
        start_angle: float,
    ) -> tuple[str, bool]:
        values = animation.values
        if not values or len(values) <= 2 and not animation.key_times:
            return ("", False)

        key_times = self._resolve_key_times(values, animation.key_times)
        entries: list[str] = []
        uses_ns = False
        splines = animation.key_splines or []

        for index, (time_fraction, raw_value) in enumerate(zip(key_times, values)):
            tm = int(round(max(0.0, min(1.0, time_fraction)) * duration_ms))
            angle = self._parse_angle(raw_value)
            arc_delta = int(round((angle - start_angle) * 60000))
            metadata, metadata_ns, accel_val, decel_val = self._tav_metadata(index, key_times, duration_ms, splines)
            if metadata_ns:
                uses_ns = True
            tav_pr = self._tav_pr_fragment(accel_val, decel_val)
            parts = [f'                                            <a:tav tm="{tm}"{metadata}>']
            if tav_pr:
                parts.append(f'                                                {tav_pr}')
            parts.append(f'                                                <a:val val="{arc_delta}"/>')
            parts.append('                                            </a:tav>')
            entries.append("\n".join(parts))

        return ("\n".join(entries), uses_ns)

    def _attribute_name(self, attribute: str | None) -> str:
        if not attribute:
            return "style"
        attr = attribute.lower()
        return _ATTRIBUTE_NAME_OVERRIDES.get(attr, attr)

    def _color_attribute_name(self, attribute: str | None) -> str:
        if not attribute:
            return "fillClr"
        attr_lower = attribute.lower()
        return _COLOR_ATTR_NAME_MAP.get(attr_lower, attr_lower)

    def _to_hex_color(self, value: str | None) -> str:
        return color_to_hex(value, default="000000")

    def _escape_attr_value(self, value: str) -> str:
        return escape(value, {"\"": "&quot;"})

    def _tav_pr_fragment(self, accel: int, decel: int) -> str:
        attrs: list[str] = []
        if accel > 0:
            attrs.append(f'accel="{accel}"')
        if decel > 0:
            attrs.append(f'decel="{decel}"')
        if not attrs:
            return ""
        return f"<a:tavPr {' '.join(attrs)}/>"

    def _policy_skip_reason(
        self,
        animation: AnimationDefinition,
        options: Mapping[str, Any],
        max_error: float,
    ) -> str | None:
        fallback_mode = str(options.get("fallback_mode", "native")).lower()
        if fallback_mode != "native":
            return f"policy:fallback_mode={fallback_mode}"

        if animation.key_splines:
            allow_native_flag = self._coerce_bool_option(options.get("allow_native_splines"), True)
            if not allow_native_flag:
                return "policy:native_splines_disabled"

            threshold_value = options.get("max_spline_error")
            if threshold_value is not None:
                threshold = self._coerce_float_option(threshold_value, 0.0)
                if max_error > threshold:
                    return f"policy:spline_error>{threshold:.2f}"
        return None

    def _coerce_bool_option(self, value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return default

    def _coerce_float_option(self, value: Any, default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _estimate_spline_error(self, spline: list[float], *, samples: int = 20) -> float:
        if len(spline) != 4:
            return 0.0
        max_error = 0.0
        for index in range(1, samples):
            progress = index / samples
            eased = BezierEasing.evaluate(progress, spline)
            error = abs(eased - progress)
            max_error = max(max_error, error)
        return max_error

    def _estimate_max_error(self, animation: AnimationDefinition) -> float:
        if not animation.key_splines:
            return 0.0
        return max(self._estimate_spline_error(spline) for spline in animation.key_splines)

    def _segment_accel_decel(self, spline: list[float]) -> tuple[int, int]:
        if len(spline) != 4:
            return (0, 0)
        _, y1, _, y2 = spline
        accel = self._clamp_percentage(y1)
        decel = self._clamp_percentage(1.0 - y2)
        return accel, decel

    def _format_spline(self, spline: list[float]) -> str:
        formatted = ["{0:.4f}".format(max(0.0, min(1.0, value))) for value in spline]
        return ",".join(formatted)


__all__ = ["DrawingMLAnimationWriter"]
