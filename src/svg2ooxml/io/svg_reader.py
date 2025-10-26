"""Placeholder SVG reader."""

from __future__ import annotations

from pathlib import Path


def read_svg_shapes(svg_path: str | Path) -> tuple[str, ...]:
    """Pretend to read an SVG by returning a fixed shape list."""
    _ = svg_path
    return ("rect", "circle", "text")


__all__ = ["read_svg_shapes"]
