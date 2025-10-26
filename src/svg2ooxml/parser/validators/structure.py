"""Structural validators for SVG roots."""

from __future__ import annotations

from lxml import etree


def ensure_svg_root(root: etree._Element) -> None:
    """Validate that the parsed root is an SVG element."""
    local_tag = root.tag.split("}")[-1]
    if local_tag != "svg":
        raise ValueError(f"Root element is '{local_tag}', expected 'svg'")


def has_basic_dimensions(root: etree._Element) -> bool:
    """Check whether the SVG root exposes basic sizing metadata."""
    width = root.get("width")
    height = root.get("height")
    view_box = root.get("viewBox")
    return (width is not None and height is not None) or view_box is not None


__all__ = ["ensure_svg_root", "has_basic_dimensions"]
