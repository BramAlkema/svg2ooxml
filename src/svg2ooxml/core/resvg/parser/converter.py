"""Conversion from lxml nodes into SvgNode structures."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.common.svg_refs import local_name as _local_name

from .css import StyleRule, parse_stylesheet
from .options import Options
from .style import parse_inline_style_with_importance
from .tree import SvgDocument, SvgNode


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    if value == "":
        return None
    return value


def _normalize_attributes(elem: etree._Element) -> tuple[dict[str, str], dict[str, str], dict[str, bool]]:
    attributes = {k: v for k, v in elem.attrib.items()}
    inline_style, inline_importance = parse_inline_style_with_importance(attributes.get("style"))
    if "style" in attributes and inline_style:
        # Keep the redundant attribute for potential round-tripping later.
        pass
    return attributes, inline_style, inline_importance


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
    attributes, inline_style, inline_importance = _normalize_attributes(elem)
    node = SvgNode(
        tag=elem.tag,
        source=elem,
        attributes=attributes,
        styles=inline_style,
        style_importance=inline_importance,
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


def _apply_cascade(document: SvgDocument) -> None:
    def recurse(node: SvgNode, inherited: dict[str, str]) -> dict[str, str]:
        applicable = [r for r in document.style_rules if _matches_rule(node, r)]
        merged = dict(inherited)
        stylesheet_declarations = [
            (decl, rule.specificity, rule.order, index)
            for rule in applicable
            for index, decl in enumerate(rule.declarations)
        ]
        stylesheet_declarations.sort(
            key=lambda item: (
                int(item[0].important),
                item[1],
                item[2],
                item[3],
            )
        )
        applied_importance: dict[str, bool] = {}
        for decl, _, _, _ in stylesheet_declarations:
            merged[decl.name] = decl.value
            applied_importance[decl.name] = decl.important

        for name, value in node.styles.items():
            inline_important = node.style_importance.get(name, False)
            if applied_importance.get(name, False) and not inline_important:
                continue
            merged[name] = value

        resolved: dict[str, str] = {}
        for prop, value in merged.items():
            lowered = value.lower()
            if lowered == "inherit":
                if prop in inherited:
                    resolved[prop] = inherited[prop]
                continue
            resolved[prop] = value

        color_value = resolved.get("color")
        if color_value is not None and color_value.lower() == "inherit":
            color_value = inherited.get("color")
        if color_value is not None and color_value.lower() == "currentcolor":
            color_value = inherited.get("color")
        if color_value is not None:
            resolved["color"] = color_value
        elif "color" in resolved:
            resolved.pop("color")

        color_reference = resolved.get("color") or inherited.get("color")
        for key in ("fill", "stroke"):
            val = resolved.get(key)
            if val is not None and val.lower() == "inherit":
                if key in inherited:
                    resolved[key] = inherited[key]
                else:
                    resolved.pop(key, None)
                continue
            if val is not None and val.lower() == "currentcolor":
                if color_reference is not None:
                    resolved[key] = color_reference
                else:
                    resolved.pop(key, None)

        node.styles = resolved
        for child in node.children:
            recurse(child, resolved)
        return resolved

    recurse(document.root, {})
