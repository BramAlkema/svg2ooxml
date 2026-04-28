"""Presentation-level PPTX XML and relationship updates."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from lxml import etree as ET

from svg2ooxml.common.boundaries import (
    is_safe_relationship_id,
    next_relationship_id,
)
from svg2ooxml.io.pptx_package_constants import (
    FONT_STYLE_ORDER,
    FONT_STYLE_TAGS,
    P_NS,
    R_DOC_NS,
    REL_NS,
)
from svg2ooxml.io.pptx_package_model import (
    PackagedFont,
    SlideAssembly,
)
from svg2ooxml.io.pptx_part_names import (
    safe_int,
    sanitize_slide_filename,
)

TracePackaging = Callable[..., None]


@dataclass(frozen=True, slots=True)
class _PresentationSlideRef:
    filename: str
    rel_id: str
    slide_id: int


@dataclass(frozen=True, slots=True)
class _PresentationFontRef:
    font: PackagedFont
    rel_id: str


def update_presentation_parts(
    *,
    package_root: Path,
    slides: Sequence[SlideAssembly],
    fonts: Sequence[PackagedFont],
    slide_size: tuple[int, int] | None = None,
    trace_packaging: TracePackaging | None = None,
) -> None:
    """Update presentation XML and package relationships for slides/fonts."""

    presentation_path = package_root / "ppt" / "presentation.xml"
    tree = ET.parse(presentation_path)
    root = tree.getroot()
    ns = {"p": P_NS, "r": R_DOC_NS}

    _update_slide_dimensions(root, ns, slide_size, trace_packaging)

    rels_path = package_root / "ppt" / "_rels" / "presentation.xml.rels"
    rels_tree = ET.parse(rels_path)
    rels_root = rels_tree.getroot()

    for rel in list(rels_root.findall(f"{{{REL_NS}}}Relationship")):
        if rel.get("Type") == f"{R_DOC_NS}/slide":
            rels_root.remove(rel)

    used_rel_ids: set[object] = {
        rel.get("Id") for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")
    }
    slide_refs = _build_slide_refs(slides, used_rel_ids)
    font_refs = _build_font_refs(fonts, used_rel_ids)

    _replace_slide_list(root, ns, slide_refs)
    if fonts:
        _replace_embedded_font_list(root, ns, font_refs)

    tree.write(presentation_path, encoding="utf-8", xml_declaration=True)

    for entry in slide_refs:
        ET.SubElement(
            rels_root,
            f"{{{REL_NS}}}Relationship",
            {
                "Id": entry.rel_id,
                "Type": f"{R_DOC_NS}/slide",
                "Target": f"slides/{entry.filename}",
            },
        )

    for font_ref in font_refs:
        ET.SubElement(
            rels_root,
            f"{{{REL_NS}}}Relationship",
            {
                "Id": font_ref.rel_id,
                "Type": f"{R_DOC_NS}/font",
                "Target": f"fonts/{font_ref.font.filename}",
            },
        )

    rels_tree.write(rels_path, encoding="utf-8", xml_declaration=True)


def _update_slide_dimensions(
    root: ET._Element,
    ns: dict[str, str],
    slide_size: tuple[int, int] | None,
    trace_packaging: TracePackaging | None,
) -> None:
    if slide_size is None:
        return
    slide_sz = root.find("p:sldSz", ns)
    if slide_sz is None:
        return

    min_slide_emu = 914400
    cx = max(slide_size[0], min_slide_emu)
    cy = max(slide_size[1], min_slide_emu)
    slide_sz.set("cx", str(cx))
    slide_sz.set("cy", str(cy))
    if trace_packaging is not None:
        trace_packaging(
            "presentation_dimensions_updated",
            metadata={
                "width_emu": slide_size[0],
                "height_emu": slide_size[1],
                "width_inches": slide_size[0] / 914400,
                "height_inches": slide_size[1] / 914400,
            },
        )


def _build_slide_refs(
    slides: Sequence[SlideAssembly],
    used_rel_ids: set[object],
) -> list[_PresentationSlideRef]:
    used_slide_ids: set[int] = set()
    refs: list[_PresentationSlideRef] = []
    for ordinal, entry in enumerate(slides, start=1):
        refs.append(
            _PresentationSlideRef(
                filename=sanitize_slide_filename(entry.filename, fallback_index=entry.index),
                rel_id=_reserve_relationship_id(entry.rel_id, used_rel_ids, prefix="rId"),
                slide_id=_reserve_slide_id(
                    entry.slide_id,
                    used_slide_ids,
                    fallback=255 + ordinal,
                ),
            )
        )
    return refs


def _build_font_refs(
    fonts: Sequence[PackagedFont],
    used_rel_ids: set[object],
) -> list[_PresentationFontRef]:
    return [
        _PresentationFontRef(
            font=font,
            rel_id=_reserve_relationship_id(
                font.relationship_id,
                used_rel_ids,
                prefix="rIdFont",
            ),
        )
        for font in fonts
    ]


def _replace_slide_list(
    root: ET._Element,
    ns: dict[str, str],
    slide_refs: Sequence[_PresentationSlideRef],
) -> None:
    slide_list = root.find("p:sldIdLst", ns)
    if slide_list is None:
        slide_list = ET.SubElement(root, f"{{{P_NS}}}sldIdLst")
    else:
        for child in list(slide_list):
            slide_list.remove(child)

    for entry in slide_refs:
        ET.SubElement(
            slide_list,
            f"{{{P_NS}}}sldId",
            {
                "id": str(entry.slide_id),
                f"{{{R_DOC_NS}}}id": entry.rel_id,
            },
        )


def _replace_embedded_font_list(
    root: ET._Element,
    ns: dict[str, str],
    font_refs: Sequence[_PresentationFontRef],
) -> None:
    font_list = root.find("p:embeddedFontLst", ns)
    if font_list is None:
        font_list = ET.Element(f"{{{P_NS}}}embeddedFontLst")
        default_text = root.find("p:defaultTextStyle", ns)
        if default_text is not None:
            root.insert(list(root).index(default_text), font_list)
        else:
            root.append(font_list)
    else:
        for child in list(font_list):
            font_list.remove(child)

    font_groups: OrderedDict[str, dict[str, _PresentationFontRef]] = OrderedDict()
    for font_ref in font_refs:
        slot = font_groups.setdefault(font_ref.font.font_family, {})
        slot[font_ref.font.style_kind] = font_ref

    for family, style_map in font_groups.items():
        entry_elem = ET.SubElement(font_list, f"{{{P_NS}}}embeddedFont")
        representative_ref = (
            style_map.get("regular")
            or style_map.get("bold")
            or style_map.get("italic")
            or style_map.get("boldItalic")
        )
        representative = representative_ref.font if representative_ref else None
        font_attrs = {"typeface": family}
        font_attrs["pitchFamily"] = (
            str(representative.pitch_family)
            if representative and representative.pitch_family is not None
            else "0"
        )
        font_attrs["charset"] = (
            str(representative.charset)
            if representative and representative.charset is not None
            else "0"
        )
        ET.SubElement(entry_elem, f"{{{P_NS}}}font", font_attrs)
        for style_kind in FONT_STYLE_ORDER:
            tagged = style_map.get(style_kind)
            if tagged is None:
                continue
            ET.SubElement(
                entry_elem,
                f"{{{P_NS}}}{FONT_STYLE_TAGS[style_kind]}",
                {f"{{{R_DOC_NS}}}id": tagged.rel_id},
            )


def _reserve_relationship_id(
    candidate: object,
    used_ids: set[object],
    *,
    prefix: str,
) -> str:
    if is_safe_relationship_id(candidate) and candidate not in used_ids:
        assert isinstance(candidate, str)
        used_ids.add(candidate)
        return candidate

    rel_id = next_relationship_id(used_ids, prefix=prefix)
    used_ids.add(rel_id)
    return rel_id


def _reserve_slide_id(candidate: object, used_ids: set[int], *, fallback: int) -> int:
    parsed = safe_int(candidate)
    if parsed is None or parsed < 256 or parsed in used_ids:
        parsed = max(256, fallback)
        while parsed in used_ids:
            parsed += 1
    used_ids.add(parsed)
    return parsed


__all__ = ["update_presentation_parts"]
