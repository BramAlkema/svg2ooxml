"""Behavior fragment rendering for compound oracle slots."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.common.boundaries import safe_lxml_parser
from svg2ooxml.drawingml.animation.oracle_templates import (
    find_template_tokens,
    render_xml_template,
    resolve_oracle_child_path,
)
from svg2ooxml.drawingml.animation.oracle_types import (
    NS_A,
    BehaviorFragment,
    OracleSlotError,
)
from svg2ooxml.drawingml.xml_builder import NS_P


class OracleFragmentMixin:
    """Render behavior fragment XML files into detached child elements."""

    def _render_behavior_fragment(
        self,
        fragment: BehaviorFragment,
        *,
        shape_id: str | int,
        duration_ms: int,
    ) -> list[etree._Element]:
        """Load a behavior fragment file and return its substituted children."""
        try:
            behavior_root = resolve_oracle_child_path(self._root, "emph", "behaviors")
            fragment_path = resolve_oracle_child_path(
                behavior_root,
                f"{fragment.name}.xml",
            )
        except ValueError as exc:
            raise OracleSlotError(
                f"Behavior fragment '{fragment.name}' escapes oracle root"
            ) from exc
        if not fragment_path.is_file():
            raise OracleSlotError(
                f"Behavior fragment '{fragment.name}' not found at {fragment_path}"
            )
        text = fragment_path.read_text(encoding="utf-8")

        substitutions: dict[str, str] = {
            "SHAPE_ID": str(shape_id),
            "DURATION_MS": str(duration_ms),
            "INNER_FILL": "hold",
        }
        for key, value in fragment.tokens.items():
            substitutions[str(key)] = str(value)
        template_tokens = find_template_tokens(text)
        extra_tokens = set(map(str, fragment.tokens)) - template_tokens
        if extra_tokens:
            raise ValueError(
                f"Behavior fragment '{fragment.name}' got unknown tokens: "
                f"{', '.join(sorted(extra_tokens))}"
            )
        rendered = render_xml_template(text, substitutions)

        wrapped = f'<root xmlns:p="{NS_P}" xmlns:a="{NS_A}">{rendered}</root>'
        parser = safe_lxml_parser(remove_blank_text=True)
        root = etree.fromstring(wrapped.encode("utf-8"), parser)
        fragment_elem = root.find("fragment")
        if fragment_elem is None:
            raise OracleSlotError(
                f"Behavior fragment '{fragment.name}' is missing <fragment> root"
            )
        children = list(fragment_elem)
        for child in children:
            fragment_elem.remove(child)
        return children


__all__ = ["OracleFragmentMixin"]
