"""Shared helpers for resvg paint bridge modules."""

from __future__ import annotations

from copy import deepcopy

from lxml import etree

from svg2ooxml.color.adapters import color_object_to_hex
from svg2ooxml.common.style.css_values import parse_style_declarations
from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.core.resvg.painting.paint import Color


def parse_style(style: str | None) -> dict[str, str]:
    return parse_style_declarations(style)[0]


def parse_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    token = value.strip()
    if not token:
        return default
    try:
        return float(token.strip("%")) / 100.0 if token.endswith("%") else float(token)
    except ValueError:
        return default


def format_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def color_to_hex(color: Color) -> str:
    return color_object_to_hex(color, prefix="#", scale="auto") or "#000000"


def normalize_hex(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip()
    if token.startswith("#"):
        token = token[1:]
    if len(token) not in {3, 6}:
        return None
    try:
        int(token, 16)
    except ValueError:
        return None
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    return f"#{token.upper()}"


def extract_href(element: etree._Element) -> str | None:
    href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
    return href if href else None


def clone_element(node: etree._Element) -> etree._Element:
    return deepcopy(node)


def copy_presentation_attributes(source: etree._Element | None, target: etree._Element) -> None:
    if source is None:
        return
    for name, value in source.attrib.items():
        if value is None:
            continue
        local = local_name(name)
        if local in {"href", "width", "height", "x", "y"}:
            continue
        if local == "style":
            existing = target.get("style")
            target.set("style", f"{existing};{value}" if existing else value)
            continue
        if name not in target.attrib:
            target.set(name, value)


__all__ = [
    "clone_element",
    "color_to_hex",
    "copy_presentation_attributes",
    "extract_href",
    "format_number",
    "normalize_hex",
    "parse_float",
    "parse_style",
]
