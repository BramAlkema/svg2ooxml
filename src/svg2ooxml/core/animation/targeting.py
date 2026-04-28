"""Target lookup and raw attribute helpers for SMIL animation parsing."""

from __future__ import annotations

from collections.abc import Sequence

from lxml import etree

from svg2ooxml.common.style.css_values import parse_style_declarations
from svg2ooxml.common.svg_refs import local_url_id

from .parser_types import ANIMATION_TAGS

_XLINK_NS = "http://www.w3.org/1999/xlink"


def find_animation_elements(
    svg_element: etree._Element,
    *,
    animation_tags: Sequence[str] = ANIMATION_TAGS,
) -> list[etree._Element]:
    elements: list[etree._Element] = []
    for element in svg_element.iter():
        if not isinstance(element.tag, str):
            continue
        if etree.QName(element).localname in animation_tags:
            elements.append(element)
    return elements


def extract_raw_attributes(
    element: etree._Element,
    *,
    target_element: etree._Element | None = None,
) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for raw_name, value in element.attrib.items():
        qname = etree.QName(raw_name)
        if qname.namespace == _XLINK_NS:
            key = f"xlink:{qname.localname}"
        else:
            key = qname.localname
        attrs[key] = value
    if target_element is not None:
        attrs["svg2ooxml_target_tag"] = etree.QName(target_element).localname
    return attrs


def ensure_target_ids(elements: list[etree._Element]) -> None:
    """Assign synthetic IDs to animation parent targets that lack an ID."""
    if not elements:
        return
    root = elements[0].getroottree().getroot()
    used_ids = {
        element_id
        for node in root.iter()
        if isinstance(node.tag, str)
        for element_id in [node.get("id")]
        if isinstance(element_id, str) and element_id
    }
    counter = 0
    for element in elements:
        href = _animation_href(element)
        if local_url_id(href) is not None:
            continue

        target = element.get("target")
        if local_url_id(target) is not None:
            continue

        parent = element.getparent()
        if parent is not None and not parent.get("id"):
            while True:
                synthetic_id = f"anim-target-{counter}"
                counter += 1
                if synthetic_id not in used_ids:
                    break
            parent.set("id", synthetic_id)
            used_ids.add(synthetic_id)


def get_target_element_id(element: etree._Element) -> str | None:
    href = _animation_href(element)
    target_id = local_url_id(href)
    if target_id is not None:
        return target_id

    target = element.get("target")
    target_id = local_url_id(target)
    if target_id is not None:
        return target_id

    parent = element.getparent()
    if parent is not None:
        parent_id = parent.get("id")
        if parent_id:
            return parent_id

    return None


def resolve_underlying_animation_value(
    animation_element: etree._Element,
    *,
    target_attribute: str | None,
    animation_tags: Sequence[str] = ANIMATION_TAGS,
) -> str | None:
    if not target_attribute:
        return None

    target = resolve_target_element(
        animation_element,
        animation_tags=animation_tags,
    )
    if target is None:
        return None

    direct_value = target.get(target_attribute)
    if direct_value is not None and direct_value.strip():
        return direct_value.strip()

    style_value = target.get("style")
    if not style_value:
        return None

    value = parse_style_declarations(style_value)[0].get(target_attribute)
    if value and value.strip():
        return value.strip()

    return None


def resolve_target_element(
    animation_element: etree._Element,
    *,
    animation_tags: Sequence[str] = ANIMATION_TAGS,
) -> etree._Element | None:
    root = animation_element.getroottree().getroot()

    href = _animation_href(animation_element)
    target_id = local_url_id(href)
    if target_id is not None:
        target = lookup_element_by_id(root, target_id)
        if target is not None:
            return target

    target = animation_element.get("target")
    target_id = local_url_id(target)
    if target_id is not None:
        return lookup_element_by_id(root, target_id)

    parent = animation_element.getparent()
    if parent is not None and etree.QName(parent).localname not in animation_tags:
        return parent

    return None


def lookup_element_by_id(
    root: etree._Element,
    element_id: str,
) -> etree._Element | None:
    element_id = element_id.strip()
    if not element_id:
        return None

    matches = root.xpath(".//*[@id=$target_id]", target_id=element_id)
    if not matches:
        return None
    return matches[0]


def _animation_href(element: etree._Element) -> str | None:
    return element.get("href") or element.get(f"{{{_XLINK_NS}}}href")


__all__ = [
    "ensure_target_ids",
    "extract_raw_attributes",
    "find_animation_elements",
    "get_target_element_id",
    "lookup_element_by_id",
    "resolve_target_element",
    "resolve_underlying_animation_value",
]
