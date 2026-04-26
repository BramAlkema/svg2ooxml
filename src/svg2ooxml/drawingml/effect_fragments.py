"""Validation helpers for raw DrawingML effect fragments."""

from __future__ import annotations

from copy import deepcopy

from lxml import etree

from svg2ooxml.common.boundaries import (
    BoundaryError,
    parse_wrapped_xml_fragment,
)
from svg2ooxml.common.svg_refs import local_name as svg_local_name
from svg2ooxml.common.svg_refs import namespace_uri
from svg2ooxml.drawingml.xml_builder import NS_A, NS_R, to_string

_EFFECT_LIST_CHILD_ORDER = (
    "blur",
    "fillOverlay",
    "glow",
    "innerShdw",
    "outerShdw",
    "prstShdw",
    "reflection",
    "softEdge",
)
_EFFECT_LIST_CHILDREN = frozenset(_EFFECT_LIST_CHILD_ORDER)
_PROJECT_EFFECT_LIST_PLACEHOLDERS = frozenset({"blipFill"})
_MERGEABLE_EFFECT_LIST_CHILDREN = _EFFECT_LIST_CHILDREN | _PROJECT_EFFECT_LIST_PLACEHOLDERS
_EFFECT_LIST_ORDER = {
    name: index
    for index, name in enumerate(
        [*_EFFECT_LIST_CHILD_ORDER, *_PROJECT_EFFECT_LIST_PLACEHOLDERS]
    )
}

def sanitize_custom_effect_fragment(fragment: str | None) -> str:
    """Return a DrawingML-only effect fragment, or ``""`` when unsafe.

    ``CustomEffect`` is the one remaining escape hatch for filter primitives that
    already produce DrawingML. Keep that escape hatch narrow: only DrawingML main
    namespace effect nodes may pass through, and malformed fragments are dropped.
    """

    root = _parse_effect_fragment(fragment)
    if root is None:
        return ""

    parts: list[str] = []
    for child in root:
        xml = _sanitize_top_level_node(child)
        if xml:
            parts.append(xml)
    return "".join(parts)


def extract_safe_effect_children(fragment: str | None) -> str:
    """Return sanitized children from an effect container fragment."""

    safe_fragment = sanitize_custom_effect_fragment(fragment)
    root = _parse_effect_fragment(safe_fragment)
    if root is None:
        return ""

    parts: list[str] = []
    for child in root:
        namespace, local_name = _split_tag(child.tag)
        if namespace == NS_A and local_name in {"effectLst", "effectDag"}:
            for grandchild in child:
                if _is_drawingml_element(grandchild) and _split_tag(grandchild.tag)[1] != "cont":
                    parts.append(to_string(deepcopy(grandchild)))
        elif _is_drawingml_element(child):
            parts.append(to_string(deepcopy(child)))
    return "".join(parts)


def merge_effect_lists(xml: str) -> str:
    """Merge top-level effect-list fragments, dropping unsafe or unknown nodes."""

    root = _parse_effect_fragment(xml)
    if root is None:
        return ""

    seen: dict[str, etree._Element] = {}
    for child in root:
        namespace, local_name = _split_tag(child.tag)
        if namespace != NS_A:
            continue
        if local_name == "effectLst":
            for effect_child in child:
                _collect_effect_list_child(seen, effect_child)
        else:
            _collect_effect_list_child(seen, child)

    if not seen:
        return ""

    ordered = sorted(
        seen.values(),
        key=lambda element: _EFFECT_LIST_ORDER.get(_split_tag(element.tag)[1], 999),
    )
    return f"<a:effectLst>{''.join(to_string(element) for element in ordered)}</a:effectLst>"


def _sanitize_top_level_node(node: etree._Element) -> str:
    if not _is_drawingml_element(node):
        return ""

    _, local_name = _split_tag(node.tag)
    if local_name == "effectLst":
        return to_string(deepcopy(node)) if _is_drawingml_subtree(node) else ""
    if local_name == "effectDag":
        return to_string(deepcopy(node)) if _is_drawingml_subtree(node) else ""
    if local_name in _EFFECT_LIST_CHILDREN and _is_drawingml_subtree(node):
        return to_string(deepcopy(node))
    return ""


def _collect_effect_list_child(
    seen: dict[str, etree._Element],
    node: etree._Element,
) -> None:
    if not _is_drawingml_subtree(node):
        return
    _, local_name = _split_tag(node.tag)
    if local_name in _MERGEABLE_EFFECT_LIST_CHILDREN:
        seen[local_name] = deepcopy(node)


def _is_drawingml_subtree(node: etree._Element) -> bool:
    for descendant in node.iter():
        if not _is_drawingml_element(descendant):
            return False
        for attr_name in descendant.attrib:
            attr_namespace, _ = _split_tag(attr_name)
            if attr_namespace and attr_namespace not in {NS_A, NS_R}:
                return False
    return True


def _is_drawingml_element(node: etree._Element) -> bool:
    namespace, _ = _split_tag(node.tag)
    return namespace == NS_A


def _parse_effect_fragment(fragment: str | None) -> etree._Element | None:
    if not fragment or not fragment.strip():
        return None

    try:
        return parse_wrapped_xml_fragment(
            fragment.strip(),
            namespaces={"a": NS_A, "r": NS_R},
        )
    except (BoundaryError, etree.XMLSyntaxError, ValueError):
        return None


def _split_tag(tag: str | None) -> tuple[str, str]:
    if not isinstance(tag, str):
        return "", ""
    return namespace_uri(tag) or "", svg_local_name(tag)


__all__ = [
    "extract_safe_effect_children",
    "merge_effect_lists",
    "sanitize_custom_effect_fragment",
]
