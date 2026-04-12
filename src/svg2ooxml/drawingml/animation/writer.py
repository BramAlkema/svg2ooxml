"""DrawingML animation writer using handler architecture.

Orchestrates all animation handlers to convert SVG animations into
PowerPoint timing XML.  All handlers return ``etree._Element`` and the
writer calls ``to_string()`` exactly once at the end.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.xml_builder import NS_P, p_sub, to_string
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationScene,
    AnimationType,
    TransformType,
)

from .handlers import (
    AnimationHandler,
    ColorAnimationHandler,
    MotionAnimationHandler,
    NumericAnimationHandler,
    OpacityAnimationHandler,
    SetAnimationHandler,
    TransformAnimationHandler,
)
from .id_allocator import TimingIDAllocator
from .policy import AnimationPolicy
from .tav_builder import TAVBuilder
from .value_processors import ValueProcessor
from .xml_builders import AnimationXMLBuilder

if TYPE_CHECKING:
    from svg2ooxml.core.tracing import ConversionTracer

__all__ = ["DrawingMLAnimationWriter"]

_logger = logging.getLogger(__name__)
_PRESENTATION_NS = {"p": NS_P}
_ANIM_MOTION_TAG = f"{{{NS_P}}}animMotion"
_CBHVR_TAG = f"{{{NS_P}}}cBhvr"
_SP_TGT_TAG = f"{{{NS_P}}}spTgt"
_RCTR_TAG = f"{{{NS_P}}}rCtr"
_ATTR_NAME_LST_TAG = f"{{{NS_P}}}attrNameLst"
_ATTR_NAME_TAG = f"{{{NS_P}}}attrName"
_SIMPLE_RELATIVE_MOTION_RE = re.compile(
    r"^M\s+0(?:\.0+)?\s+0(?:\.0+)?\s+L\s+"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+E$"
)


@dataclass
class _MotionFragmentRecord:
    par: etree._Element
    child_tn_list: etree._Element
    motion: etree._Element
    behavior: etree._Element
    behavior_ctn: etree._Element
    target_shape: str
    dx: float
    dy: float
    additive: str | None
    attr_names: tuple[str, ...]
    origin: str
    path_edit_mode: str
    r_ang: str | None
    pts_types: str | None
    r_ctr: tuple[str, str] | None
    outer_signature: tuple[Any, ...]
    behavior_signature: tuple[Any, ...]


def _merge_concurrent_simple_motion_fragments(
    animation_elements: list[etree._Element],
) -> list[etree._Element]:
    groups: dict[tuple[Any, ...], list[_MotionFragmentRecord]] = {}
    for par in animation_elements:
        for record in _iter_simple_motion_fragments(par):
            key = (
                record.target_shape,
                record.outer_signature,
                record.behavior_signature,
            )
            groups.setdefault(key, []).append(record)

    for records in groups.values():
        compatible_groups: list[list[_MotionFragmentRecord]] = []
        for record in records:
            for subgroup in compatible_groups:
                if _motion_records_compatible(subgroup[0], record):
                    subgroup.append(record)
                    break
            else:
                compatible_groups.append([record])

        for subgroup in compatible_groups:
            if len(subgroup) < 2:
                continue
            _merge_motion_group(subgroup)

    merged_elements: list[etree._Element] = []
    for par in animation_elements:
        child_tn_list = par.find("./p:cTn/p:childTnLst", namespaces=_PRESENTATION_NS)
        if child_tn_list is None or len(child_tn_list):
            merged_elements.append(par)
    return merged_elements


def _iter_simple_motion_fragments(par: etree._Element) -> list[_MotionFragmentRecord]:
    outer_ctn = par.find("./p:cTn", namespaces=_PRESENTATION_NS)
    child_tn_list = par.find("./p:cTn/p:childTnLst", namespaces=_PRESENTATION_NS)
    if outer_ctn is None or child_tn_list is None:
        return []

    records: list[_MotionFragmentRecord] = []
    for child in child_tn_list:
        if child.tag != _ANIM_MOTION_TAG:
            continue
        record = _extract_simple_motion_fragment(
            par=par,
            outer_ctn=outer_ctn,
            child_tn_list=child_tn_list,
            motion=child,
        )
        if record is not None:
            records.append(record)
    return records


def _extract_simple_motion_fragment(
    *,
    par: etree._Element,
    outer_ctn: etree._Element,
    child_tn_list: etree._Element,
    motion: etree._Element,
) -> _MotionFragmentRecord | None:
    if motion.get("pathEditMode") != "relative":
        return None

    match = _SIMPLE_RELATIVE_MOTION_RE.fullmatch(motion.get("path", "").strip())
    if match is None:
        return None

    behavior = motion.find("./p:cBhvr", namespaces=_PRESENTATION_NS)
    behavior_ctn = motion.find("./p:cBhvr/p:cTn", namespaces=_PRESENTATION_NS)
    target = motion.find("./p:cBhvr/p:tgtEl/p:spTgt", namespaces=_PRESENTATION_NS)
    if behavior is None or behavior_ctn is None or target is None:
        return None

    target_shape = target.get("spid")
    if not target_shape:
        return None

    attr_names = tuple(
        attr_name.text or ""
        for attr_name in behavior.findall(
            "./p:attrNameLst/p:attrName",
            namespaces=_PRESENTATION_NS,
        )
        if attr_name.text
    )
    r_ctr = _read_r_ctr(motion)

    return _MotionFragmentRecord(
        par=par,
        child_tn_list=child_tn_list,
        motion=motion,
        behavior=behavior,
        behavior_ctn=behavior_ctn,
        target_shape=target_shape,
        dx=float(match.group(1)),
        dy=float(match.group(2)),
        additive=behavior.get("additive"),
        attr_names=attr_names,
        origin=motion.get("origin", "layout"),
        path_edit_mode=motion.get("pathEditMode", "relative"),
        r_ang=motion.get("rAng"),
        pts_types=motion.get("ptsTypes"),
        r_ctr=r_ctr,
        outer_signature=_timing_signature(
            outer_ctn,
            ignore_attrs={
                "id",
                "grpId",
                "presetID",
                "presetClass",
                "presetSubtype",
                "nodeType",
            },
        ),
        behavior_signature=(
            _attrs_signature(behavior, ignore={"rctx", "additive"}),
            _timing_signature(behavior_ctn, ignore_attrs={"id"}),
        ),
    )


def _motion_records_compatible(
    left: _MotionFragmentRecord,
    right: _MotionFragmentRecord,
) -> bool:
    if left.origin != right.origin:
        return False
    if left.path_edit_mode != right.path_edit_mode:
        return False
    if not _optional_values_compatible(left.r_ang, right.r_ang):
        return False
    if not _optional_values_compatible(left.pts_types, right.pts_types):
        return False
    if not _optional_values_compatible(left.r_ctr, right.r_ctr):
        return False
    return True


def _merge_motion_group(records: list[_MotionFragmentRecord]) -> None:
    anchor = _choose_motion_anchor(records)
    merged_dx = sum(record.dx for record in records)
    merged_dy = sum(record.dy for record in records)
    anchor.motion.set("path", _format_motion_path(merged_dx, merged_dy))
    anchor.motion.set("origin", anchor.origin)
    anchor.motion.set("pathEditMode", anchor.path_edit_mode)
    anchor.motion.attrib.pop("rAng", None)
    anchor.motion.attrib.pop("ptsTypes", None)
    _sync_r_ctr(anchor.motion, None)
    _sync_attr_name_list(anchor.behavior, [])
    anchor.behavior.attrib.pop("additive", None)

    for record in records:
        if record is anchor:
            continue
        record.child_tn_list.remove(record.motion)


def _choose_motion_anchor(records: list[_MotionFragmentRecord]) -> _MotionFragmentRecord:
    def score(record: _MotionFragmentRecord) -> tuple[int, int, int]:
        non_motion_children = sum(
            1 for child in record.child_tn_list if child.tag != _ANIM_MOTION_TAG
        )
        return (
            non_motion_children,
            -len(record.attr_names),
            -(1 if record.behavior.get("rctx") else 0),
        )

    return min(records, key=score)


def _merged_attr_names(records: list[_MotionFragmentRecord]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for record in records:
        for attr_name in record.attr_names:
            if attr_name in seen:
                continue
            seen.add(attr_name)
            merged.append(attr_name)
    return merged


def _sync_attr_name_list(c_bhvr: etree._Element, attr_names: list[str]) -> None:
    attr_name_lst = c_bhvr.find("./p:attrNameLst", namespaces=_PRESENTATION_NS)
    if attr_names:
        if attr_name_lst is None:
            attr_name_lst = p_sub(c_bhvr, "attrNameLst")
        for child in list(attr_name_lst):
            attr_name_lst.remove(child)
        for attr_name in attr_names:
            attr_elem = p_sub(attr_name_lst, "attrName")
            attr_elem.text = attr_name
    elif attr_name_lst is not None:
        c_bhvr.remove(attr_name_lst)

    if any(
        attr_name.startswith("ppt_") or attr_name.startswith("style.")
        for attr_name in attr_names
    ):
        c_bhvr.set("rctx", "PPT")
    else:
        c_bhvr.attrib.pop("rctx", None)


def _sync_r_ctr(
    motion: etree._Element,
    r_ctr: tuple[str, str] | None,
) -> None:
    existing = motion.find("./p:rCtr", namespaces=_PRESENTATION_NS)
    if r_ctr is None:
        if existing is not None:
            motion.remove(existing)
        return

    if existing is None:
        existing = p_sub(motion, "rCtr")
    existing.set("x", r_ctr[0])
    existing.set("y", r_ctr[1])


def _read_r_ctr(motion: etree._Element) -> tuple[str, str] | None:
    r_ctr = motion.find("./p:rCtr", namespaces=_PRESENTATION_NS)
    if r_ctr is None:
        return None
    return (r_ctr.get("x", "0"), r_ctr.get("y", "0"))


def _optional_values_compatible(left: Any, right: Any) -> bool:
    return left is None or right is None or left == right


def _attrs_signature(
    elem: etree._Element,
    *,
    ignore: set[str] | None = None,
) -> tuple[tuple[str, str], ...]:
    ignore = ignore or set()
    return tuple(
        sorted(
            (key, value)
            for key, value in elem.attrib.items()
            if key not in ignore
        )
    )


def _timing_signature(
    elem: etree._Element,
    *,
    ignore_attrs: set[str] | None = None,
) -> tuple[Any, ...]:
    ignore_attrs = ignore_attrs or set()
    return (
        _attrs_signature(elem, ignore=ignore_attrs),
        _child_xml(elem, "stCondLst"),
        _child_xml(elem, "endCondLst"),
        _child_xml(elem, "endSync"),
    )


def _child_xml(elem: etree._Element, child_name: str) -> str:
    child = elem.find(f"./p:{child_name}", namespaces=_PRESENTATION_NS)
    if child is None:
        return ""
    return etree.tostring(child, encoding="unicode")


def _format_motion_path(dx: float, dy: float) -> str:
    return f"M 0 0 L {_format_coord(dx)} {_format_coord(dy)} E"


def _format_coord(value: float) -> str:
    if abs(value) < 1e-12:
        return "0"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


class DrawingMLAnimationWriter:
    """Render animation definitions as DrawingML timing XML."""

    def __init__(self) -> None:
        self._unit_converter = UnitConverter()
        self._xml_builder = AnimationXMLBuilder()
        self._value_processor = ValueProcessor()
        self._tav_builder = TAVBuilder(self._xml_builder)
        self._id_allocator = TimingIDAllocator()
        self._policy: AnimationPolicy | None = None

        # Handlers in priority order (most specific first, catch-all last)
        self._handlers: list[AnimationHandler] = [
            OpacityAnimationHandler(
                self._xml_builder, self._value_processor,
                self._tav_builder, self._unit_converter,
            ),
            ColorAnimationHandler(
                self._xml_builder, self._value_processor,
                self._tav_builder, self._unit_converter,
            ),
            SetAnimationHandler(
                self._xml_builder, self._value_processor,
                self._tav_builder, self._unit_converter,
            ),
            MotionAnimationHandler(
                self._xml_builder, self._value_processor,
                self._tav_builder, self._unit_converter,
            ),
            TransformAnimationHandler(
                self._xml_builder, self._value_processor,
                self._tav_builder, self._unit_converter,
            ),
            NumericAnimationHandler(
                self._xml_builder, self._value_processor,
                self._tav_builder, self._unit_converter,
            ),
        ]

    def build(
        self,
        animations: Sequence[AnimationDefinition],
        timeline: Sequence[AnimationScene],
        *,
        tracer: ConversionTracer | None = None,
        options: Mapping[str, Any] | None = None,
        animated_shape_ids: list[str] | None = None,
        start_id: int = 1,
    ) -> str:
        """Build PowerPoint timing XML for a sequence of animations."""
        options = dict(options or {})
        self._policy = AnimationPolicy(options)

        # Pre-allocate IDs for the complete timing tree, starting after shape IDs
        ids = self._id_allocator.allocate(n_animations=len(animations), start_id=start_id)

        animation_elements: list[etree._Element] = []
        id_index = 0

        for animation in animations:
            anim_ids = ids.animations[id_index]
            id_index += 1

            elem, meta = self._build_animation(
                animation, options, anim_ids.par, anim_ids.behavior
            )

            _logger.debug(
                "Animation fragment for %s (%s): %s",
                animation.element_id,
                animation.target_attribute,
                "SUCCESS" if elem is not None else f"SKIPPED ({meta.get('reason') if meta else 'unknown'})",
            )

            if elem is not None:
                animation_elements.append(elem)
                if tracer is not None:
                    emitted_metadata: dict[str, Any] = {
                        "element_id": animation.element_id,
                        "animation_type": (
                            animation.animation_type.value
                            if hasattr(animation.animation_type, "value")
                            else str(animation.animation_type)
                        ),
                        "attribute": animation.target_attribute,
                        "fallback_mode": options.get("fallback_mode", "native"),
                    }
                    tracer.record_stage_event(
                        stage="animation",
                        action="fragment_emitted",
                        metadata=emitted_metadata,
                    )
                    rotate_mode = str(getattr(animation, "motion_rotate", "")).strip().lower()
                    if rotate_mode in {"auto", "auto-reverse"}:
                        tracer.record_stage_event(
                            stage="animation",
                            action="fidelity_downgrade",
                            metadata={
                                "reason": "rotate_auto_approximated",
                                "element_id": animation.element_id,
                                "rotate_mode": rotate_mode,
                            },
                        )
            elif tracer is not None:
                metadata: dict[str, Any] = {
                    "element_id": animation.element_id,
                    "animation_type": (
                        animation.animation_type.value
                        if hasattr(animation.animation_type, "value")
                        else str(animation.animation_type)
                    ),
                    "attribute": animation.target_attribute,
                    "fallback_mode": options.get("fallback_mode", "native"),
                }
                if meta:
                    metadata.update(meta)
                tracer.record_stage_event(
                    stage="animation",
                    action="fragment_skipped",
                    metadata=metadata,
                )

        if not animation_elements:
            return ""

        # Check if timing should be globally suppressed by policy.
        # Per-fragment suppression is handled in should_skip().
        should_suppress = False
        if self._policy:
            should_suppress = self._policy.should_suppress_timing()

        if should_suppress:
            return ""

        animation_elements = _merge_concurrent_simple_motion_fragments(
            animation_elements
        )

        # Build the complete timing tree as a single element, then serialize once
        timing_tree = self._xml_builder.build_timing_tree(
            ids=ids,
            animation_elements=animation_elements,
            animated_shape_ids=animated_shape_ids or [],
        )
        return to_string(timing_tree)

    def _build_animation(
        self,
        animation: AnimationDefinition,
        options: Mapping[str, Any],
        par_id: int,
        behavior_id: int,
    ) -> tuple[etree._Element | None, dict[str, Any] | None]:
        """Build element for a single animation."""
        if self._policy is None:
            self._policy = AnimationPolicy(options)

        animation = self._bake_accumulate(animation)
        animation = self._clamp_duration(animation)

        max_error = self._policy.estimate_spline_error(animation)
        should_skip, skip_reason = self._policy.should_skip(animation, max_error)
        if should_skip:
            return None, {"reason": skip_reason}

        handler = self._find_handler(animation)
        if handler is None:
            return None, {"reason": self._unsupported_reason(animation)}

        try:
            result = handler.build(animation, par_id, behavior_id)
            if result is None:
                return None, {"reason": "handler_returned_empty"}
            return result, None
        except Exception as e:
            return None, {"reason": f"handler_error: {str(e)}"}

    @staticmethod
    def _unsupported_reason(animation: AnimationDefinition) -> str:
        """Return a stable reason code for animations with no registered handler."""
        if (
            animation.animation_type == AnimationType.ANIMATE_TRANSFORM
            and animation.transform_type in {TransformType.SKEWX, TransformType.SKEWY}
        ):
            return f"unsupported_transform_{animation.transform_type.value.lower()}"
        if animation.target_attribute == "color":
            return "unsupported_attribute_color"
        return "no_handler_found"

    @staticmethod
    def _bake_accumulate(animation: AnimationDefinition) -> AnimationDefinition:
        """Bake accumulate="sum" into expanded keyframe values.

        Each repetition builds on the previous end value by adding the
        end-start delta for numeric values.
        """
        if animation.accumulate != "sum":
            return animation
        if animation.repeat_count in (None, "indefinite", 1, "1"):
            return animation
        if len(animation.values) < 2:
            return animation
        try:
            repeat_n = int(animation.repeat_count)
        except (ValueError, TypeError):
            return animation
        if repeat_n <= 1:
            return animation

        base_vals = animation.values
        try:
            start_f = float(base_vals[0])
            end_f = float(base_vals[-1])
        except ValueError:
            return animation  # non-numeric — can't accumulate

        delta = end_f - start_f
        expanded: list[str] = list(base_vals)
        for rep in range(1, repeat_n):
            offset = delta * rep
            expanded.extend(str(float(v) + offset) for v in base_vals[1:])
        return replace(animation, values=expanded, accumulate="none")

    @staticmethod
    def _clamp_duration(animation: AnimationDefinition) -> AnimationDefinition:
        """Apply min/max duration constraints from SMIL."""
        if animation.min_ms is None and animation.max_ms is None:
            return animation
        dur = animation.duration_ms
        if dur == float("inf"):
            return animation
        if animation.min_ms is not None:
            dur = max(dur, animation.min_ms)
        if animation.max_ms is not None:
            dur = min(dur, animation.max_ms)
        if dur == animation.duration_ms:
            return animation
        return replace(
            animation,
            timing=replace(animation.timing, duration=dur / 1000.0),
        )

    def _find_handler(self, animation: AnimationDefinition) -> AnimationHandler | None:
        for handler in self._handlers:
            if handler.can_handle(animation):
                return handler
        return None
