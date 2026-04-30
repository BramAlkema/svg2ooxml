"""SVG media fallback helpers for complex text fidelity cases."""

from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any

from lxml import etree

from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.policy.text_policy import TextPolicyDecision


def dense_rotation_fallback_mode(decision: TextPolicyDecision | None) -> str:
    """Return the configured dense-rotation fallback mode."""

    if decision is None:
        return "auto"
    fallback = getattr(decision, "fallback", None)
    mode = getattr(fallback, "dense_rotation_fallback", None)
    if not isinstance(mode, str) or not mode.strip():
        return "auto"
    return mode.strip().lower().replace("-", "_")


def bidi_override_fallback_mode(decision: TextPolicyDecision | None) -> str:
    """Return the configured mixed-script bidi-override fallback mode."""

    if decision is None:
        return "native"
    fallback = getattr(decision, "fallback", None)
    mode = getattr(fallback, "bidi_override_fallback", None)
    if not isinstance(mode, str) or not mode.strip():
        return "native"
    return mode.strip().lower().replace("-", "_")


def has_mixed_ltr_rtl_text(text: str) -> bool:
    """Return True when text contains strong LTR and RTL characters."""

    has_ltr = False
    has_rtl = False
    for char in text:
        bidi = unicodedata.bidirectional(char)
        if bidi == "L":
            has_ltr = True
        elif bidi in {"R", "AL", "AN"}:
            has_rtl = True
        if has_ltr and has_rtl:
            return True
    return False


def context_viewport_size(context: Any) -> tuple[float, float]:
    """Resolve the conversion viewport used for full-slide SVG fallbacks."""

    css_context = getattr(context, "css_context", None)
    width = getattr(css_context, "viewport_width", None)
    height = getattr(css_context, "viewport_height", None)
    return _positive_pair(width, height, default=(1.0, 1.0))


def source_text_svg_payload(
    element: etree._Element,
    *,
    viewport_size: tuple[float, float],
) -> tuple[bytes, tuple[float, float]] | None:
    """Serialize ``element`` and its styling ancestors as a standalone SVG."""

    root = _source_root(element)
    width_px, height_px = _source_svg_size(root, viewport_size)
    svg_attrib = _standalone_svg_attributes(
        root,
        width_px=width_px,
        height_px=height_px,
    )
    svg = etree.Element(
        root.tag if local_name(getattr(root, "tag", "")).lower() == "svg" else "svg",
        nsmap=root.nsmap,
        attrib=svg_attrib,
    )
    for support_node in _source_support_nodes(root):
        svg.append(deepcopy(support_node))

    subtree = _source_text_subtree(element, root)
    if subtree is None:
        return None
    svg.append(subtree)
    return etree.tostring(svg, encoding="utf-8"), (width_px, height_px)


def _standalone_svg_attributes(
    root: etree._Element,
    *,
    width_px: float,
    height_px: float,
) -> dict[str, str]:
    attributes = {
        key: value
        for key, value in root.attrib.items()
        if _preserve_root_attribute(key)
    }
    attributes["width"] = _format_svg_number(width_px)
    attributes["height"] = _format_svg_number(height_px)
    attributes["viewBox"] = root.get("viewBox") or (
        f"0 0 {_format_svg_number(width_px)} {_format_svg_number(height_px)}"
    )
    return attributes


def _preserve_root_attribute(name: str) -> bool:
    local = local_name(name)
    if local in {"width", "height", "viewBox", "x", "y", "id"}:
        return False
    if local in {
        "class",
        "style",
        "lang",
        "color",
        "direction",
        "fill",
        "fill-opacity",
        "fill-rule",
        "font-family",
        "font-feature-settings",
        "font-size",
        "font-stretch",
        "font-style",
        "font-variant",
        "font-weight",
        "letter-spacing",
        "opacity",
        "stroke",
        "stroke-dasharray",
        "stroke-dashoffset",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "stroke-opacity",
        "stroke-width",
        "text-anchor",
        "unicode-bidi",
        "word-spacing",
        "writing-mode",
    }:
        return True
    return name == "{http://www.w3.org/XML/1998/namespace}lang"


def _source_root(element: etree._Element) -> etree._Element:
    try:
        root = element.getroottree().getroot()
    except Exception:
        return element
    return root if isinstance(root, etree._Element) else element


def _source_support_nodes(root: etree._Element) -> list[etree._Element]:
    support_nodes: list[etree._Element] = []
    for node in root.iter():
        if node is root:
            continue
        tag = local_name(getattr(node, "tag", "")).lower()
        if tag == "defs" and not _has_support_ancestor(node, root):
            support_nodes.append(node)
        elif tag == "style" and not _has_defs_ancestor(node, root):
            support_nodes.append(node)
    return support_nodes


def _has_support_ancestor(node: etree._Element, root: etree._Element) -> bool:
    for ancestor in node.iterancestors():
        if ancestor is root:
            return False
        if local_name(getattr(ancestor, "tag", "")).lower() in {"defs", "style"}:
            return True
    return False


def _has_defs_ancestor(node: etree._Element, root: etree._Element) -> bool:
    for ancestor in node.iterancestors():
        if ancestor is root:
            return False
        if local_name(getattr(ancestor, "tag", "")).lower() == "defs":
            return True
    return False


def _source_svg_size(
    root: etree._Element,
    fallback: tuple[float, float],
) -> tuple[float, float]:
    view_box = root.get("viewBox")
    if view_box:
        parts = [part for part in re.split(r"[\s,]+", view_box.strip()) if part]
        if len(parts) == 4:
            try:
                return _positive_pair(
                    float(parts[2]), float(parts[3]), default=fallback
                )
            except ValueError:
                pass
    return _positive_pair(fallback[0], fallback[1], default=(1.0, 1.0))


def _positive_pair(
    width: object,
    height: object,
    *,
    default: tuple[float, float],
) -> tuple[float, float]:
    try:
        w = float(width)
        h = float(height)
    except (TypeError, ValueError):
        return default
    if w <= 0.0 or h <= 0.0:
        return default
    return w, h


def _source_text_subtree(
    element: etree._Element,
    root: etree._Element,
) -> etree._Element | None:
    node = deepcopy(element)
    current = element.getparent()
    while current is not None and current is not root:
        if local_name(getattr(current, "tag", "")).lower() != "defs":
            wrapper = etree.Element(
                current.tag,
                attrib=dict(current.attrib),
                nsmap=current.nsmap,
            )
            wrapper.append(node)
            node = wrapper
        current = current.getparent()
    return node


def _format_svg_number(value: float) -> str:
    if abs(value - round(value)) <= 1e-9:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


__all__ = [
    "bidi_override_fallback_mode",
    "context_viewport_size",
    "dense_rotation_fallback_mode",
    "has_mixed_ltr_rtl_text",
    "source_text_svg_payload",
]
