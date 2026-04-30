"""Resvg paint override handling for shape conversion."""

from __future__ import annotations

from dataclasses import replace

from lxml import etree

from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.ir.paint import PatternPaint, SolidPaint


class ResvgPaintOverrideMixin:
    def _resolved_resvg_paint_opacity(
        self,
        opacity_source: etree._Element | None,
        key: str,
        *,
        fallback_element: etree._Element,
    ) -> float:
        if opacity_source is None:
            opacity_source = fallback_element
        try:
            paint_style = self._style_extractor._compute_paint_style_with_inheritance(
                opacity_source,
                context=self._css_context,
            )
        except Exception:
            return 1.0
        return self._style_opacity(paint_style, key)

    def _apply_resvg_paint_overrides(
        self,
        node,
        base_style: StyleResult,
        *,
        fallback_element: etree._Element,
        preserve_base_paint_opacity: bool = False,
        preserve_base_paint_presence: bool = False,
    ) -> StyleResult:
        updated = base_style
        tree = getattr(self, "_resvg_tree", None)
        if tree is None:
            return updated
        source_element = self._resvg_canonical_source_element(
            getattr(node, "source", None)
        )
        if hasattr(node, "stroke") and node.stroke is not None:
            from svg2ooxml.paint.resvg_bridge import resolve_stroke_style

            resvg_stroke = resolve_stroke_style(node.stroke, tree)
            if resvg_stroke is not None and resvg_stroke.paint is not None:
                if preserve_base_paint_presence and updated.stroke is not None:
                    pass
                elif (
                    preserve_base_paint_presence
                    and updated.stroke is None
                    and not self._source_has_property(source_element, "stroke")
                ):
                    pass
                else:
                    stroke_paint = resvg_stroke.paint
                    if (
                        isinstance(stroke_paint, PatternPaint)
                        and updated.stroke is not None
                        and isinstance(updated.stroke.paint, PatternPaint)
                    ):
                        stroke_paint = self._merge_pattern_paint(
                            stroke_paint,
                            updated.stroke.paint,
                        )
                    elif (
                        isinstance(stroke_paint, PatternPaint)
                        and updated.stroke is not None
                        and isinstance(updated.stroke.paint, SolidPaint)
                    ):
                        stroke_paint = updated.stroke.paint
                    elif preserve_base_paint_opacity and updated.stroke is not None:
                        stroke_paint = self._paint_with_base_opacity(
                            stroke_paint,
                            updated.stroke.paint,
                        )
                    elif preserve_base_paint_opacity:
                        stroke_paint = self._paint_with_opacity(
                            stroke_paint,
                            self._resolved_resvg_paint_opacity(
                                source_element,
                                "stroke_opacity",
                                fallback_element=fallback_element,
                            ),
                        )
                    if updated.stroke is not None:
                        resvg_stroke = replace(
                            resvg_stroke,
                            width=updated.stroke.width,
                            join=updated.stroke.join,
                            cap=updated.stroke.cap,
                            miter_limit=updated.stroke.miter_limit,
                            dash_array=updated.stroke.dash_array,
                            dash_offset=updated.stroke.dash_offset,
                            opacity=updated.stroke.opacity,
                        )
                    updated = replace(
                        updated,
                        stroke=replace(resvg_stroke, paint=stroke_paint),
                    )
        elif self._source_explicitly_disables_paint(source_element, "stroke"):
            updated = replace(updated, stroke=None)
        if hasattr(node, "fill") and node.fill is not None:
            from svg2ooxml.paint.resvg_bridge import resolve_fill_paint

            resvg_fill = resolve_fill_paint(node.fill, tree)
            if resvg_fill is not None:
                if preserve_base_paint_presence and updated.fill is not None:
                    return updated
                if (
                    preserve_base_paint_presence
                    and updated.fill is None
                    and not self._source_has_property(source_element, "fill")
                ):
                    return updated
                if isinstance(resvg_fill, PatternPaint) and isinstance(
                    updated.fill, PatternPaint
                ):
                    resvg_fill = self._merge_pattern_paint(resvg_fill, updated.fill)
                elif isinstance(resvg_fill, PatternPaint) and isinstance(
                    updated.fill, SolidPaint
                ):
                    resvg_fill = updated.fill
                elif preserve_base_paint_opacity:
                    preserved_fill = self._paint_with_base_opacity(
                        resvg_fill,
                        updated.fill,
                    )
                    if preserved_fill is resvg_fill:
                        resvg_fill = self._paint_with_opacity(
                            resvg_fill,
                            self._resolved_resvg_paint_opacity(
                                source_element,
                                "fill_opacity",
                                fallback_element=fallback_element,
                            ),
                        )
                    else:
                        resvg_fill = preserved_fill
                updated = replace(updated, fill=resvg_fill)
            elif self._source_explicitly_disables_paint(source_element, "fill"):
                updated = replace(updated, fill=None)
        elif self._source_explicitly_disables_paint(source_element, "fill"):
            updated = replace(updated, fill=None)
        return updated


__all__ = ["ResvgPaintOverrideMixin"]
