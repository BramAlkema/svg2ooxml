"""Mask baking utilities for IR elements."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from lxml import etree

from svg2ooxml.ir.paint import LinearGradientPaint, SolidPaint, GradientStop, Paint
from svg2ooxml.ir.scene import MaskRef, MaskDefinition

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
        root = etree.fromstring(f"<root xmlns:svg='http://www.w3.org/2000/svg'>{combined_xml}</root>")
        
        ns = {"svg": "http://www.w3.org/2000/svg"}
        
        # Helper to find gradient by ID in definitions or doc_root
        def find_grad_by_id(grad_id):
            if not grad_id: return None
            # Search in the mask content itself first
            g = root.xpath(f"//svg:linearGradient[@id='{grad_id}']", namespaces=ns) or \
                root.xpath(f"//linearGradient[@id='{grad_id}']")
            if g: return g[0]
            
            # Search in document root if available
            if doc_root is not None:
                g = doc_root.xpath(f"//svg:linearGradient[@id='{grad_id}']", namespaces=ns) or \
                    doc_root.xpath(f"//linearGradient[@id='{grad_id}']")
                if g: return g[0]
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
                offset = _parse_percent(stop.get("offset", "0"))
                
                # Check style attribute too
                style = _parse_style(stop.get("style"))
                color = stop.get("stop-color") or style.get("stop-color") or "#ffffff"
                stop_opacity = _parse_float(stop.get("stop-opacity") or style.get("stop-opacity") or "1.0")
                
                brightness = _calculate_luminance(color)
                effective_alpha = brightness * stop_opacity
                stops.append(GradientStop(offset=offset, rgb=fill.rgb, opacity=effective_alpha))
            
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

def _parse_percent(val: str) -> float:
    val = val.strip()
    if val.endswith("%"):
        return float(val[:-1]) / 100.0
    try:
        return float(val)
    except ValueError:
        return 0.0

def _parse_coord(val: str) -> float:
    if val is None: return 0.0
    val = val.strip()
    if val.endswith("%"):
        return float(val[:-1]) / 100.0
    try:
        return float(val)
    except ValueError:
        return 0.0

def _parse_float(val: str) -> float:
    if val is None: return 1.0
    try:
        return float(val)
    except ValueError:
        return 1.0

def _calculate_luminance(color: str) -> float:
    color = color.strip().lstrip("#")
    if len(color) == 3:
        color = "".join(c*2 for ch in color)
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
    if not style_str: return {}
    parts = [p.split(":", 1) for p in style_str.split(";") if ":" in p]
    return {k.strip(): v.strip() for k, v in parts}