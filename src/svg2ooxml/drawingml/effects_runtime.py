"""DrawingML effect serialization helpers."""

from __future__ import annotations

from collections.abc import Iterable

from svg2ooxml.drawingml.effect_fragments import (
    merge_effect_lists,
    sanitize_custom_effect_fragment,
)
from svg2ooxml.drawingml.xml_builder import (
    blur,
    effect_list,
    glow,
    outer_shadow,
    reflection,
    soft_edge,
    srgb_color,
    to_string,
)
from svg2ooxml.filters.utils.dml import is_effect_dag, merge_effect_fragments
from svg2ooxml.ir.effects import (
    BlurEffect,
    CustomEffect,
    Effect,
    GlowEffect,
    ReflectionEffect,
    ShadowEffect,
    SoftEdgeEffect,
)


def effect_block(effects: Iterable[Effect]) -> str:
    effect_strings: list[str] = []
    for effect in effects or []:
        xml = effect_to_drawingml(effect)
        if xml:
            effect_strings.append(xml.strip())

    if not effect_strings:
        return ""

    # Preserve alpha/composite graphs via effectDag when present.
    if any(is_effect_dag(fragment) for fragment in effect_strings):
        merged = merge_effect_fragments(*effect_strings, prefer_container="effectDag")
        if merged:
            return _format_block(merged, "        ")
        return ""

    # Single effect without effectLst wrapper — return as-is.
    if len(effect_strings) == 1 and "<a:effectLst" not in effect_strings[0]:
        return _format_block(effect_strings[0], "        ")

    # Merge all effectLst content into one, dedup, filter, and reorder.
    merged = merge_effect_lists("".join(effect_strings))
    if not merged:
        return ""
    return _format_block(merged, "        ")


def effect_to_drawingml(effect: Effect) -> str:
    """Convert effect to DrawingML XML using safe lxml builders."""
    if isinstance(effect, CustomEffect):
        return sanitize_custom_effect_fragment(effect.drawingml)

    if isinstance(effect, BlurEffect):
        return to_string(effect_list(blur(effect.to_emu())))

    if isinstance(effect, SoftEdgeEffect):
        return to_string(effect_list(soft_edge(effect.to_emu())))

    if isinstance(effect, GlowEffect):
        color = (effect.color or "FFFFFF").upper()
        color_elem = srgb_color(color)
        return to_string(effect_list(glow(effect.to_emu(), color_elem)))

    if isinstance(effect, ShadowEffect):
        blur_rad, dist = effect.to_emu()
        direction = effect.to_direction_emu()
        alpha = effect.to_alpha_val()
        color = (effect.color or "000000").upper()
        color_elem = srgb_color(color, alpha=alpha)
        shadow = outer_shadow(
            blur_rad, dist, direction, color_elem, algn="ctr", rotWithShape="0"
        )
        return to_string(effect_list(shadow))

    if isinstance(effect, ReflectionEffect):
        blur_rad, dist = effect.to_emu()
        start_alpha, end_alpha = effect.to_alpha_vals()
        return to_string(effect_list(reflection(blur_rad, dist, start_alpha, end_alpha)))

    return ""


def _format_block(xml: str, indent: str) -> str:
    if not xml:
        return ""
    lines = xml.splitlines()
    return "\n".join(indent + line for line in lines) + "\n"


__all__ = ["effect_block", "effect_to_drawingml"]
