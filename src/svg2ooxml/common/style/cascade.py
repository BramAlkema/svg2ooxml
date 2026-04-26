"""Stylesheet collection and cascade ordering for SVG CSS."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

import tinycss2
from lxml import etree

from svg2ooxml.common.style.css_values import resolve_calc
from svg2ooxml.common.style.model import CSSDeclaration, CSSOrigin, CSSRule
from svg2ooxml.common.style.selectors import (
    CompiledSelector,
    compute_specificity,
    parse_selector,
)

if TYPE_CHECKING:
    from svg2ooxml.core.parser.units import UnitConverter

_SVG_NAMESPACE = "http://www.w3.org/2000/svg"

_CASCADE_PRIORITY = {
    CSSOrigin.USER_AGENT: 0,
    CSSOrigin.PRESENTATION_ATTR: 1,
    CSSOrigin.AUTHOR: 2,
    CSSOrigin.INLINE: 3,
}


def parse_inline_declarations(style_str: str) -> Iterable[tuple[str, str, bool]]:
    if not style_str:
        return []
    try:
        declarations = tinycss2.parse_declaration_list(
            style_str,
            skip_whitespace=True,
            skip_comments=True,
        )
    except Exception:
        return []

    resolved: list[tuple[str, str, bool]] = []
    for decl in declarations:
        if decl.type != "declaration":
            continue
        name = decl.name.lower()
        value = tinycss2.serialize(decl.value).strip()
        resolved.append((name, value, bool(decl.important)))
    return resolved


class StylesheetCascade:
    """Collect stylesheet rules and expose matching declarations in cascade order."""

    def __init__(self, unit_converter: UnitConverter) -> None:
        self._unit_converter = unit_converter
        self._rules: list[CSSRule] = []
        self._custom_properties: dict[str, str] = {}
        self._viewport_width: float | None = None
        self._viewport_height: float | None = None

    def collect(
        self,
        root: etree._Element | None,
        *,
        viewport_width: float | None = None,
        viewport_height: float | None = None,
    ) -> None:
        self._rules = []
        self._custom_properties = {}
        self._viewport_width = viewport_width
        self._viewport_height = viewport_height
        if root is None:
            return

        style_elements = root.findall(f".//{{{_SVG_NAMESPACE}}}style")
        order = 0
        for style in style_elements:
            text = style.text or ""
            if not text.strip():
                continue
            try:
                stylesheet = tinycss2.parse_stylesheet(
                    text,
                    skip_whitespace=True,
                    skip_comments=True,
                )
            except Exception:
                continue
            order = self._process_stylesheet_rules(stylesheet, order)

    def declarations_for(self, element: etree._Element) -> list[CSSDeclaration]:
        if not self._rules:
            return []

        matches: list[tuple[CSSDeclaration, tuple[int, int, int], int, int, CSSOrigin]] = []
        for rule in self._rules:
            for selector in rule.selectors:
                if not selector.matches(element):
                    continue
                for index, declaration in enumerate(rule.declarations):
                    matches.append((declaration, selector.specificity, rule.order, index, rule.origin))

        if not matches:
            return []

        matches.sort(
            key=lambda item: (
                int(item[0].important),
                _CASCADE_PRIORITY.get(item[4], 0),
                item[1],
                item[2],
                item[3],
            )
        )
        return [item[0] for item in matches]

    def _process_stylesheet_rules(self, stylesheet, order: int) -> int:
        for rule in stylesheet:
            if rule.type == "at-rule" and rule.lower_at_keyword == "media":
                order = self._process_media_rule(rule, order)
                continue
            if rule.type != "qualified-rule":
                continue
            order = self._process_qualified_rule(rule, order)
        return order

    def _process_media_rule(self, rule, order: int) -> int:
        query = tinycss2.serialize(rule.prelude).strip().lower()
        if not self._media_matches(query):
            return order
        if rule.content is None:
            return order
        try:
            child_rules = tinycss2.parse_rule_list(
                rule.content,
                skip_whitespace=True,
                skip_comments=True,
            )
        except Exception:
            return order
        return self._process_stylesheet_rules(child_rules, order)

    def _process_qualified_rule(self, rule, order: int) -> int:
        selector_text = tinycss2.serialize(rule.prelude).strip()
        if not selector_text:
            return order
        declarations = self._parse_rule_declarations(rule)
        if not declarations:
            return order

        if selector_text == ":root":
            for decl in declarations:
                if decl.name.startswith("--"):
                    self._custom_properties[decl.name] = decl.value

        selectors = self._compile_selectors(selector_text)
        if not selectors:
            return order

        self._rules.append(
            CSSRule(
                selectors=tuple(selectors),
                declarations=tuple(declarations),
                order=order,
            )
        )
        return order + 1

    def _media_matches(self, query: str) -> bool:
        if self._viewport_width is None and self._viewport_height is None:
            return True

        width = self._viewport_width or 0.0
        height = self._viewport_height or 0.0
        conversion = self._unit_converter.create_context(
            width=width,
            height=height,
            parent_width=width,
            parent_height=height,
            viewport_width=width,
            viewport_height=height,
        )
        for match in re.finditer(
            r"(min|max)-(width|height)\s*:\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?[a-z%]*)",
            query,
        ):
            bound_type, dimension, value = match.group(1), match.group(2), match.group(3)
            axis = "x" if dimension == "width" else "y"
            try:
                threshold = self._unit_converter.to_px(value, conversion, axis=axis)
            except Exception:
                threshold = 0.0
            actual = width if dimension == "width" else height
            if bound_type == "min" and actual < threshold:
                return False
            if bound_type == "max" and actual > threshold:
                return False
        return True

    def _parse_rule_declarations(self, rule) -> list[CSSDeclaration]:
        try:
            declarations = tinycss2.parse_declaration_list(
                rule.content,
                skip_whitespace=True,
                skip_comments=True,
            )
        except Exception:
            return []

        resolved: list[CSSDeclaration] = []
        for decl in declarations:
            if decl.type != "declaration":
                continue
            name = decl.name.lower()
            value = tinycss2.serialize(decl.value).strip()
            if not name or not value:
                continue
            if "var(" in value:
                value = self._resolve_var(value)
            if "calc(" in value:
                value = resolve_calc(value)
            resolved.append(
                CSSDeclaration(
                    name=name,
                    value=value,
                    important=bool(decl.important),
                )
            )
        return resolved

    def _resolve_var(self, value: str) -> str:
        def _replace(match: re.Match[str]) -> str:
            inner = match.group(1).strip()
            parts = inner.split(",", 1)
            name = parts[0].strip()
            fallback = parts[1].strip() if len(parts) > 1 else ""
            resolved = self._custom_properties.get(name)
            if resolved is not None:
                return resolved
            return fallback or name

        return re.sub(r"var\(([^)]+)\)", _replace, value)

    @staticmethod
    def _compile_selectors(selector_text: str) -> list[CompiledSelector]:
        selectors: list[CompiledSelector] = []
        for chunk in selector_text.split(","):
            parsed = parse_selector(chunk.strip())
            if not parsed:
                continue
            selectors.append(
                CompiledSelector(
                    parts=tuple(reversed(parsed)),
                    specificity=compute_specificity(parsed),
                )
            )
        return selectors


__all__ = [
    "StylesheetCascade",
    "parse_inline_declarations",
]
