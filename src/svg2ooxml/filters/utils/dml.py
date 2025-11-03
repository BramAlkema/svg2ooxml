"""Helpers for building exporter hook comments embedded in DrawingML."""

from __future__ import annotations

from typing import Iterable, Mapping


def build_exporter_hook(
    name: str,
    attributes: Mapping[str, object] | None = None,
    *,
    payloads: Iterable[str] | None = None,
) -> str:
    """Return a comment tag that downstream exporters can interpret."""

    parts: list[str] = []
    if attributes:
        for key, value in attributes.items():
            parts.append(f'{key}="{_format_value(value)}"')
    if payloads:
        for index, fragment in enumerate(payloads):
            parts.append(f'payload{index}="{_escape(fragment)}"')

    suffix = ""
    if parts:
        suffix = " " + " ".join(parts)
    return f"<!-- svg2ooxml:{name}{suffix} -->"


def is_effect_list(fragment: str | None) -> bool:
    """Return True when *fragment* looks like a DrawingML effect list."""

    if not fragment:
        return False
    return fragment.lstrip().startswith("<a:effectLst")


def extract_effect_children(fragment: str) -> str:
    """Return the inner XML of an effect list fragment."""

    text = fragment.strip()
    if not is_effect_list(text):
        return text
    if text.endswith("/>"):
        return ""
    start = text.find(">")
    end = text.rfind("</a:effectLst>")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start + 1 : end]


def merge_effect_fragments(*fragments: str | None) -> str:
    """Merge zero or more effect-list fragments into a single effect list."""

    children: list[str] = []
    for fragment in fragments:
        if not fragment:
            continue
        inner = extract_effect_children(fragment) if is_effect_list(fragment) else fragment
        if inner:
            children.append(inner)
    if not children:
        return ""
    return f"<a:effectLst>{''.join(children)}</a:effectLst>"


def _format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (list, tuple)):
        return " ".join(_format_value(item) for item in value)
    return _escape(str(value))


def _escape(value: str) -> str:
    return value.replace('"', "&quot;")


__all__ = ["build_exporter_hook", "is_effect_list", "extract_effect_children", "merge_effect_fragments"]
