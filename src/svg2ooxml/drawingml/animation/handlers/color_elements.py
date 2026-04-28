"""Element builders for color animation handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import a_sub, p_elem, p_sub

if TYPE_CHECKING:
    pass


class ColorElementMixin:
    """Low-level ``animClr`` builders used by ``ColorAnimationHandler``."""

    def _build_anim_clr_element(
        self,
        *,
        behavior_id: int,
        duration_ms: int,
        target_shape: str,
        ppt_attribute: str,
        from_color: str,
        to_color: str,
        additive: str,
        fill_mode: str,
        repeat_count: int | str | None,
    ) -> etree._Element:
        from_hex = self._processor.parse_color(from_color)
        to_hex = self._processor.parse_color(to_color)

        anim_clr = p_elem("animClr", clrSpc="rgb", dir="cw")
        c_bhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=duration_ms,
            target_shape=target_shape,
            attr_name_list=[ppt_attribute],
            additive=additive,
            fill_mode=fill_mode,
            repeat_count=repeat_count,
            override="childStyle",
        )
        anim_clr.append(c_bhvr)

        from_elem = p_sub(anim_clr, "from")
        a_sub(from_elem, "srgbClr", val=from_hex)

        to_elem = p_sub(anim_clr, "to")
        a_sub(to_elem, "srgbClr", val=to_hex)

        return anim_clr
