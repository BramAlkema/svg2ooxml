"""Helpers for building exporter hook comments embedded in DrawingML."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

# Import centralized XML builders for safe DrawingML generation
from lxml import etree

from svg2ooxml.drawingml.xml_builder import NS_A, a_elem, graft_xml_fragment, to_string


def build_exporter_hook(
    name: str,
    attributes: Mapping[str, object] | None = None,
    *,
    payloads: Iterable[str] | None = None,
) -> str:
    """Return a comment tag that downstream exporters can interpret."""

    parts: list[str] = []
    if attributes:
        for key, value in attributes.items():
            parts.append(f'{key}="{_format_value(value)}"')
    if payloads:
        for index, fragment in enumerate(payloads):
            parts.append(f'payload{index}="{_escape(fragment)}"')

    suffix = ""
    if parts:
        suffix = " " + " ".join(parts)
    return f"<!-- svg2ooxml:{name}{suffix} -->"


def is_effect_list(fragment: str | None) -> bool:
    """Return True when *fragment* looks like a DrawingML effect list."""

    if not fragment:
        return False
    return fragment.lstrip().startswith("<a:effectLst")


def extract_effect_children(fragment: str) -> str:
    """Return the inner XML of an effect list fragment."""

    text = fragment.strip()
    if not text:
        return ""
    try:
        return _flatten_effect_children(text)
    except Exception:
        # Fallback to the original string parsing logic if XML parsing fails.
        if not is_effect_list(text):
            return text
        if text.endswith("/>"):
            return ""
        start = text.find(">")
        end = text.rfind("</a:effectLst>")
        if start == -1 or end == -1 or end <= start:
            return text
        return text[start + 1 : end]


def _flatten_effect_children(fragment: str) -> str:
    """Flatten effect list fragments into a single sequence of effect nodes."""

    wrapped = f'<root xmlns:a="{NS_A}">{fragment}</root>'
    temp = etree.fromstring(wrapped.encode("utf-8"))
    parts: list[str] = []
    for child in temp:
        if _local_name(child.tag) == "effectLst":
            for grandchild in child:
                parts.append(_serialize_node(grandchild))
        else:
            parts.append(_serialize_node(child))
    return "".join(parts)


def _serialize_node(node: etree._Element) -> str:
    if isinstance(node, (etree._Comment, etree._ProcessingInstruction)):
        return etree.tostring(node, encoding="unicode")
    return to_string(node)


def _local_name(tag: str | None) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def merge_effect_fragments(*fragments: str | None) -> str:
    """Merge zero or more effect-list fragments into a single effect list."""

    children: list[str] = []
    for fragment in fragments:
        if not fragment:
            continue
        inner = extract_effect_children(fragment) if is_effect_list(fragment) else fragment
        if inner:
            children.append(inner)
    if not children:
        return ""

    # Build effect list using lxml
    effectLst = a_elem("effectLst")

    # Parse and append child XML fragments
    for child_xml in children:
        try:
            graft_xml_fragment(effectLst, child_xml)
        except Exception:
            continue

    return to_string(effectLst)


def _format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (list, tuple)):
        return " ".join(_format_value(item) for item in value)
    return _escape(str(value))


def _escape(value: str) -> str:
    return value.replace('"', "&quot;")


__all__ = ["build_exporter_hook", "is_effect_list", "extract_effect_children", "merge_effect_fragments"]
