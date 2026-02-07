"""CSS parsing utilities leveraging tinycss2."""

from __future__ import annotations

from dataclasses import dataclass

import tinycss2

SelectorSpecificity = tuple[int, int, int]


@dataclass(slots=True)
class StyleRule:
    selector: str
    selector_type: str
    value: str
    specificity: SelectorSpecificity
    declarations: dict[str, str]
    order: int


def _compute_specificity(selector_type: str) -> SelectorSpecificity:
    if selector_type == "id":
        return (1, 0, 0)
    if selector_type == "class":
        return (0, 1, 0)
    return (0, 0, 1)


def _normalize_value(value: str) -> str:
    return value.strip()


def parse_stylesheet(css_text: str, *, order_offset: int = 0) -> list[StyleRule]:
    rules: list[StyleRule] = []
    parsed = tinycss2.parse_stylesheet(css_text, skip_comments=True, skip_whitespace=True)
    order = order_offset
    for rule in parsed:
        if rule.type != "qualified-rule":
            continue
        selector_text = tinycss2.serialize(rule.prelude).strip()
        if not selector_text:
            continue
        declarations: dict[str, str] = {}
        for decl in tinycss2.parse_declaration_list(
            rule.content, skip_comments=True, skip_whitespace=True
        ):
            if decl.type != "declaration" or decl.name is None:
                continue
            value = tinycss2.serialize(decl.value).strip()
            declarations[decl.name] = value
        if not declarations:
            continue
        selectors = [part.strip() for part in selector_text.split(",") if part.strip()]
        for sel in selectors:
            if sel.startswith("#"):
                selector_type = "id"
                value = sel[1:]
            elif sel.startswith("."):
                selector_type = "class"
                value = sel[1:]
            else:
                selector_type = "tag"
                value = sel.lower()
            rule_obj = StyleRule(
                selector=sel,
                selector_type=selector_type,
                value=_normalize_value(value),
                specificity=_compute_specificity(selector_type),
                declarations=dict(declarations),
                order=order,
            )
            rules.append(rule_obj)
            order += 1
    return rules
