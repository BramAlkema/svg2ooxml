"""Font metrics, scaling, fallback resolution, and run creation helpers.

Extracted from ``core.ir.text_converter`` — pure move, no behavior changes.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from svg2ooxml.color.utils import rgb_object_to_hex
from svg2ooxml.ir.text import Run
from svg2ooxml.policy.text_policy import TextPolicyDecision

# ---------------------------------------------------------------
# Font fallback table
# ---------------------------------------------------------------

FONT_FALLBACKS: dict[str, str] = {
    "sans-serif": "Arial",
    "serif": "Times New Roman",
    "monospace": "Courier New",
    "cursive": "Comic Sans MS",
    "fantasy": "Impact",
    "svgfreesansascii": "Arial",
}

# ---------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------


def coerce_hex_color(token: str) -> str:
    value = (token or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return "000000"
    try:
        int(value, 16)
    except ValueError:
        return "000000"
    return value.upper()


def resvg_color_to_hex(color: Any) -> str:
    return rgb_object_to_hex(color, scale="unit") or "000000"


# ---------------------------------------------------------------
# Font family normalisation
# ---------------------------------------------------------------


def font_fallback(family: str | None) -> str | None:
    if not family:
        return None
    key = family.strip().lower()
    return FONT_FALLBACKS.get(key)


def normalize_font_family(family: str | None) -> str | None:
    if family is None:
        return None
    token = family.strip()
    if not token:
        return None
    mapped = FONT_FALLBACKS.get(token.lower())
    return mapped or token


def normalize_font_family_list(family: str | None) -> str:
    if not family:
        return "Arial"
    tokens = [
        part.strip().strip("\"'")
        for part in family.split(",")
        if part.strip().strip("\"'")
    ]
    if not tokens:
        return "Arial"
    primary = tokens[0]
    normalized = normalize_font_family(primary)
    return normalized or primary


# ---------------------------------------------------------------
# Run metrics scaling / compatibility
# ---------------------------------------------------------------


def scale_run_metrics(run: Run, scale: float) -> Run:
    if not math.isfinite(scale) or scale <= 0.0 or abs(scale - 1.0) <= 1e-6:
        return run

    def _scaled(value: float | None) -> float | None:
        if value is None:
            return None
        return float(value) * scale

    return replace(
        run,
        font_size_pt=max(run.font_size_pt * scale, 0.01),
        stroke_width_px=_scaled(run.stroke_width_px),
        kerning=_scaled(run.kerning),
        letter_spacing=_scaled(run.letter_spacing),
        word_spacing=_scaled(run.word_spacing),
    )


def runs_compatible(first: Run, second: Run) -> bool:
    return (
        first.font_family == second.font_family
        and abs(first.font_size_pt - second.font_size_pt) <= 1e-6
        and first.bold == second.bold
        and first.italic == second.italic
        and first.underline == second.underline
        and first.strike == second.strike
        and first.rgb == second.rgb
        and first.theme_color == second.theme_color
        and abs(first.fill_opacity - second.fill_opacity) <= 1e-6
        and first.stroke_rgb == second.stroke_rgb
        and first.stroke_theme_color == second.stroke_theme_color
        and abs((first.stroke_width_px or 0.0) - (second.stroke_width_px or 0.0))
        <= 1e-6
        and abs((first.stroke_opacity or 1.0) - (second.stroke_opacity or 1.0))
        <= 1e-6
    )


def merge_runs(runs: list[Run]) -> list[Run]:
    if not runs:
        return []
    merged: list[Run] = [runs[0]]
    for run in runs[1:]:
        last = merged[-1]
        if runs_compatible(last, run):
            merged[-1] = replace(last, text=last.text + run.text)
        else:
            merged.append(run)
    return merged


# ---------------------------------------------------------------
# Run creation from resvg node / style dict
# ---------------------------------------------------------------


def run_from_resvg_node(resvg_node: Any, text: str) -> Run:
    text_style = getattr(resvg_node, "text_style", None)
    fill_style = getattr(resvg_node, "fill", None)
    stroke_style = getattr(resvg_node, "stroke", None)

    font_family = "Arial"
    font_size_pt = 12.0
    bold = False
    italic = False
    underline = False
    strike = False
    letter_spacing = None

    if text_style is not None:
        families = getattr(text_style, "font_families", None)
        if families:
            font_family = families[0] or font_family
        size = getattr(text_style, "font_size", None)
        if isinstance(size, (int, float)) and size > 0:
            font_size_pt = float(size)
        weight = str(getattr(text_style, "font_weight", "") or "").strip().lower()
        if weight:
            if weight in {"bold", "bolder"}:
                bold = True
            else:
                try:
                    bold = int(weight) >= 700
                except ValueError:
                    bold = False
        style = str(getattr(text_style, "font_style", "") or "").strip().lower()
        italic = style in {"italic", "oblique"}
        decoration = str(getattr(text_style, "text_decoration", "") or "").lower()
        underline = "underline" in decoration
        strike = "line-through" in decoration
        letter_spacing = getattr(text_style, "letter_spacing", None)

    rgb = "000000"
    fill_opacity = 1.0
    if fill_style is not None:
        color = getattr(fill_style, "color", None)
        if color is not None:
            rgb = resvg_color_to_hex(color)
        opacity = getattr(fill_style, "opacity", None)
        if isinstance(opacity, (int, float)):
            fill_opacity = float(opacity)

    stroke_rgb = None
    stroke_width_px = None
    stroke_opacity = None
    if stroke_style is not None:
        color = getattr(stroke_style, "color", None)
        if color is not None:
            stroke_rgb = resvg_color_to_hex(color)
        width = getattr(stroke_style, "width", None)
        if isinstance(width, (int, float)):
            stroke_width_px = float(width)
        opacity = getattr(stroke_style, "opacity", None)
        if isinstance(opacity, (int, float)):
            stroke_opacity = float(opacity)

    return Run(
        text=text,
        font_family=font_family,
        font_size_pt=font_size_pt,
        bold=bold,
        italic=italic,
        underline=underline,
        strike=strike,
        rgb=rgb,
        fill_opacity=fill_opacity,
        stroke_rgb=stroke_rgb,
        stroke_width_px=stroke_width_px,
        stroke_opacity=stroke_opacity,
        letter_spacing=letter_spacing,
    )


def create_run_from_style(
    text: str,
    style: Mapping[str, Any],
    *,
    resolve_text_length_fn: Any,
) -> Run:
    """Build a ``Run`` from a computed style dict.

    *resolve_text_length_fn* is the bound method
    ``TextConverter._resolve_text_length`` passed in by the coordinator so
    that unit resolution still goes through the converter context.
    """
    fill = style.get("fill") or "#000000"
    hex_color = coerce_hex_color(fill)
    fill_opacity = float(style.get("fill_opacity", 1.0))

    stroke = style.get("stroke")
    stroke_rgb = None
    stroke_width = None
    stroke_opacity = None

    if stroke and stroke.lower() != "none":
        stroke_rgb = coerce_hex_color(stroke)
        stroke_width_raw = style.get("stroke_width", "1")
        stroke_width = resolve_text_length_fn(
            stroke_width_raw,
            axis="x",
            font_size_pt=float(style.get("font_size_pt", 12.0)),
        )
        stroke_opacity = float(style.get("stroke_opacity", 1.0))

    font_size = float(style.get("font_size_pt", 12.0))
    font_family_raw = normalize_font_family_list(style.get("font_family"))
    weight_token = (style.get("font_weight") or "normal").lower()
    bold = weight_token in {"bold", "bolder", "600", "700", "800", "900"}
    font_style = (style.get("font_style") or "normal").lower()
    text_decoration = (style.get("text_decoration") or "").lower()
    underline_flag = "underline" in text_decoration
    strike_flag = any(
        token in text_decoration for token in ("line-through", "strike")
    )
    return Run(
        text=text,
        font_family=font_family_raw,
        font_size_pt=font_size,
        bold=bold,
        italic=font_style == "italic",
        underline=underline_flag,
        strike=strike_flag,
        rgb=hex_color,
        fill_opacity=fill_opacity,
        stroke_rgb=stroke_rgb,
        stroke_width_px=stroke_width,
        stroke_opacity=stroke_opacity,
    )


# ---------------------------------------------------------------
# Policy application
# ---------------------------------------------------------------


def resolve_font_fallback(
    family: str | None,
    fallback_order: Iterable[str],
) -> str | None:
    current = (family or "").strip()
    current_lower = current.lower()
    for candidate in fallback_order:
        resolved = normalize_font_family(candidate)
        if not resolved:
            continue
        if resolved.lower() == current_lower:
            continue
        return resolved

    normalized = normalize_font_family(font_fallback(current))
    if normalized and normalized.lower() != current_lower:
        return normalized
    return None


def apply_text_decision(
    run: Run,
    decision: TextPolicyDecision,
) -> tuple[Run, dict[str, Any]]:
    updated = run
    metadata: dict[str, Any] = {}

    if not decision.allow_effects and (run.bold or run.italic or run.underline):
        updated = replace(updated, bold=False, italic=False, underline=False)
        metadata["effects_stripped"] = True

    behavior = decision.fallback.missing_font_behavior.lower()
    if behavior == "fallback_family":
        fallback = resolve_font_fallback(
            updated.font_family, decision.fallback.fallback_order
        )
        if fallback and fallback.lower() != updated.font_family.lower():
            updated = replace(updated, font_family=fallback)
            metadata["font_fallback"] = fallback
    glyph_fallback = decision.fallback.glyph_fallback
    if glyph_fallback:
        metadata["glyph_fallback"] = glyph_fallback

    if decision.fallback.max_vectorized_glyphs:
        metadata["max_vectorized_glyphs"] = decision.fallback.max_vectorized_glyphs
    metadata["prefer_vector_fallback"] = decision.fallback.prefer_vector_fallback
    metadata["wordart_detection"] = {
        "enabled": decision.wordart.enable_detection,
        "confidence_threshold": decision.wordart.confidence_threshold,
    }

    return updated, metadata


# ---------------------------------------------------------------
# Module-level utility
# ---------------------------------------------------------------


def parse_float(
    value: str | None, *, default: float | None = None
) -> float | None:
    if value is None:
        return default
    value = str(value).strip()
    if not value:
        return default
    try:
        if value.endswith("%"):
            return float(value[:-1]) / 100.0
        return float(value)  # type: ignore[arg-type]
    except ValueError:
        return default
