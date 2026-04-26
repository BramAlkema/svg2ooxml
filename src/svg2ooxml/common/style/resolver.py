"""CSS style resolver with tinycss2-backed parsing."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.common.style.cascade import StylesheetCascade
from svg2ooxml.common.style.model import (
    CSSDeclaration,
    CSSOrigin,
    CSSRule,
    PropertyDescriptor,
    StyleContext,
)
from svg2ooxml.common.style.paint import (
    apply_stylesheet_paints as _apply_stylesheet_paints,
)
from svg2ooxml.common.style.paint import (
    compute_paint_style as _compute_paint_style,
)
from svg2ooxml.common.style.selectors import (
    CompiledSelector,
    SelectorPart,
)
from svg2ooxml.common.style.text import (
    TEXT_ATTRIBUTE_MAP,
    TEXT_DEFAULTS,
)
from svg2ooxml.common.style.text import (
    apply_stylesheet_text as _apply_stylesheet_text,
)
from svg2ooxml.common.style.text import (
    compute_text_style as _compute_text_style,
)
from svg2ooxml.common.style.text import (
    default_text_style as _default_text_style,
)
from svg2ooxml.common.units.scalars import PX_PER_INCH

if TYPE_CHECKING:
    from svg2ooxml.core.parser.units import UnitConverter

_DEFAULT_UNITLESS_FONT_SCALE = float(
    os.getenv("SVG2OOXML_UNITLESS_FONT_SCALE", str(72.0 / PX_PER_INCH))
)


class StyleResolver:
    """Resolve SVG style attributes and inline CSS using tinycss2."""

    _TEXT_DEFAULTS: dict[str, Any] = TEXT_DEFAULTS
    _TEXT_ATTRIBUTE_MAP: dict[str, PropertyDescriptor] = TEXT_ATTRIBUTE_MAP

    def __init__(
        self,
        unit_converter: UnitConverter | None = None,
        *,
        unitless_font_size_scale: float | None = None,
    ) -> None:
        if unit_converter is None:
            from svg2ooxml.core.parser.units import UnitConverter

            unit_converter = UnitConverter()
        self._unit_converter = unit_converter
        self._unitless_font_size_scale = (
            float(unitless_font_size_scale)
            if unitless_font_size_scale is not None
            else _DEFAULT_UNITLESS_FONT_SCALE
        )
        self._cascade = StylesheetCascade(self._unit_converter)

    # ------------------------------------------------------------------ #
    # Text styling                                                       #
    # ------------------------------------------------------------------ #

    def default_text_style(self) -> dict[str, Any]:
        return _default_text_style()

    def compute_text_style(
        self,
        element,
        context: StyleContext | None = None,
        parent_style: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _compute_text_style(
            element,
            context=context,
            parent_style=parent_style,
            stylesheet_declarations=self._collect_css_declarations(element),
            unitless_font_size_scale=self._unitless_font_size_scale,
        )

    # ------------------------------------------------------------------ #
    # Presentation styling                                               #
    # ------------------------------------------------------------------ #

    def compute_paint_style(
        self,
        element,
        context: StyleContext | None = None,
        parent_style: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _compute_paint_style(
            element,
            context=context,
            parent_style=parent_style,
            stylesheet_declarations=self._collect_css_declarations(element),
            unit_converter=self._unit_converter,
        )

    # ------------------------------------------------------------------ #
    # Stylesheet helpers                                                 #
    # ------------------------------------------------------------------ #

    def collect_css(
        self,
        root: etree._Element,
        *,
        viewport_width: float | None = None,
        viewport_height: float | None = None,
    ) -> None:
        """Parse <style> elements so selectors can be applied during styling."""

        self._cascade.collect(
            root,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )

    def _collect_css_declarations(self, element: etree._Element) -> list[CSSDeclaration]:
        return self._cascade.declarations_for(element)

    def apply_stylesheet_paints(
        self,
        element: etree._Element,
        *,
        apply_color,
        apply_fill,
        apply_stroke,
        style: dict[str, Any],
        context: StyleContext | None,
        importance_map: dict[str, bool] | None = None,
        origin_map: dict[str, CSSOrigin] | None = None,
    ) -> tuple[dict[str, bool], dict[str, CSSOrigin]]:
        """Apply styles defined in <style> elements respecting CSS cascade.

        The declarations are already sorted by _collect_css_declarations() in
        cascade order, so we apply them all and let later ones override earlier ones.
        """

        return _apply_stylesheet_paints(
            self._collect_css_declarations(element),
            apply_color=apply_color,
            apply_fill=apply_fill,
            apply_stroke=apply_stroke,
            style=style,
            context=context,
            unit_converter=self._unit_converter,
            importance_map=importance_map,
            origin_map=origin_map,
        )

    def apply_stylesheet_text(
        self,
        element: etree._Element,
        *,
        style: dict[str, Any],
        context: StyleContext | None,
        importance_map: dict[str, bool] | None = None,
        origin_map: dict[str, CSSOrigin] | None = None,
    ) -> tuple[dict[str, bool], dict[str, CSSOrigin]]:
        """Apply text-related stylesheet declarations to ``style``.

        The declarations are already sorted by _collect_css_declarations() in
        cascade order, so we apply them all and let later ones override earlier ones.
        """

        return _apply_stylesheet_text(
            self._collect_css_declarations(element),
            style=style,
            context=context,
            importance_map=importance_map,
            origin_map=origin_map,
            unitless_font_size_scale=self._unitless_font_size_scale,
        )

__all__ = [
    "CSSDeclaration",
    "CSSOrigin",
    "CSSRule",
    "CompiledSelector",
    "PropertyDescriptor",
    "SelectorPart",
    "StyleContext",
    "StyleResolver",
]
