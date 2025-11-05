"""CSS style resolver with tinycss2-backed parsing."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Any

from lxml import etree

import tinycss2

if TYPE_CHECKING:
    from svg2ooxml.core.parser import ConversionContext, UnitConverter

PropertyHandler = Callable[[str], object]

_DEFAULT_FONT_SIZE_PT = 12.0
_DEFAULT_FILL = "#000000"


class CSSOrigin(IntEnum):
    """CSS cascade origin levels per CSS Cascade 4 spec.

    Higher values win in normal (non-!important) cascade.
    For !important declarations, the order is reversed.

    Note: PRESENTATION_ATTR and INLINE are both part of the author origin,
    but we track them separately to apply correct specificity and ordering.
    """
    USER_AGENT = 1      # Browser/UA default styles
    AUTHOR = 2          # Stylesheet rules
    PRESENTATION_ATTR = 3  # SVG presentation attributes (author origin, specificity 0)
    INLINE = 4          # Inline style="" attributes (author origin, highest specificity)


def _strip_quotes(value: str) -> str:
    return value.strip('"\'' )


def _normalize_font_weight(value: str) -> str:
    token = value.strip().lower()
    mapping = {
        "100": "lighter",
        "200": "lighter",
        "300": "light",
        "400": "normal",
        "500": "normal",
        "600": "semibold",
        "700": "bold",
        "800": "bolder",
        "900": "bolder",
    }
    return mapping.get(token, token)


def _parse_font_size_token(value: str, base_pt: float) -> float:
    token = value.strip().lower()
    try:
        if token.endswith("px"):
            return float(token[:-2]) * 0.75
        if token.endswith("pt"):
            return float(token[:-2])
        if token.endswith("em"):
            return float(token[:-2]) * base_pt
        if token.endswith("%"):
            return base_pt * float(token[:-1]) / 100.0
        return float(token)
    except ValueError:
        return base_pt


def _hex_to_rgba(color: str) -> tuple[float, float, float, float]:
    token = color.lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    if len(token) != 6:
        return (0.0, 0.0, 0.0, 1.0)
    r = int(token[0:2], 16) / 255.0
    g = int(token[2:4], 16) / 255.0
    b = int(token[4:6], 16) / 255.0
    return (r, g, b, 1.0)


def _rgba_to_hex(value: tuple[float, float, float, float]) -> str:
    r, g, b, _ = value
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, int(round(r * 255)))),
        max(0, min(255, int(round(g * 255)))),
        max(0, min(255, int(round(b * 255)))),
    )


@dataclass(frozen=True)
class PropertyDescriptor:
    """Maps CSS property names to resolver keys and parsers."""

    key: str
    parser: PropertyHandler


@dataclass(frozen=True)
class StyleContext:
    """Viewport-aware context for CSS evaluation."""

    conversion: ConversionContext
    viewport_width: float
    viewport_height: float


@dataclass(frozen=True)
class SelectorPart:
    """Single selector component with optional combinator to the left."""

    tag: str | None
    element_id: str | None
    classes: tuple[str, ...]
    combinator: str | None  # 'descendant', 'child', or None


@dataclass(frozen=True)
class CompiledSelector:
    """Selector compiled into reversed parts for fast matching."""

    parts: tuple[SelectorPart, ...]
    specificity: tuple[int, int, int]

    def matches(self, element: etree._Element) -> bool:
        return _matches_selector(self.parts, element)


@dataclass(frozen=True)
class CSSDeclaration:
    """Single CSS declaration."""

    name: str
    value: str
    important: bool
    origin: CSSOrigin = CSSOrigin.AUTHOR


@dataclass(frozen=True)
class CSSRule:
    """Qualified CSS rule with associated selectors."""

    selectors: tuple[CompiledSelector, ...]
    declarations: tuple[CSSDeclaration, ...]
    order: int
    origin: CSSOrigin = CSSOrigin.AUTHOR


class StyleResolver:
    """Resolve SVG style attributes and inline CSS using tinycss2."""

    _TEXT_DEFAULTS: dict[str, Any] = {
        "font_family": "Arial",
        "font_size_pt": _DEFAULT_FONT_SIZE_PT,
        "font_weight": "normal",
        "font_style": "normal",
        "text_decoration": "none",
        "fill": _DEFAULT_FILL,
    }

    _TEXT_ATTRIBUTE_MAP: dict[str, PropertyDescriptor] = {
        "font-family": PropertyDescriptor("font_family", _strip_quotes),
        "font-size": PropertyDescriptor("font_size_pt", str.strip),
        "font-weight": PropertyDescriptor("font_weight", _normalize_font_weight),
        "font-style": PropertyDescriptor("font_style", str.strip),
        "text-decoration": PropertyDescriptor("text_decoration", str.strip),
        "fill": PropertyDescriptor("fill", str.strip),
    }

    _TEXT_CSS_MAP = _TEXT_ATTRIBUTE_MAP

    def __init__(self, unit_converter: UnitConverter | None = None) -> None:
        if unit_converter is None:
            from svg2ooxml.core.parser import UnitConverter

            unit_converter = UnitConverter()
        self._unit_converter = unit_converter
        self._css_rules: list[CSSRule] = []

    # ------------------------------------------------------------------ #
    # Text styling                                                       #
    # ------------------------------------------------------------------ #

    def default_text_style(self) -> dict[str, Any]:
        return dict(self._TEXT_DEFAULTS)

    def compute_text_style(
        self,
        element,
        context: StyleContext | None = None,
        parent_style: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        style = dict(parent_style) if parent_style else self.default_text_style()
        importance: dict[str, bool] = {}
        origin_level: dict[str, CSSOrigin] = {}
        skip_stylesheet = element.get("data-svg2ooxml-use-clone") == "true"

        # Presentation attributes (author origin, specificity 0)
        for attr, descriptor in self._TEXT_ATTRIBUTE_MAP.items():
            raw = element.get(attr)
            if raw is None:
                continue
            self._apply_text_property(style, descriptor, raw, context)
            importance[attr] = False
            origin_level[attr] = CSSOrigin.PRESENTATION_ATTR

        # Stylesheet rules (author origin, with specificity)
        if not skip_stylesheet:
            importance, origin_level = self.apply_stylesheet_text(
                element,
                style=style,
                context=context,
                importance_map=importance,
                origin_map=origin_level,
            )

        # Inline styles (author origin, highest precedence)
        inline = element.get("style")
        if inline:
            for name, value, _important in self._parse_inline_declarations(inline):
                descriptor = self._TEXT_CSS_MAP.get(name)
                if descriptor and value is not None:
                    prev_important = importance.get(name, False)

                    # Skip only if previous declaration was !important and this one is not
                    # (Within inline styles, !important always wins over non-!important)
                    if prev_important and not _important:
                        continue
                    # For same importance level: inline styles (INLINE origin) always override
                    # earlier origins due to cascade rules. Within the same inline style attribute,
                    # source order applies (later wins), so we always apply.

                    self._apply_text_property(style, descriptor, value, context)
                    importance[name] = _important
                    origin_level[name] = CSSOrigin.INLINE

        return style

    # ------------------------------------------------------------------ #
    # Presentation styling                                               #
    # ------------------------------------------------------------------ #

    def compute_paint_style(
        self,
        element,
        context: StyleContext | None = None,
        parent_style: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        style = dict(parent_style) if parent_style else {
            "fill": _DEFAULT_FILL,
            "fill_opacity": 1.0,
            "stroke": None,
            "stroke_opacity": 1.0,
            "stroke_width_px": 1.0,
            "opacity": 1.0,
        }
        importance: dict[str, bool] = {}
        origin_level: dict[str, CSSOrigin] = {}
        skip_stylesheet = element.get("data-svg2ooxml-use-clone") == "true"

        def current_fill() -> str:
            fill = style.get("fill")
            if isinstance(fill, str):
                return fill
            return _DEFAULT_FILL

        def apply_fill(value: str | None, importance_flag: bool = False, origin: CSSOrigin = CSSOrigin.AUTHOR) -> None:
            if value is None:
                return
            token = value.strip()
            if not token:
                return
            if token.lower() == "none":
                style["fill"] = None
                importance["fill"] = importance_flag
                origin_level["fill"] = origin
                return
            if token.startswith("url("):
                style["fill"] = token
                importance["fill"] = importance_flag
                origin_level["fill"] = origin
                return
            style["fill"] = self._resolve_color(token, current_fill())
            importance["fill"] = importance_flag
            origin_level["fill"] = origin

        def apply_stroke(value: str | None, importance_flag: bool = False, origin: CSSOrigin = CSSOrigin.AUTHOR) -> None:
            if value is None:
                return
            token = value.strip()
            if not token:
                return
            if token.lower() == "none":
                style["stroke"] = None
                importance["stroke"] = importance_flag
                origin_level["stroke"] = origin
                return
            if token.startswith("url("):
                style["stroke"] = token
                importance["stroke"] = importance_flag
                origin_level["stroke"] = origin
                return
            style["stroke"] = self._resolve_color(token, style.get("stroke") or _DEFAULT_FILL)
            importance["stroke"] = importance_flag
            origin_level["stroke"] = origin

        # Presentation attributes (author origin, specificity 0)
        apply_fill(element.get("fill"), False, CSSOrigin.PRESENTATION_ATTR)
        apply_stroke(element.get("stroke"), False, CSSOrigin.PRESENTATION_ATTR)

        fill_opacity = element.get("fill-opacity")
        if fill_opacity is not None:
            style["fill_opacity"] = self._parse_float(fill_opacity, default=style.get("fill_opacity", 1.0))
            importance["fill-opacity"] = False
            origin_level["fill-opacity"] = CSSOrigin.PRESENTATION_ATTR

        stroke_opacity = element.get("stroke-opacity")
        if stroke_opacity is not None:
            style["stroke_opacity"] = self._parse_float(stroke_opacity, default=style.get("stroke_opacity", 1.0))
            importance["stroke-opacity"] = False
            origin_level["stroke-opacity"] = CSSOrigin.PRESENTATION_ATTR

        stroke_width = element.get("stroke-width")
        if stroke_width is not None:
            style["stroke_width_px"] = self._length_to_px(stroke_width, context, axis="x")
            importance["stroke-width"] = False
            origin_level["stroke-width"] = CSSOrigin.PRESENTATION_ATTR

        opacity = element.get("opacity")
        if opacity is not None:
            style["opacity"] = self._parse_float(opacity, default=style.get("opacity", 1.0))
            importance["opacity"] = False
            origin_level["opacity"] = CSSOrigin.PRESENTATION_ATTR

        # Stylesheet rules (author origin, with specificity)
        if not skip_stylesheet:
            importance, origin_level = self.apply_stylesheet_paints(
                element,
                apply_fill=apply_fill,
                apply_stroke=apply_stroke,
                style=style,
                context=context,
                importance_map=importance,
                origin_map=origin_level,
            )

        # Inline styles (author origin, highest precedence)
        inline = element.get("style")
        if inline:
            for name, value, _important in self._parse_inline_declarations(inline):
                prev_important = importance.get(name, False)

                # Skip only if previous declaration was !important and this one is not
                # (Within inline styles, !important always wins over non-!important)
                if prev_important and not _important:
                    continue
                # For same importance level: inline styles (INLINE origin) always override
                # earlier origins due to cascade rules. Within the same inline style attribute,
                # source order applies (later wins), so we always apply.

                if name == "fill":
                    apply_fill(value, _important, CSSOrigin.INLINE)
                elif name == "fill-opacity":
                    style["fill_opacity"] = self._parse_float(value, default=style.get("fill_opacity", 1.0))
                    importance["fill-opacity"] = _important
                    origin_level["fill-opacity"] = CSSOrigin.INLINE
                elif name == "stroke":
                    apply_stroke(value, _important, CSSOrigin.INLINE)
                elif name == "stroke-opacity":
                    style["stroke_opacity"] = self._parse_float(value, default=style.get("stroke_opacity", 1.0))
                    importance["stroke-opacity"] = _important
                    origin_level["stroke-opacity"] = CSSOrigin.INLINE
                elif name == "stroke-width":
                    style["stroke_width_px"] = self._length_to_px(value, context, axis="x")
                    importance["stroke-width"] = _important
                    origin_level["stroke-width"] = CSSOrigin.INLINE
                elif name == "opacity":
                    style["opacity"] = self._parse_float(value, default=style.get("opacity", 1.0))
                    importance["opacity"] = _important
                    origin_level["opacity"] = CSSOrigin.INLINE

        return style

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _parse_inline_declarations(
        self,
        style_str: str,
    ) -> Iterable[tuple[str, str, bool]]:
        if not style_str:
            return []
        try:
            declarations = tinycss2.parse_declaration_list(
                style_str,
                skip_whitespace=True,
                skip_comments=True,
            )
        except Exception:
            return []

        resolved: list[tuple[str, str, bool]] = []
        for decl in declarations:
            if decl.type != "declaration":
                continue
            name = decl.name.lower()
            value = tinycss2.serialize(decl.value).strip()
            resolved.append((name, value, bool(decl.important)))
        return resolved

    def _apply_text_property(
        self,
        style: dict[str, Any],
        descriptor: PropertyDescriptor,
        raw_value: str,
        context: StyleContext | None,
    ) -> None:
        try:
            value = descriptor.parser(raw_value)
        except Exception:  # pragma: no cover - defensive fallback
            return

        if descriptor.key == "font_size_pt":
            base = float(style.get("font_size_pt", _DEFAULT_FONT_SIZE_PT))
            style["font_size_pt"] = _parse_font_size_token(value, base)
        elif descriptor.key == "fill":
            current = style.get("fill", _DEFAULT_FILL)
            style["fill"] = self._resolve_color(value, current if isinstance(current, str) else _DEFAULT_FILL)
        else:
            style[descriptor.key] = value

    def _resolve_color(self, token: str, current_hex: str) -> str:
        stripped = token.strip()
        if not stripped:
            return current_hex
        if stripped.lower() == "none":
            return current_hex
        if stripped.startswith("url("):
            return stripped
        from svg2ooxml.core.parser import parse_color

        rgba = parse_color(stripped, current_color=_hex_to_rgba(current_hex))
        if rgba is None:
            return current_hex
        return _rgba_to_hex(rgba)

    def _length_to_px(
        self,
        value: str | None,
        context: StyleContext | None,
        axis: str = "x",
    ) -> float:
        if value is None:
            return 0.0
        token = value.strip()
        if not token:
            return 0.0

        try:
            return float(token)
        except ValueError:
            pass

        if context is not None:
            if token.endswith("%"):
                try:
                    pct = float(token[:-1])
                except ValueError:
                    pct = 0.0
                basis = context.viewport_width if axis == "x" else context.viewport_height
                return basis * (pct / 100.0) if basis is not None else 0.0
            if token.endswith("em"):
                try:
                    return float(token[:-2]) * context.conversion.font_size
                except ValueError:
                    return context.conversion.font_size

        try:
            return self._unit_converter.to_px(token)
        except Exception:
            return 0.0

    @staticmethod
    def _parse_float(value: str | None, default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------------ #
    # Stylesheet helpers                                                 #
    # ------------------------------------------------------------------ #

    def collect_css(self, root: etree._Element) -> None:
        """Parse <style> elements so selectors can be applied during styling."""

        self._css_rules = []
        if root is None:
            return

        style_elements = root.findall(".//{http://www.w3.org/2000/svg}style")
        order = 0
        for style in style_elements:
            text = style.text or ""
            if not text.strip():
                continue
            try:
                stylesheet = tinycss2.parse_stylesheet(
                    text,
                    skip_whitespace=True,
                    skip_comments=True,
                )
            except Exception:
                continue
            for rule in stylesheet:
                if rule.type != "qualified-rule":
                    continue
                selector_text = tinycss2.serialize(rule.prelude).strip()
                if not selector_text:
                    continue
                declarations = self._parse_rule_declarations(rule)
                if not declarations:
                    continue
                selectors = self._compile_selectors(selector_text)
                if not selectors:
                    continue
                css_rule = CSSRule(
                    selectors=tuple(selectors),
                    declarations=tuple(declarations),
                    order=order,
                )
                self._css_rules.append(css_rule)
                order += 1

    def _parse_rule_declarations(self, rule) -> list[CSSDeclaration]:
        try:
            declarations = tinycss2.parse_declaration_list(
                rule.content,
                skip_whitespace=True,
                skip_comments=True,
            )
        except Exception:
            return []

        resolved: list[CSSDeclaration] = []
        for decl in declarations:
            if decl.type != "declaration":
                continue
            name = decl.name.lower()
            value = tinycss2.serialize(decl.value).strip()
            if not name or not value:
                continue
            resolved.append(CSSDeclaration(name=name, value=value, important=bool(decl.important)))
        return resolved

    def _compile_selectors(self, selector_text: str) -> list[CompiledSelector]:
        selectors: list[CompiledSelector] = []
        for chunk in selector_text.split(","):
            parsed = _parse_selector(chunk.strip())
            if not parsed:
                continue
            parts_rev = tuple(reversed(parsed))
            specificity = _compute_specificity(parsed)
            selectors.append(
                CompiledSelector(
                    parts=parts_rev,
                    specificity=specificity,
                )
            )
        return selectors

    def _collect_css_declarations(self, element: etree._Element) -> list[CSSDeclaration]:
        if not self._css_rules:
            return []

        matches: list[tuple[CSSDeclaration, tuple[int, int, int], int, int, CSSOrigin]] = []
        for rule in self._css_rules:
            for selector in rule.selectors:
                if not selector.matches(element):
                    continue
                for index, declaration in enumerate(rule.declarations):
                    matches.append((declaration, selector.specificity, rule.order, index, rule.origin))

        if not matches:
            return []

        def cascade_precedence(origin: CSSOrigin, important: bool) -> int:
            """Calculate cascade precedence per CSS Cascade 4 spec."""

            if important:
                priority_map = {
                    CSSOrigin.USER_AGENT: 0,
                    CSSOrigin.PRESENTATION_ATTR: 1,
                    CSSOrigin.AUTHOR: 2,
                    CSSOrigin.INLINE: 3,
                }
            else:
                priority_map = {
                    CSSOrigin.USER_AGENT: 0,
                    CSSOrigin.PRESENTATION_ATTR: 1,
                    CSSOrigin.AUTHOR: 2,
                    CSSOrigin.INLINE: 3,
                }
            return priority_map.get(origin, 0)

        matches.sort(
            key=lambda item: (
                cascade_precedence(item[4], item[0].important),  # Origin + importance
                item[1],  # Specificity (ids, classes, tags)
                item[2],  # Rule order (source order)
                item[3],  # Declaration index
            )
        )
        return [item[0] for item in matches]

    def apply_stylesheet_paints(
        self,
        element: etree._Element,
        *,
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

        applied_importance = importance_map if importance_map is not None else {}
        applied_origin = origin_map if origin_map is not None else {}

        for decl in self._collect_css_declarations(element):
            name = decl.name
            value = decl.value

            if name == "fill":
                apply_fill(value, decl.important, decl.origin)
            elif name == "fill-opacity":
                style["fill_opacity"] = self._parse_float(value, default=style.get("fill_opacity", 1.0))
                applied_importance["fill-opacity"] = decl.important
                applied_origin["fill-opacity"] = decl.origin
            elif name == "stroke":
                apply_stroke(value, decl.important, decl.origin)
            elif name == "stroke-opacity":
                style["stroke_opacity"] = self._parse_float(value, default=style.get("stroke_opacity", 1.0))
                applied_importance["stroke-opacity"] = decl.important
                applied_origin["stroke-opacity"] = decl.origin
            elif name == "stroke-width":
                style["stroke_width_px"] = self._length_to_px(value, context, axis="x")
                applied_importance["stroke-width"] = decl.important
                applied_origin["stroke-width"] = decl.origin
            elif name == "opacity":
                style["opacity"] = self._parse_float(value, default=style.get("opacity", 1.0))
                applied_importance["opacity"] = decl.important
                applied_origin["opacity"] = decl.origin

        return applied_importance, applied_origin

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

        applied_importance = importance_map if importance_map is not None else {}
        applied_origin = origin_map if origin_map is not None else {}

        for decl in self._collect_css_declarations(element):
            descriptor = self._TEXT_CSS_MAP.get(decl.name)
            if descriptor is None:
                continue

            self._apply_text_property(style, descriptor, decl.value, context)
            applied_importance[decl.name] = decl.important
            applied_origin[decl.name] = decl.origin

        return applied_importance, applied_origin


def _parse_selector(selector: str) -> list[SelectorPart]:
    """Parse a limited subset of CSS selectors (type, class, id, descendant, child)."""

    parts: list[SelectorPart] = []
    length = len(selector)
    i = 0
    pending_combinator: str | None = None

    while i < length:
        # Skip whitespace
        while i < length and selector[i].isspace():
            i += 1
            pending_combinator = pending_combinator or ("descendant" if parts else None)

        if i >= length:
            break

        if selector[i] == ">":
            pending_combinator = "child"
            i += 1
            continue

        start = i
        tag = None
        while i < length and (selector[i].isalnum() or selector[i] in {"-", "_"}):
            i += 1
        if i > start:
            tag = selector[start:i]

        classes: list[str] = []
        element_id: str | None = None
        while i < length:
            if selector[i] == ".":
                i += 1
                start = i
                while i < length and (selector[i].isalnum() or selector[i] in {"-", "_"}):
                    i += 1
                if start < i:
                    classes.append(selector[start:i])
            elif selector[i] == "#":
                i += 1
                start = i
                while i < length and (selector[i].isalnum() or selector[i] in {"-", "_"}):
                    i += 1
                if start < i:
                    element_id = selector[start:i]
            else:
                break

        if tag is None and not classes and element_id is None:
            # Unsupported selector component – abort parsing this selector.
            return []

        parts.append(
            SelectorPart(
                tag=tag,
                element_id=element_id,
                classes=tuple(classes),
                combinator=pending_combinator,
            )
        )
        pending_combinator = None

    if parts:
        parts[0] = SelectorPart(
            tag=parts[0].tag,
            element_id=parts[0].element_id,
            classes=parts[0].classes,
            combinator=None,
        )
    return parts


def _compute_specificity(parts: Iterable[SelectorPart]) -> tuple[int, int, int]:
    ids = 0
    classes = 0
    tags = 0
    for part in parts:
        if part.element_id:
            ids += 1
        if part.classes:
            classes += len(part.classes)
        if part.tag:
            tags += 1
    return (ids, classes, tags)


def _matches_selector(parts: tuple[SelectorPart, ...], element: etree._Element) -> bool:
    def match_part(index: int, node: etree._Element) -> bool:
        part = parts[index]
        if not _matches_simple_selector(part, node):
            return False
        if index == len(parts) - 1:
            return True

        combinator = part.combinator
        if combinator == "child":
            parent = node.getparent()
            if parent is None:
                return False
            return match_part(index + 1, parent)
        if combinator == "descendant":
            parent = node.getparent()
            while parent is not None:
                if match_part(index + 1, parent):
                    return True
                parent = parent.getparent()
            return False
        return match_part(index + 1, node)

    if not parts:
        return False
    return match_part(0, element)


def _matches_simple_selector(part: SelectorPart, element: etree._Element) -> bool:
    if part.tag:
        local_name = element.tag.split("}")[-1]
        if local_name != part.tag:
            return False

    if part.element_id:
        if element.get("id") != part.element_id:
            return False

    if part.classes:
        class_attr = element.get("class")
        if not class_attr:
            return False
        classes = class_attr.split()
        for token in part.classes:
            if token not in classes:
                return False
    return True


__all__ = ["StyleContext", "StyleResolver"]
