"""Style and viewport helpers for the split parser components."""

from __future__ import annotations

import re
from typing import Tuple

from lxml import etree

from svg2ooxml.css.resolver import StyleContext
from svg2ooxml.parser.units import UnitConverter


class StyleContextBuilder:
    """Build viewport-aware style contexts mirroring svg2pptx behaviour."""

    def __init__(self, unit_converter: UnitConverter) -> None:
        self._unit_converter = unit_converter

    def build(self, svg_root: etree._Element) -> StyleContext:
        width_px, height_px = self.resolve_viewport(svg_root)
        conversion_ctx = self._unit_converter.create_context(
            width=width_px,
            height=height_px,
            font_size=12.0,
            dpi=self._unit_converter.dpi,
            parent_width=width_px,
            parent_height=height_px,
        )
        return StyleContext(
            conversion=conversion_ctx,
            viewport_width=width_px,
            viewport_height=height_px,
        )

    def resolve_viewport(self, svg_root: etree._Element) -> Tuple[float, float]:
        width_attr = svg_root.get("width")
        height_attr = svg_root.get("height")
        viewbox_attr = svg_root.get("viewBox")

        vb_width = vb_height = None
        if viewbox_attr:
            parts = re.split(r"[\s,]+", viewbox_attr.strip())
            if len(parts) == 4:
                try:
                    _, _, vbw, vbh = map(float, parts)
                    vb_width, vb_height = vbw, vbh
                except ValueError:
                    vb_width = vb_height = None

        width_base = vb_width if vb_width is not None else None
        height_base = vb_height if vb_height is not None else None

        width_px = self._to_pixels(width_attr, base=width_base, fallback=800.0)
        height_px = self._to_pixels(height_attr, base=height_base, fallback=600.0)

        return width_px, height_px

    def _to_pixels(self, value: str | None, *, base: float | None, fallback: float) -> float:
        if not value:
            return base if base is not None else fallback
        token = value.strip()
        if not token:
            return base if base is not None else fallback
        if token.endswith("%"):
            try:
                percent = float(token[:-1]) / 100.0
            except ValueError:
                return base if base is not None else fallback
            reference = base if base is not None else fallback
            return reference * percent
        try:
            return self._unit_converter.to_px(token)
        except Exception:
            return base if base is not None else fallback


__all__ = ["StyleContextBuilder"]
