"""Helpers for parsing inline CSS style attributes."""

from __future__ import annotations

from svg2ooxml.common.style.css_values import parse_style_declarations


def parse_inline_style(style: str | None) -> dict[str, str]:
    return parse_inline_style_with_importance(style)[0]


def parse_inline_style_with_importance(style: str | None) -> tuple[dict[str, str], dict[str, bool]]:
    return parse_style_declarations(style)
