"""Small CSS value helpers shared by style resolution code."""

from __future__ import annotations

import tinycss2

from svg2ooxml.common.style.css_math import simplify_calc_functions


def resolve_calc(value: str) -> str:
    """Evaluate context-free ``calc()`` expressions when units are compatible.

    Mixed-unit length math such as ``calc(100% - 10px)`` needs viewport context.
    Leave those expressions intact so property-specific resolvers can evaluate
    them later with the right axis.
    """

    return simplify_calc_functions(value)


def parse_style_declarations(style: str | None) -> tuple[dict[str, str], dict[str, bool]]:
    """Parse a CSS declaration list into values and importance flags."""

    if not style:
        return {}, {}

    declarations: dict[str, str] = {}
    importance: dict[str, bool] = {}
    for decl in tinycss2.parse_declaration_list(
        style,
        skip_comments=True,
        skip_whitespace=True,
    ):
        if decl.type != "declaration" or decl.name is None:
            continue
        name = decl.name.strip().lower()
        value = tinycss2.serialize(decl.value).strip()
        if not name or not value:
            continue
        declarations[name] = value
        importance[name] = bool(decl.important)
    return declarations, importance
