"""Small CSS value helpers shared by style resolution code."""

from __future__ import annotations

import re

import tinycss2


def resolve_calc(value: str) -> str:
    """Evaluate context-free ``calc()`` expressions when units are compatible.

    Mixed-unit length math such as ``calc(100% - 10px)`` needs viewport context.
    Leave those expressions intact so property-specific resolvers can evaluate
    them later with the right axis.
    """

    def _eval_calc(match):
        expr = match.group(1).strip()
        tokens = re.findall(
            r"([+\-*/])|((?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z%]*)",
            expr,
        )
        if not tokens:
            return match.group(0)
        has_additive_op = any(tok_op in {"+", "-"} for tok_op, _tok_num, _tok_unit in tokens)
        has_unit = any(bool(tok_unit) for _tok_op, tok_num, tok_unit in tokens if tok_num)
        has_unitless = any(not tok_unit for _tok_op, tok_num, tok_unit in tokens if tok_num)
        if has_additive_op and has_unit and has_unitless:
            return match.group(0)

        result = 0.0
        op = "+"
        unit: str | None = None
        for tok_op, tok_num, tok_unit in tokens:
            if tok_op:
                op = tok_op
                continue
            if not tok_num:
                continue
            if tok_unit:
                if unit is None:
                    unit = tok_unit
                elif unit != tok_unit:
                    return match.group(0)
            val = float(tok_num)
            if op == "+":
                result += val
            elif op == "-":
                result -= val
            elif op == "*":
                result *= val
            elif op == "/" and val != 0:
                result /= val

        return f"{result:g}{unit or ''}"

    return re.sub(r"calc\(([^)]+)\)", _eval_calc, value)


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
