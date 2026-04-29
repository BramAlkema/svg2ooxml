"""Mask baking utilities for IR elements."""

from __future__ import annotations

import logging
from typing import Any

from lxml import etree

from svg2ooxml.common.boundaries import parse_wrapped_xml_fragment
from svg2ooxml.common.conversions.opacity import parse_opacity
from svg2ooxml.common.gradient_units import parse_gradient_offset
from svg2ooxml.common.style.css_values import parse_style_declarations
from svg2ooxml.common.units.lengths import parse_number_or_percent
from svg2ooxml.ir.paint import GradientStop, LinearGradientPaint, Paint, SolidPaint
from svg2ooxml.ir.scene import MaskRef

logger = logging.getLogger(__name__)

def try_bake_mask(fill: Paint, mask_ref: MaskRef | None, services: Any = None, doc_root: etree._Element | None = None) -> tuple[Paint, MaskRef | None]:
    """Attempt to bake a simple gradient mask into a solid fill.
    
    Returns:
        (new_fill, new_mask_ref)
    """
    if mask_ref is None or not isinstance(fill, SolidPaint):
        return fill, mask_ref
        
    definition = mask_ref.definition
    if definition is None or not definition.content_xml:
        return fill, mask_ref
        
    try:
        combined_xml = "".join(definition.content_xml)
        root = parse_wrapped_xml_fragment(
            combined_xml,
            namespaces={"svg": "http://www.w3.org/2000/svg"},
        )
        
        ns = {"svg": "http://www.w3.org/2000/svg"}
        
        # Helper to find gradient by ID in definitions or doc_root
        def find_grad_by_id(grad_id):
            if not grad_id:
                return None
            found = _find_linear_gradient_by_id(root, grad_id, ns)
            if found is not None:
                return found

            # Search in document root if available
            if doc_root is not None:
                return _find_linear_gradient_by_id(doc_root, grad_id, ns)
            return None

        # 1. Look for linearGradient directly in the mask content
        grad = root.xpath(".//svg:linearGradient", namespaces=ns) or root.xpath(".//linearGradient")
        
        # 2. If not found, check if a rect/path uses a gradient
        if not grad:
            shapes = root.xpath(".//*[contains(@fill, 'url(#')]")
            if shapes:
                fill_attr = shapes[0].get("fill")
                grad_id = fill_attr.split("#")[1].split(")")[0]
                g_elem = find_grad_by_id(grad_id)
                if g_elem is not None:
                    grad = [g_elem]

        if grad and len(grad) >= 1:
            g = grad[0]
            stops = []
            for stop in g.xpath(".//svg:stop", namespaces=ns) or g.xpath(".//stop"):
                offset = parse_gradient_offset(stop.get("offset", "0"))
                
                # Check style attribute too
                style = _parse_style(stop.get("style"))
                color = stop.get("stop-color") or style.get("stop-color") or "#ffffff"
                stop_opacity = parse_opacity(
                    stop.get("stop-opacity") or style.get("stop-opacity") or "1.0"
                )
                
                brightness = _calculate_luminance(color)
                effective_alpha = brightness * stop_opacity
                stops.append(
                    GradientStop(
                        offset=offset,
                        rgb=fill.rgb,
                        opacity=effective_alpha,
                        theme_color=getattr(fill, "theme_color", None),
                    )
                )
            
            if len(stops) >= 2:
                x1 = _parse_coord(g.get("x1", "0%"))
                y1 = _parse_coord(g.get("y1", "0%"))
                x2 = _parse_coord(g.get("x2", "100%"))
                y2 = _parse_coord(g.get("y2", "0%"))
                
                new_fill = LinearGradientPaint(
                    stops=stops,
                    start=(x1, y1),
                    end=(x2, y2),
                    gradient_units=g.get("gradientUnits", "objectBoundingBox"),
                    spread_method=g.get("spreadMethod", "pad"),
                )
                
                logger.info("Baked mask %s into gradient fill", mask_ref.mask_id)
                return new_fill, None
                
    except Exception as e:
        logger.debug("Failed to bake mask: %s", e)
        
    return fill, mask_ref

def _parse_coord(val: str | None) -> float:
    return parse_number_or_percent(val, 0.0)

def _calculate_luminance(color: str) -> float:
    color = color.strip().lstrip("#")
    if len(color) == 3:
        color = "".join(ch * 2 for ch in color)
    if len(color) != 6:
        return 1.0
        
    try:
        r = int(color[0:2], 16) / 255.0
        g = int(color[2:4], 16) / 255.0
        b = int(color[4:6], 16) / 255.0
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    except ValueError:
        return 1.0

def _parse_style(style_str: str | None) -> dict[str, str]:
    return parse_style_declarations(style_str)[0]


def _find_linear_gradient_by_id(
    root: etree._Element,
    grad_id: str,
    namespaces: dict[str, str],
) -> etree._Element | None:
    gradients = root.xpath("//svg:linearGradient", namespaces=namespaces) or root.xpath(
        "//*[local-name()='linearGradient']"
    )
    for gradient in gradients:
        if gradient.get("id") == grad_id:
            return gradient
    return None
