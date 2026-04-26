"""Small CSS value helpers shared by style resolution code."""

from __future__ import annotations

import re

import tinycss2


def resolve_calc(value: str) -> str:
    """Evaluate simple calc() expressions, preserving the dominant unit."""

    def _eval_calc(match):
        expr = match.group(1).strip()
        tokens = re.findall(r"([+\-*/])|([.\d]+)\s*(%|px|em|rem|pt)?", expr)
        if not tokens:
            return match.group(0)

        result = 0.0
        op = "+"
        unit = ""
        for tok_op, tok_num, tok_unit in tokens:
            if tok_op:
                op = tok_op
                continue
            if not tok_num:
                continue
            val = float(tok_num)
            if tok_unit:
                unit = tok_unit
            if op == "+":
                result += val
            elif op == "-":
                result -= val
            elif op == "*":
                result *= val
            elif op == "/" and val != 0:
                result /= val

        return f"{result:g}{unit}"

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
