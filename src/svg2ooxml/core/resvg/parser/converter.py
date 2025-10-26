"""Conversion from lxml nodes into SvgNode structures."""

from __future__ import annotations

from lxml import etree

from .css import StyleRule, parse_stylesheet
from .options import Options
from .style import parse_inline_style
from .tree import SvgDocument, SvgNode


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_attributes(elem: etree._Element) -> tuple[dict[str, str], dict[str, str]]:
    attributes = {k: v for k, v in elem.attrib.items()}
    inline_style = parse_inline_style(attributes.get("style"))
    if "style" in attributes and inline_style:
        # Keep the redundant attribute for potential round-tripping later.
        pass
    return attributes, inline_style


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _convert_element(
    elem: etree._Element,
    options: Options,
    style_rules: list[StyleRule],
) -> SvgNode | None:
    local_name = _local_name(elem.tag)
    if local_name == "style":
        css_text = elem.text or ""
        style_rules.extend(parse_stylesheet(css_text, order_offset=len(style_rules)))
        return None
    attributes, inline_style = _normalize_attributes(elem)
    node = SvgNode(
        tag=elem.tag,
        source=elem,
        attributes=attributes,
        styles=inline_style,
        text=_normalize_text(elem.text),
        tail=_normalize_text(elem.tail),
    )
    children = []
    for child in elem:
        converted = _convert_element(child, options, style_rules)
        if converted is not None:
            children.append(converted)
    node.children = children
    return node


def convert_document(root: etree._Element, options: Options) -> SvgDocument:
    style_rules: list[StyleRule] = []
    node = _convert_element(root, options, style_rules)
    if node is None:
        raise ValueError("Root element cannot be empty")
    document = SvgDocument(root=node, style_rules=style_rules)
    _apply_cascade(document)
    return document


def _matches_rule(node: SvgNode, rule: StyleRule) -> bool:
    local = _local_name(node.tag)
    if rule.selector_type == "tag":
        return local.lower() == rule.value
    if rule.selector_type == "id":
        return node.attributes.get("id") == rule.value
    if rule.selector_type == "class":
        classes = node.attributes.get("class", "").split()
        return rule.value in classes
    return False


def _resolve_inherit(value: str, inherited: dict[str, str]) -> Optional[str]:
    if value == "inherit":
        return inherited.get(value)
    return value


def _apply_cascade(document: SvgDocument) -> None:
    def recurse(node: SvgNode, inherited: dict[str, str]) -> dict[str, str]:
        applicable = [r for r in document.style_rules if _matches_rule(node, r)]
        applicable.sort(key=lambda r: (r.specificity, r.order))
        merged = dict(inherited)
        for rule in applicable:
            merged.update(rule.declarations)
        merged.update(node.styles)

        resolved: dict[str, str] = {}
        for prop, value in merged.items():
            if value == "inherit":
                if prop in inherited:
                    resolved[prop] = inherited[prop]
                continue
            resolved[prop] = value

        color_value = resolved.get("color")
        if color_value == "inherit":
            color_value = inherited.get("color")
        if color_value == "currentColor":
            color_value = inherited.get("color")
        if color_value is not None:
            resolved["color"] = color_value
        elif "color" in resolved:
            resolved.pop("color")

        color_reference = resolved.get("color") or inherited.get("color")
        for key in ("fill", "stroke"):
            val = resolved.get(key)
            if val == "inherit":
                if key in inherited:
                    resolved[key] = inherited[key]
                else:
                    resolved.pop(key, None)
                continue
            if val == "currentColor":
                if color_reference is not None:
                    resolved[key] = color_reference
                else:
                    resolved.pop(key, None)

        node.styles = resolved
        for child in node.children:
            recurse(child, resolved)
        return resolved

    recurse(document.root, {})
