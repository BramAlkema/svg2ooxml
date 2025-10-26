"""Helpers for parsing inline CSS style attributes."""

from __future__ import annotations


def parse_inline_style(style: str | None) -> dict[str, str]:
    if not style:
        return {}

    declarations: dict[str, str] = {}
    for part in style.split(";"):
        if not part.strip():
            continue
        if ":" not in part:
            continue
        name, value = part.split(":", 1)
        name = name.strip()
        value = value.strip()
        if not name or not value:
            continue
        declarations[name] = value
    return declarations
