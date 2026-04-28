"""Single-slot animation oracle instantiation."""

from __future__ import annotations

from typing import Any

from lxml import etree

from svg2ooxml.common.boundaries import safe_lxml_parser
from svg2ooxml.drawingml.animation.oracle_templates import render_xml_template
from svg2ooxml.drawingml.animation.oracle_types import _BUILD_MODE_ATTR, NS_A
from svg2ooxml.drawingml.xml_builder import NS_P


class OracleInstantiationMixin:
    """Instantiate one parameterized oracle slot into a timing subtree."""

    def instantiate(
        self,
        slot_name: str,
        *,
        shape_id: str | int,
        par_id: int,
        duration_ms: int,
        delay_ms: int = 0,
        **tokens: Any,
    ) -> etree._Element:
        """Return a fully substituted ``<p:par>`` element."""
        slot = self.slot(slot_name)
        substitutions: dict[str, str] = {
            "SHAPE_ID": str(shape_id),
            "PAR_ID": str(par_id),
            "DURATION_MS": str(duration_ms),
            "DELAY_MS": str(delay_ms),
        }
        for name in slot.behavior_tokens:
            if name not in tokens:
                raise ValueError(f"Slot '{slot_name}' requires behavior token '{name}'")
            substitutions[name] = str(tokens.pop(name))
        for name in slot.content_tokens:
            if name not in tokens:
                raise ValueError(f"Slot '{slot_name}' requires content token '{name}'")
            substitutions[name] = str(tokens.pop(name))
        if tokens:
            unknown = ", ".join(sorted(tokens))
            raise ValueError(f"Unknown tokens for slot '{slot_name}': {unknown}")

        text = self.template_text(slot_name)
        rendered = render_xml_template(text, substitutions)

        wrapped = f'<root xmlns:p="{NS_P}" xmlns:a="{NS_A}">{rendered}</root>'
        parser = safe_lxml_parser(remove_blank_text=True)
        root = etree.fromstring(wrapped.encode("utf-8"), parser)
        par = root[0]
        par.set(_BUILD_MODE_ATTR, slot.bld_mode)
        root.remove(par)
        return par


__all__ = ["OracleInstantiationMixin"]
