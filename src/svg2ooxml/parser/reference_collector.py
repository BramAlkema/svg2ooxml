"""Reference collection helpers for parser subsystems."""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"


@dataclass
class ParserReferences:
    masks: dict[str, dict] = field(default_factory=dict)
    symbols: dict[str, etree._Element] = field(default_factory=dict)
    filters: dict[str, etree._Element] = field(default_factory=dict)
    markers: dict[str, etree._Element] = field(default_factory=dict)


def collect_references(svg_root: etree._Element) -> ParserReferences:
    references = ParserReferences()
    references.masks = {}
    namespaces = _build_namespace_map(svg_root)
    references.symbols = _collect_symbols(svg_root, namespaces)
    references.filters = _collect_filters(svg_root, namespaces)
    references.markers = _collect_markers(svg_root, namespaces)
    return references


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_namespace_map(svg_root: etree._Element) -> dict[str, str]:
    namespaces = {k or "svg": v for k, v in (svg_root.nsmap or {}).items() if v}
    if "svg" not in namespaces:
        namespaces["svg"] = SVG_NS
    return namespaces


def _collect_by_xpath(
    svg_root: etree._Element, xpath: str, namespaces: dict[str, str]
) -> list[etree._Element]:
    try:
        return list(svg_root.xpath(xpath, namespaces=namespaces))
    except Exception:
        return []


def _collect_symbols(
    svg_root: etree._Element, namespaces: dict[str, str]
) -> dict[str, etree._Element]:
    symbols: dict[str, etree._Element] = {}
    elements = _collect_by_xpath(svg_root, ".//svg:symbol", namespaces)
    if not elements:
        elements = list(svg_root.findall(f".//{{{SVG_NS}}}symbol"))
    if not elements:
        elements = list(svg_root.findall(".//symbol"))
    for element in elements:
        symbol_id = element.get("id")
        if not symbol_id:
            continue
        symbols[symbol_id] = element
    return symbols


def _collect_filters(
    svg_root: etree._Element, namespaces: dict[str, str]
) -> dict[str, etree._Element]:
    filters: dict[str, etree._Element] = {}
    elements = _collect_by_xpath(svg_root, ".//svg:filter", namespaces)
    if not elements:
        elements = list(svg_root.findall(f".//{{{SVG_NS}}}filter"))
    if not elements:
        elements = list(svg_root.findall(".//filter"))
    for element in elements:
        filter_id = element.get("id")
        if not filter_id:
            continue
        filters[filter_id] = element
    return filters


def _collect_markers(
    svg_root: etree._Element, namespaces: dict[str, str]
) -> dict[str, etree._Element]:
    markers: dict[str, etree._Element] = {}
    elements = _collect_by_xpath(svg_root, ".//svg:marker", namespaces)
    if not elements:
        elements = list(svg_root.findall(f".//{{{SVG_NS}}}marker"))
    if not elements:
        elements = list(svg_root.findall(".//marker"))
    for element in elements:
        marker_id = element.get("id")
        if not marker_id:
            continue
        markers[marker_id] = element
    return markers


__all__ = ["collect_references", "ParserReferences"]
