"""Hook comment parsing and native effect builders for filter rendering."""

from __future__ import annotations

import math
import re

from lxml import etree

from svg2ooxml.color.utils import color_to_hex
from svg2ooxml.common.conversions.angles import radians_to_ppt
from svg2ooxml.common.conversions.opacity import opacity_to_ppt, parse_opacity
from svg2ooxml.common.units import px_to_emu
from svg2ooxml.common.units.lengths import parse_number
from svg2ooxml.common.units.scalars import EMU_PER_INCH
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string

HOOK_PATTERN = re.compile(r"<!--\s*svg2ooxml:(?P<name>\w+)(?P<attrs>[^>]*)-->", re.IGNORECASE)
ATTR_PATTERN = re.compile(r"(\w+)=\"([^\"]*)\"")


class FilterRendererHookMixin:
    """Parse primitive hooks and build simple DrawingML fragments."""

    def _hook_builders(self):
        return {
            "flood": self._build_flood,
            "offset": self._build_offset,
            "merge": self._build_pass_through,
            "tile": self._build_pass_through,
            "composite": self._build_pass_through,
            "blend": self._build_pass_through,
            "componentTransfer": self._build_comment_only,
            "convolveMatrix": self._build_comment_only,
            "image": self._build_comment_only,
            "diffuseLighting": self._build_comment_only,
            "specularLighting": self._build_comment_only,
        }

    def _build_flood(self, name, attrs, remainder, result, context) -> str:
        color = color_to_hex(attrs.get("color"), default="000000")
        opacity = parse_opacity(attrs.get("opacity"), default=1.0)
        alpha = opacity_to_ppt(opacity)

        effectLst = a_elem("effectLst")
        solidFill = a_sub(effectLst, "solidFill")
        srgbClr = a_sub(solidFill, "srgbClr", val=color)
        a_sub(srgbClr, "alpha", val=alpha)
        return to_string(effectLst)

    def _build_offset(self, name, attrs, remainder, result, context) -> str:
        dx = parse_number(attrs.get("dx"), 0.0)
        dy = parse_number(attrs.get("dy"), 0.0)

        dx_emu = int(px_to_emu(dx))
        dy_emu = int(px_to_emu(dy))
        distance = int(math.hypot(dx_emu, dy_emu))

        effectLst = a_elem("effectLst")
        if distance == 0:
            effectLst.append(etree.Comment(" offset: no displacement "))
            return to_string(effectLst)

        angle_rad = math.atan2(dy_emu, dx_emu)
        ppt_angle = radians_to_ppt(angle_rad % (2 * math.pi))
        distance = min(distance, EMU_PER_INCH)

        outerShdw = a_sub(
            effectLst,
            "outerShdw",
            blurRad="0",
            dist=distance,
            dir=ppt_angle,
            algn="ctr",
        )
        srgbClr = a_sub(outerShdw, "srgbClr", val="000000")
        a_sub(srgbClr, "alpha", val="0")
        return to_string(effectLst)

    def _build_pass_through(self, name, attrs, remainder, result, context) -> str:
        if remainder:
            return remainder
        return self._build_comment(name, attrs)

    def _build_comment_only(self, name, attrs, remainder, result, context) -> str:
        return self._build_comment(name, attrs)

    def _extract_hook(self, drawingml: str):
        match = HOOK_PATTERN.search(drawingml)
        if not match:
            return None, {}, drawingml
        prefix = drawingml[: match.start()]
        if prefix.strip():
            return None, {}, drawingml
        name = match.group("name")
        attr_block = match.group("attrs") or ""
        attrs = {m.group(1): m.group(2) for m in ATTR_PATTERN.finditer(attr_block)}
        remainder = drawingml[match.end() :].strip()
        return name, attrs, remainder

    def _build_comment(self, name: str, attrs: dict[str, str]) -> str:
        if not attrs:
            return self._comment_xml(f"svg2ooxml:{name}")
        pairs = " ".join(f'{key}="{value}"' for key, value in attrs.items())
        return self._comment_xml(f"svg2ooxml:{name} {pairs}")


__all__ = ["ATTR_PATTERN", "HOOK_PATTERN", "FilterRendererHookMixin"]
