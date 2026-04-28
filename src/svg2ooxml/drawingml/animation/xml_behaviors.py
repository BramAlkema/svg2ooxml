"""Behavior XML helpers for PowerPoint animation timing."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.drawingml.xml_builder import p_elem, p_sub

from .timing_values import format_duration_ms, repeat_count_value


class AnimationBehaviorXMLMixin:
    """Build common behavior cores and simple set behaviors."""

    def build_behavior_core_elem(
        self,
        *,
        behavior_id: int,
        duration_ms: int,
        target_shape: str,
        repeat_count: str | int | None = None,
        fill_mode: str | None = None,
        additive: str | None = None,
        accel: int | None = None,
        decel: int | None = None,
        attr_name_list: list[str] | None = None,
        auto_reverse: bool = False,
        override: str | None = None,
    ) -> etree._Element:
        """Build ``<p:cBhvr>`` common behavior element."""
        cBhvr = p_elem("cBhvr")

        if self._needs_ppt_runtime_context(attr_name_list):
            cBhvr.set("rctx", "PPT")
        if override:
            cBhvr.set("override", override)

        ppt_fill = "remove" if fill_mode == "remove" else "hold"
        ctn_attrs: dict[str, str] = {
            "id": str(behavior_id),
            "dur": format_duration_ms(duration_ms),
            "fill": ppt_fill,
            "nodeType": "withEffect",
        }
        ppt_repeat = repeat_count_value(repeat_count)
        if ppt_repeat is not None:
            ctn_attrs["repeatCount"] = ppt_repeat
        if accel is not None:
            ctn_attrs["accel"] = str(accel)
        if decel is not None:
            ctn_attrs["decel"] = str(decel)
        if auto_reverse:
            ctn_attrs["autoRev"] = "1"

        p_sub(cBhvr, "cTn", **ctn_attrs)

        tgt_el = p_sub(cBhvr, "tgtEl")
        p_sub(tgt_el, "spTgt", spid=target_shape)

        if attr_name_list is not None:
            cBhvr.append(self.build_attribute_list(attr_name_list))

        return cBhvr

    @staticmethod
    def _repeat_count_value(repeat_count: str | int | None) -> str | None:
        return repeat_count_value(repeat_count)

    @staticmethod
    def _needs_ppt_runtime_context(attr_name_list: list[str] | None) -> bool:
        """Return True when the behavior targets PPT runtime-only properties."""
        if not attr_name_list:
            return False
        return any(
            name.startswith("ppt_") or name.startswith("style.")
            for name in attr_name_list
        )

    def build_set_elem(
        self,
        *,
        behavior_id: int,
        duration_ms: int,
        target_shape: str,
        ppt_attribute: str,
        fill_mode: str | None = None,
        additive: str | None = None,
        repeat_count: str | int | None = None,
    ) -> etree._Element:
        """Build ``<p:set>`` element with behavior core."""
        set_elem = p_elem("set")
        cBhvr = self.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=duration_ms,
            target_shape=target_shape,
            attr_name_list=[ppt_attribute],
            fill_mode=fill_mode,
            additive=additive,
            repeat_count=repeat_count,
        )
        set_elem.append(cBhvr)
        return set_elem


__all__ = ["AnimationBehaviorXMLMixin"]
