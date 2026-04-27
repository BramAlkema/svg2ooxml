"""Motion fragment merging helpers for DrawingML animation timing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from lxml import etree

from svg2ooxml.drawingml.xml_builder import NS_P, p_sub

from .native_fragment import NativeFragment

_PRESENTATION_NS = {"p": NS_P}
_ANIM_MOTION_TAG = f"{{{NS_P}}}animMotion"
_CTN_TAG = f"{{{NS_P}}}cTn"
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


def merge_concurrent_simple_motion_fragments(
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
            _behavior_ctn_signature(behavior_ctn),
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
    if _normalized_rotation_angle(left.r_ang) != _normalized_rotation_angle(right.r_ang):
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
    merged_rotation = _merged_rotation_angle(records)
    anchor.motion.set("path", _format_motion_path(merged_dx, merged_dy))
    anchor.motion.set("origin", anchor.origin)
    anchor.motion.set("pathEditMode", anchor.path_edit_mode)
    if merged_rotation is None:
        anchor.motion.attrib.pop("rAng", None)
    else:
        anchor.motion.set("rAng", merged_rotation)
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


def _normalized_rotation_angle(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        if abs(float(value)) <= 1e-9:
            return None
    except (TypeError, ValueError):
        pass
    return value


def _merged_rotation_angle(records: list[_MotionFragmentRecord]) -> str | None:
    angles = {
        normalized
        for record in records
        if (normalized := _normalized_rotation_angle(record.r_ang)) is not None
    }
    if len(angles) == 1:
        return next(iter(angles))
    return None


def renumber_generated_timing_ids(
    records: list[tuple[NativeFragment, Any]],
    *,
    reserved_ids: set[int],
) -> None:
    existing_ids = set(reserved_ids)
    for fragment, _anim_ids in records:
        par = fragment.par
        for ctn in par.iter(_CTN_TAG):
            parsed = _parse_timing_id(ctn.get("id"))
            if parsed is not None:
                existing_ids.add(parsed)

    next_id = (max(existing_ids) + 1) if existing_ids else 1
    used_ids: set[int] = set()

    def _next_available_id() -> int:
        nonlocal next_id
        while next_id in used_ids or next_id in reserved_ids:
            next_id += 1
        value = next_id
        used_ids.add(value)
        next_id += 1
        return value

    for fragment, anim_ids in records:
        par = fragment.par
        expected_ids = {int(anim_ids.par), int(anim_ids.behavior)}
        preserved_expected: set[int] = set()
        for ctn in par.iter(_CTN_TAG):
            current = _parse_timing_id(ctn.get("id"))
            should_preserve_expected = (
                current in expected_ids
                and current not in preserved_expected
                and current not in used_ids
            )
            if should_preserve_expected:
                used_ids.add(current)
                preserved_expected.add(current)
                continue

            if current is None or current in used_ids or current in reserved_ids:
                ctn.set("id", str(_next_available_id()))
                continue

            used_ids.add(current)


def _parse_timing_id(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _behavior_ctn_signature(elem: etree._Element) -> tuple[Any, ...]:
    """Normalize behavior cTn signatures for merge compatibility.

    Inner behavior ``<p:cTn>`` nodes sometimes carry a redundant
    ``<p:stCondLst><p:cond delay="0"/></p:stCondLst>`` and sometimes omit it.
    That difference should not block merging equivalent concurrent motion
    fragments.
    """
    return (
        _attrs_signature(elem, ignore={"id"}),
        _child_xml(elem, "endCondLst"),
        _child_xml(elem, "endSync"),
    )


def _child_xml(elem: etree._Element, child_name: str) -> str:
    child = elem.find(f"./p:{child_name}", namespaces=_PRESENTATION_NS)
    if child is None:
        return ""
    # Normalize away inherited namespace declarations from internal metadata
    # so structurally identical timing fragments compare equal.
    return etree.tostring(
        child,
        method="c14n",
        exclusive=True,
        with_comments=False,
    ).decode("utf-8")


def _format_motion_path(dx: float, dy: float) -> str:
    return f"M 0 0 L {_format_coord(dx)} {_format_coord(dy)} E"


def _format_coord(value: float) -> str:
    if abs(value) < 1e-12:
        return "0"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text
