"""Private text layout complexity predicates."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from svg2ooxml.common.conversions.transforms import parse_strict_numeric_list
from svg2ooxml.common.geometry.transforms.decompose import classify_linear_transform
from svg2ooxml.core.resvg.text.layout_complexity import TextLayoutComplexity

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.usvg_tree import TextNode


class TextLayoutChecksMixin:
    """Predicate helpers used by ``TextLayoutAnalyzer``."""

    def _has_text_path(self, node: TextNode) -> bool:
        for child in getattr(node, "children", []):
            if hasattr(child, "tag") and child.tag and "textPath" in child.tag:
                return True

        attrs = getattr(node, "attributes", {}) or {}
        return "textPath" in attrs or "href" in attrs

    def _has_vertical_text(self, node: TextNode) -> bool:
        attrs = getattr(node, "attributes", {}) or {}
        writing_mode = attrs.get("writing-mode", "").lower()
        if writing_mode in ("tb", "tb-rl", "vertical-rl", "vertical-lr"):
            return True

        text_orientation = attrs.get("text-orientation", "").lower()
        if "upright" in text_orientation or "sideways" in text_orientation:
            return True

        return "glyph-orientation-vertical" in attrs

    def _has_complex_transform(self, node: TextNode) -> bool:
        transform = getattr(node, "transform", None)
        if transform is None:
            return False

        a = getattr(transform, "a", 1.0)
        b = getattr(transform, "b", 0.0)
        c = getattr(transform, "c", 0.0)
        d = getattr(transform, "d", 1.0)

        if abs(a - 1.0) < 1e-6 and abs(b) < 1e-6 and abs(c) < 1e-6 and abs(d - 1.0) < 1e-6:
            return False

        rotation_rad = math.atan2(b, a)
        rotation_deg = abs(math.degrees(rotation_rad))
        if rotation_deg > self.max_rotation_deg:
            return True

        classification = classify_linear_transform(a, b, c, d)
        if classification.ratio > self.max_scale_ratio:
            return True
        if classification.has_shear and classification.shear_degrees > self.max_skew_deg:
            return True

        return False

    def _has_complex_positioning(self, node: TextNode) -> bool:
        attrs = getattr(node, "attributes", {}) or {}
        rotate_attr = attrs.get("rotate", "").strip()
        if rotate_attr:
            try:
                vals = parse_strict_numeric_list(rotate_attr, allow_calc=True)
                if not vals:
                    return True
                if len(set(vals)) > 1:
                    return True
            except ValueError:
                return True

        x_count = _position_value_count(attrs.get("x", ""))
        y_count = _position_value_count(attrs.get("y", ""))
        if x_count > 1 or y_count > 1:
            return True

        dx_count = _position_value_count(attrs.get("dx", ""))
        dy_count = _position_value_count(attrs.get("dy", ""))
        if dx_count > 1 or dy_count > 1:
            return True

        return self._has_spacing_adjustments(node)

    def _check_child_spans(self, node: TextNode) -> tuple[bool, str]:
        for child in getattr(node, "children", []):
            child_tag = getattr(child, "tag", "")
            if not child_tag or not any(tag in child_tag.lower() for tag in ["tspan", "text"]):
                continue

            if self._has_vertical_text(child):
                return (True, TextLayoutComplexity.HAS_CHILD_SPAN_VERTICAL_TEXT)
            if self._has_complex_transform(child):
                return (True, TextLayoutComplexity.HAS_COMPLEX_TRANSFORM)
            if self._has_complex_positioning(child):
                return (True, TextLayoutComplexity.HAS_CHILD_SPAN_COMPLEX_POSITIONING)
            if self._has_kerning(child):
                return (True, TextLayoutComplexity.HAS_KERNING)
            if self._has_ligatures(child):
                return (True, TextLayoutComplexity.HAS_LIGATURES)
            if self._has_glyph_reuse(child):
                return (True, TextLayoutComplexity.HAS_GLYPH_REUSE)

            has_complex, reason = self._check_child_spans(child)
            if has_complex:
                return (True, reason)

        return (False, "")

    def _style_value(self, node: TextNode, name: str) -> str | None:
        attrs = getattr(node, "attributes", {}) or {}
        styles = getattr(node, "styles", {}) or {}
        return styles.get(name) or attrs.get(name)

    def _has_kerning(self, node: TextNode) -> bool:
        kerning = self._style_value(node, "font-kerning") or self._style_value(node, "kerning")
        if kerning and kerning.strip().lower() not in {"auto", "normal"}:
            return True
        return self._font_feature_enabled(node, {"kern"})

    def _has_ligatures(self, node: TextNode) -> bool:
        ligatures = self._style_value(node, "font-variant-ligatures")
        if ligatures and ligatures.strip().lower() not in {"normal", "none"}:
            return True
        return self._font_feature_enabled(node, {"liga", "clig", "dlig", "hlig"})

    def _has_glyph_reuse(self, node: TextNode) -> bool:
        features = self._style_value(node, "font-feature-settings")
        return bool(features and features.strip().lower() != "normal")

    def _font_feature_enabled(self, node: TextNode, tokens: set[str]) -> bool:
        value = self._style_value(node, "font-feature-settings")
        if not value:
            return False
        raw = value.lower()
        if raw.strip() == "normal":
            return False
        return any(token in raw for token in tokens)

    def _has_spacing_adjustments(self, node: TextNode) -> bool:
        word_spacing = self._style_value(node, "word-spacing")
        if word_spacing and word_spacing.strip().lower() not in {"normal", "0", "0px", "0%"}:
            return True
        text_length = self._style_value(node, "textLength")
        if text_length and text_length.strip():
            return True
        length_adjust = self._style_value(node, "lengthAdjust")
        if length_adjust and length_adjust.strip():
            return True
        return False


def _position_value_count(value: str) -> int:
    return len(value.split()) if value else 0


__all__ = ["TextLayoutChecksMixin"]
