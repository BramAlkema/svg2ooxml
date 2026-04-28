"""Effect cleanup and paint-order helpers for DrawingML shape rendering."""

from __future__ import annotations

from dataclasses import replace

from svg2ooxml.ir.effects import CustomEffect

from .shape_renderer_utils import is_invalid_custom_effect_xml


class ShapeRendererEffectsMixin:
    """Handle shape effect sanitizing and paint-order decomposition."""

    def _render_reversed_paint_order(
        self,
        element,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        """Emit stroke-only shape behind fill-only shape for reversed paint order."""
        stroke_element = replace(element, fill=None)
        fill_element = replace(element, stroke=None)

        clean_meta = dict(metadata)
        clean_meta.pop("paint_order", None)

        stroke_result = self.render(
            stroke_element,
            shape_id,
            clean_meta,
            hyperlink_xml="",
        )
        if stroke_result is None:
            return self.render(element, shape_id, clean_meta, hyperlink_xml=hyperlink_xml)

        stroke_xml, next_id = stroke_result
        fill_result = self.render(
            fill_element,
            next_id,
            clean_meta,
            hyperlink_xml=hyperlink_xml,
        )
        if fill_result is None:
            return stroke_xml, next_id

        fill_xml, final_id = fill_result
        return stroke_xml + fill_xml, final_id

    def _strip_invalid_filter_effects(self, element):
        effects = getattr(element, "effects", None)
        if not effects:
            return element
        cleaned = []
        for effect in effects:
            if isinstance(effect, CustomEffect):
                xml = effect.drawingml or ""
                if is_invalid_custom_effect_xml(
                    xml,
                    invalid_substrings=self._INVALID_EFFECT_SUBSTRINGS,
                ):
                    continue
            cleaned.append(effect)
        if len(cleaned) == len(effects):
            return element
        try:
            return replace(element, effects=cleaned)
        except TypeError:
            try:
                element.effects = cleaned
            except Exception:  # pragma: no cover - defensive
                return element
            return element


__all__ = ["ShapeRendererEffectsMixin"]
