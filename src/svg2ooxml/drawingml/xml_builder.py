"""Centralized XML builders for DrawingML generation.

This module provides safe, reusable lxml-based builders for common DrawingML
XML patterns. All XML generation should use these builders instead of string
concatenation to ensure proper escaping and consistency.

Examples:
    >>> from svg2ooxml.drawingml.xml_builder import solid_fill, to_string
    >>> fill = solid_fill("FF0000", alpha=50000)
    >>> xml = to_string(fill)
    >>> print(xml)
    <a:solidFill><a:srgbClr val="FF0000"><a:alpha val="50000"/></a:srgbClr></a:solidFill>
"""

from __future__ import annotations

from lxml import etree

# DrawingML namespaces (Office Open XML)
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Namespace map for registration
NSMAP = {"a": NS_A, "p": NS_P, "r": NS_R}


def a_elem(tag: str, **attrs: str | int | float) -> etree._Element:
    """Create element with 'a:' namespace (DrawingML main).

    Args:
        tag: Tag name without namespace (e.g., "solidFill")
        **attrs: Attributes as keyword arguments (auto-converted to strings)

    Returns:
        lxml Element with DrawingML namespace

    Example:
        >>> elem = a_elem("srgbClr", val="FF0000")
        >>> to_string(elem)
        '<a:srgbClr val="FF0000"/>'
    """
    elem = etree.Element(f"{{{NS_A}}}{tag}")
    for key, value in attrs.items():
        elem.set(key, str(value))
    return elem


def p_elem(tag: str, **attrs: str | int | float) -> etree._Element:
    """Create element with 'p:' namespace (PresentationML).

    Args:
        tag: Tag name without namespace (e.g., "txBody")
        **attrs: Attributes as keyword arguments (auto-converted to strings)

    Returns:
        lxml Element with PresentationML namespace

    Example:
        >>> elem = p_elem("txBody")
        >>> to_string(elem)
        '<p:txBody/>'
    """
    elem = etree.Element(f"{{{NS_P}}}{tag}")
    for key, value in attrs.items():
        elem.set(key, str(value))
    return elem


def a_sub(parent: etree._Element, tag: str, **attrs: str | int | float) -> etree._Element:
    """Create and append child element with 'a:' namespace.

    Args:
        parent: Parent element to append to
        tag: Tag name without namespace
        **attrs: Attributes as keyword arguments

    Returns:
        Created child element

    Example:
        >>> parent = a_elem("solidFill")
        >>> child = a_sub(parent, "srgbClr", val="FF0000")
    """
    elem = etree.SubElement(parent, f"{{{NS_A}}}{tag}")
    for key, value in attrs.items():
        elem.set(key, str(value))
    return elem


def p_sub(parent: etree._Element, tag: str, **attrs: str | int | float) -> etree._Element:
    """Create and append child element with 'p:' namespace.

    Args:
        parent: Parent element to append to
        tag: Tag name without namespace
        **attrs: Attributes as keyword arguments

    Returns:
        Created child element
    """
    elem = etree.SubElement(parent, f"{{{NS_P}}}{tag}")
    for key, value in attrs.items():
        elem.set(key, str(value))
    return elem


def to_string(elem: etree._Element) -> str:
    """Serialize element to XML string with namespace prefixes.

    Converts namespace URIs to a:/p: prefixes for Office compatibility.
    Strips namespace declarations for cleaner output.

    Args:
        elem: lxml Element to serialize

    Returns:
        XML string with a: and p: namespace prefixes

    Example:
        >>> elem = a_elem("solidFill")
        >>> to_string(elem)
        '<a:solidFill/>'
    """
    # Serialize with namespaces
    xml_str = etree.tostring(elem, encoding="unicode")

    # lxml uses ns0:, ns1:, etc. for undefined prefixes
    import re

    # Build a map of nsX: -> proper prefix (a:, p:, or r:)
    # by parsing xmlns declarations before we strip them
    ns_map = {}
    xmlns_pattern = r'xmlns:(ns\d+)="([^"]+)"'
    for match in re.finditer(xmlns_pattern, xml_str):
        ns_prefix = match.group(1)  # e.g., "ns0"
        uri = match.group(2)  # e.g., "http://schemas.openxmlformats.org/drawingml/2006/main"

        if uri == NS_A:
            ns_map[ns_prefix] = "a"
        elif uri == NS_P:
            ns_map[ns_prefix] = "p"
        elif uri == NS_R:
            ns_map[ns_prefix] = "r"

    # Remove xmlns declarations
    xml_str = re.sub(r'\s+xmlns:ns\d+="[^"]+"', '', xml_str)

    # Replace nsX: prefixes with proper a:, p:, or r: prefixes
    for ns_prefix, proper_prefix in ns_map.items():
        xml_str = xml_str.replace(f'<{ns_prefix}:', f'<{proper_prefix}:')
        xml_str = xml_str.replace(f'</{ns_prefix}:', f'</{proper_prefix}:')
        xml_str = xml_str.replace(f' {ns_prefix}:', f' {proper_prefix}:')

    return xml_str


def graft_xml_fragment(
    parent: etree._Element,
    xml: str,
    *,
    namespaces: dict[str, str] | None = None,
) -> None:
    """Parse an XML fragment string and append its children to *parent*.

    Transitional helper for migrating from string-returning producers to
    element-returning producers.  New code should NOT call this; instead
    have producers return ``etree._Element`` directly.

    Args:
        parent: Target element to append children to.
        xml: Raw XML fragment (may contain multiple root-level elements).
        namespaces: Namespace prefixes for the wrapper root.
            Defaults to ``{"a": NS_A}`` when *None*.
    """
    if not xml or not xml.strip():
        return
    if namespaces is None:
        namespaces = {"a": NS_A}
    ns_decls = " ".join(
        f'xmlns:{prefix}="{uri}"' for prefix, uri in namespaces.items()
    )
    wrapped = f"<root {ns_decls}>{xml}</root>"
    temp = etree.fromstring(wrapped.encode("utf-8"))
    for child in temp:
        parent.append(child)


# ============================================================================
# Common DrawingML Builders
# ============================================================================


def solid_fill(rgb: str, alpha: int = 100000) -> etree._Element:
    """Create <a:solidFill> element with sRGB color.

    Args:
        rgb: 6-character hex color without # (e.g., "FF0000" for red)
        alpha: Alpha value 0-100000 (default: 100000 = fully opaque)
               100000 = 100%, 50000 = 50%, 0 = fully transparent

    Returns:
        <a:solidFill> element with nested <a:srgbClr> and optional <a:alpha>

    Example:
        >>> fill = solid_fill("FF0000", alpha=50000)
        >>> to_string(fill)
        '<a:solidFill><a:srgbClr val="FF0000"><a:alpha val="50000"/></a:srgbClr></a:solidFill>'
    """
    solidFill = a_elem("solidFill")
    srgbClr = a_sub(solidFill, "srgbClr", val=rgb.upper())

    # Only add alpha if not fully opaque
    if alpha < 100000:
        a_sub(srgbClr, "alpha", val=alpha)

    return solidFill


def srgb_color(rgb: str, alpha: int | None = None) -> etree._Element:
    """Create <a:srgbClr> element with optional alpha.

    Args:
        rgb: 6-character hex color without # (e.g., "FF0000")
        alpha: Optional alpha value 0-100000

    Returns:
        <a:srgbClr> element with optional <a:alpha> child

    Example:
        >>> color = srgb_color("00FF00", alpha=75000)
        >>> to_string(color)
        '<a:srgbClr val="00FF00"><a:alpha val="75000"/></a:srgbClr>'
    """
    srgbClr = a_elem("srgbClr", val=rgb.upper())

    if alpha is not None:
        a_sub(srgbClr, "alpha", val=alpha)

    return srgbClr


def no_fill() -> etree._Element:
    """Create <a:noFill/> element.

    Returns:
        <a:noFill/> element

    Example:
        >>> nofill = no_fill()
        >>> to_string(nofill)
        '<a:noFill/>'
    """
    return a_elem("noFill")


def effect_list(*effects: etree._Element) -> etree._Element:
    """Create <a:effectLst> containing child effects.

    Args:
        *effects: Effect elements to include (blur, glow, shadow, etc.)

    Returns:
        <a:effectLst> element containing all effects

    Example:
        >>> blur = a_elem("blur", rad="100000")
        >>> glow = a_elem("glow", rad="50000")
        >>> effects = effect_list(blur, glow)
        >>> to_string(effects)
        '<a:effectLst><a:blur rad="100000"/><a:glow rad="50000"/></a:effectLst>'
    """
    effectLst = a_elem("effectLst")
    for effect in effects:
        effectLst.append(effect)
    return effectLst


def ln(width_emu: int, fill_elem: etree._Element | None = None, **attrs: str | int) -> etree._Element:
    """Create <a:ln> line/stroke element.

    Args:
        width_emu: Line width in EMUs
        fill_elem: Optional fill element (solidFill, noFill, etc.)
        **attrs: Additional line attributes (cap, cmpd, algn, etc.)

    Returns:
        <a:ln> element with fill and attributes

    Example:
        >>> line = ln(12700, solid_fill("000000"))
        >>> to_string(line)
        '<a:ln w="12700"><a:solidFill><a:srgbClr val="000000"/></a:solidFill></a:ln>'
    """
    line = a_elem("ln", w=width_emu, **attrs)

    if fill_elem is not None:
        line.append(fill_elem)

    return line


def blur(radius_emu: int) -> etree._Element:
    """Create <a:blur> effect element.

    Args:
        radius_emu: Blur radius in EMUs

    Returns:
        <a:blur> element

    Example:
        >>> blur_effect = blur(100000)
        >>> to_string(blur_effect)
        '<a:blur rad="100000"/>'
    """
    return a_elem("blur", rad=radius_emu)


def glow(radius_emu: int, color_elem: etree._Element) -> etree._Element:
    """Create <a:glow> effect element.

    Args:
        radius_emu: Glow radius in EMUs
        color_elem: Color element (srgbClr, schemeClr, etc.)

    Returns:
        <a:glow> element with color

    Example:
        >>> color = srgb_color("FF0000", alpha=50000)
        >>> glow_effect = glow(50000, color)
        >>> to_string(glow_effect)
        '<a:glow rad="50000"><a:srgbClr val="FF0000"><a:alpha val="50000"/></a:srgbClr></a:glow>'
    """
    glow_elem = a_elem("glow", rad=radius_emu)
    glow_elem.append(color_elem)
    return glow_elem


def outer_shadow(
    blur_rad: int,
    dist: int,
    dir_angle: int,
    color_elem: etree._Element,
    **attrs: str | int,
) -> etree._Element:
    """Create <a:outerShdw> outer shadow effect.

    Args:
        blur_rad: Blur radius in EMUs
        dist: Distance in EMUs
        dir_angle: Direction angle in 60000ths of a degree (e.g., 2700000 = 45°)
        color_elem: Color element
        **attrs: Additional attributes (algn, rotWithShape, etc.)

    Returns:
        <a:outerShdw> element

    Example:
        >>> color = srgb_color("000000", alpha=50000)
        >>> shadow = outer_shadow(100000, 50000, 2700000, color)
        >>> to_string(shadow)
        '<a:outerShdw blurRad="100000" dist="50000" dir="2700000"><a:srgbClr val="000000"><a:alpha val="50000"/></a:srgbClr></a:outerShdw>'
    """
    shadow = a_elem("outerShdw", blurRad=blur_rad, dist=dist, dir=dir_angle, **attrs)
    shadow.append(color_elem)
    return shadow


def soft_edge(radius_emu: int) -> etree._Element:
    """Create <a:softEdge> effect element.

    Args:
        radius_emu: Soft edge radius in EMUs

    Returns:
        <a:softEdge> element

    Example:
        >>> edge = soft_edge(25000)
        >>> to_string(edge)
        '<a:softEdge rad="25000"/>'
    """
    return a_elem("softEdge", rad=radius_emu)


def reflection(blur_rad: int, dist: int, start_alpha: int, end_alpha: int) -> etree._Element:
    """Create <a:reflection> effect element.

    Args:
        blur_rad: Blur radius in EMUs
        dist: Distance in EMUs
        start_alpha: Start alpha value 0-100000
        end_alpha: End alpha value 0-100000

    Returns:
        <a:reflection> element

    Example:
        >>> refl = reflection(100000, 50000, 80000, 0)
        >>> to_string(refl)
        '<a:reflection blurRad="100000" dist="50000" stA="80000" endA="0"/>'
    """
    return a_elem("reflection", blurRad=blur_rad, dist=dist, stA=start_alpha, endA=end_alpha)


__all__ = [
    # Core builders
    "a_elem",
    "p_elem",
    "a_sub",
    "p_sub",
    "to_string",
    "graft_xml_fragment",
    # Common patterns
    "solid_fill",
    "srgb_color",
    "no_fill",
    "effect_list",
    "ln",
    # Effects
    "blur",
    "glow",
    "outer_shadow",
    "soft_edge",
    "reflection",
    # Namespaces (for advanced usage)
    "NS_A",
    "NS_P",
    "NS_R",
    "NSMAP",
]
