"""Build-list support for PowerPoint animation timing XML."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.drawingml.xml_builder import NS_P, p_sub

from .constants import SVG2_ANIMATION_NS

__all__ = [
    "append_build_list",
    "strip_internal_metadata",
]

_BUILD_MODE_ATTR = f"{{{SVG2_ANIMATION_NS}}}bldMode"


def append_build_list(
    timing: etree._Element,
    *,
    animation_elements: list[etree._Element],
    animated_shape_ids: list[str],
) -> None:
    """Append ``<p:bldLst>`` entries for animated shapes and effects."""
    effect_build_entries = _collect_effect_build_entries(animation_elements)
    if not animated_shape_ids and not effect_build_entries:
        return

    bld_lst = p_sub(timing, "bldLst")
    for shape_id in animated_shape_ids:
        p_sub(bld_lst, "bldP", spid=shape_id, grpId="0", animBg="1")
    for shape_id, grp_id, build_mode in effect_build_entries:
        p_sub(
            bld_lst,
            "bldP",
            spid=shape_id,
            grpId=grp_id,
            **_build_list_attrs(build_mode),
        )


def strip_internal_metadata(root: etree._Element) -> None:
    """Remove svg2ooxml-only attributes before serializing PPT timing XML."""
    for elem in root.iter():
        internal_attrs = [
            name for name in elem.attrib if etree.QName(name).namespace == SVG2_ANIMATION_NS
        ]
        for name in internal_attrs:
            del elem.attrib[name]


def _collect_effect_build_entries(
    animation_elements: list[etree._Element],
) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    for par in animation_elements:
        build_mode = par.get(_BUILD_MODE_ATTR, "animBg")
        for elem in par.iter(f"{{{NS_P}}}cTn"):
            if not elem.get("presetClass") and not elem.get("presetID"):
                continue
            entry_id = elem.get("id")
            if not entry_id:
                continue
            sp_tgt = elem.find(f".//{{{NS_P}}}spTgt")
            if sp_tgt is None:
                continue
            shape_id = sp_tgt.get("spid")
            if not shape_id:
                continue
            key = (shape_id, entry_id)
            if key in seen:
                continue
            seen.add(key)
            entries.append((shape_id, entry_id, build_mode))

    return entries


def _build_list_attrs(build_mode: str) -> dict[str, str]:
    if build_mode == "paragraph":
        return {"build": "p", "rev": "1"}
    if build_mode == "allAtOnce":
        return {"build": "allAtOnce", "animBg": "1"}
    return {"animBg": "1"}
