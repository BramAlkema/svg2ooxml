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


def _format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (list, tuple)):
        return " ".join(_format_value(item) for item in value)
    return _escape(str(value))


def _escape(value: str) -> str:
    return value.replace('"', "&quot;")


__all__ = ["build_exporter_hook"]
