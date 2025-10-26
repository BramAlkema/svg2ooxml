"""Utilities for analysing colour palettes."""

from __future__ import annotations

import math
from statistics import mean
from typing import Iterable, Sequence

from .bridge import (
    ADVANCED_COLOR_ENGINE_AVAILABLE,
    ensure_advanced_color_engine,
    to_advanced_color,
)
from .models import Color
from .parsers import parse_color

MAX_OKLAB_DISTANCE = 0.5  # Empirical scale factor for complexity normalisation

__all__ = ["summarize_palette", "MAX_OKLAB_DISTANCE"]


def summarize_palette(values: Iterable[str | Color]) -> dict[str, object]:
    """Summarise an iterable of colour values."""

    colours: list[Color] = []
    palette_all: list[str] = []
    for value in values:
        colour = value if isinstance(value, Color) else parse_color(value)
        if colour is None:
            continue
        colours.append(colour)
        palette_all.append(colour.to_hex().upper())

    unique_palette = list(dict.fromkeys(palette_all))
    count = len(colours)
    stats: dict[str, object] = {
        "palette": unique_palette,
        "palette_all": palette_all,
        "count": count,
        "unique": len(unique_palette),
        "has_transparency": any(colour.a < 1.0 for colour in colours),
        "recommended_space": "srgb",
        "advanced_available": False,
    }

    if not colours:
        stats.update(
            {
                "mean_oklab": (0.0, 0.0, 0.0),
                "max_oklab_distance": 0.0,
                "variance_oklab": 0.0,
                "lightness_range": 0.0,
                "chroma_range": 0.0,
                "alpha_range": 0.0,
                "complexity": 0.0,
            }
        )
        return stats

    l_values: list[float] = []
    a_values: list[float] = []
    b_values: list[float] = []
    chroma_values: list[float] = []
    alpha_values: list[float] = []
    oklab_values: list[tuple[float, float, float]] = []

    for colour in colours:
        l, a, b = colour.to_oklab()
        oklab_values.append((l, a, b))
        l_values.append(l)
        a_values.append(a)
        b_values.append(b)
        chroma_values.append(math.sqrt(a * a + b * b))
        alpha_values.append(colour.a)

    mean_l = sum(l_values) / count
    mean_a = sum(a_values) / count
    mean_b = sum(b_values) / count
    mean_lab = (mean_l, mean_a, mean_b)

    variance = _mean_squared_distance(oklab_values, mean_lab)
    max_distance = _max_pairwise_distance(oklab_values)

    stats.update(
        {
            "mean_oklab": mean_lab,
            "variance_oklab": variance,
            "max_oklab_distance": max_distance,
            "lightness_range": max(l_values) - min(l_values),
            "chroma_range": max(chroma_values) - min(chroma_values),
            "alpha_range": max(alpha_values) - min(alpha_values),
            "complexity": min(1.0, max_distance / MAX_OKLAB_DISTANCE),
        }
    )

    stats.update(_advanced_palette_statistics(colours, stats))
    return stats


def _advanced_palette_statistics(colours: Sequence[Color], base_stats: dict[str, object]) -> dict[str, object]:
    """Augment palette statistics using the advanced colour engine when available."""

    if not colours or not ADVANCED_COLOR_ENGINE_AVAILABLE:
        return {"advanced_available": False}

    try:
        ensure_advanced_color_engine()
    except RuntimeError:
        return {"advanced_available": False}

    advanced_colours = []
    for colour in colours:
        try:
            advanced_colours.append(to_advanced_color(colour))
        except Exception:
            continue

    if not advanced_colours:
        return {"advanced_available": False}

    oklab_values = [colour.oklab() for colour in advanced_colours]
    oklch_values = [colour.oklch() for colour in advanced_colours]
    hue_values = [value[2] for value in oklch_values]
    chroma_values = [value[1] for value in oklch_values]
    lightness_values = [value[0] for value in oklch_values]

    hue_spread = _circular_spread(hue_values)

    try:
        mean_hue = _circular_mean(hue_values)
    except ZeroDivisionError:
        mean_hue = 0.0

    mean_chroma = mean(chroma_values) if chroma_values else 0.0
    mean_lightness = mean(lightness_values) if lightness_values else 0.0

    stats: dict[str, object] = {
        "advanced_available": True,
        "mean_oklch": (mean_lightness, mean_chroma, mean_hue),
        "hue_spread": hue_spread,
        "max_chroma": max(chroma_values) if chroma_values else 0.0,
        "min_chroma": min(chroma_values) if chroma_values else 0.0,
        "saturation_variance": _variance(chroma_values),
        "lightness_std": math.sqrt(_variance(lightness_values)),
    }

    stats["recommended_space"] = _recommend_colour_space(stats, base_stats)

    stats["lighten_preview"] = [
        colour.lighten(0.12).hex(include_hash=True).upper() for colour in advanced_colours
    ]
    stats["saturate_preview"] = [
        colour.saturate(0.18).hex(include_hash=True).upper() for colour in advanced_colours
    ]

    try:
        from .advanced import ColorHarmony  # Local import to avoid eager load churn

        harmony = ColorHarmony(advanced_colours[0])
        harmony_count = min(max(len(advanced_colours), 3), 6)
        stats["harmony_suggestions"] = [
            colour.hex(include_hash=True).upper() for colour in harmony.analogous(count=harmony_count)
        ]
    except Exception:
        stats["harmony_suggestions"] = []

    if len(advanced_colours) >= 2:
        try:
            from .advanced import ColorAccessibility

            accessibility = ColorAccessibility()
            contrast = accessibility.contrast_ratio(advanced_colours[0], advanced_colours[1])
            stats["pairwise_contrast"] = contrast
        except Exception:
            stats["pairwise_contrast"] = None
    else:
        stats["pairwise_contrast"] = None

    return stats


def _mean_squared_distance(values: Sequence[tuple[float, float, float]], mean: tuple[float, float, float]) -> float:
    if not values:
        return 0.0
    total = 0.0
    for v in values:
        total += _oklab_distance(v, mean) ** 2
    return total / len(values)


def _max_pairwise_distance(values: Sequence[tuple[float, float, float]]) -> float:
    max_distance = 0.0
    for index, first in enumerate(values):
        for second in values[index + 1 :]:
            max_distance = max(max_distance, _oklab_distance(first, second))
    return max_distance


def _oklab_distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return math.sqrt(
        (first[0] - second[0]) ** 2
        + (first[1] - second[1]) ** 2
        + (first[2] - second[2]) ** 2
    )


def _variance(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    m = mean(values)
    return sum((value - m) ** 2 for value in values) / len(values)


def _circular_spread(hues: Sequence[float]) -> float:
    if not hues:
        return 0.0
    ordered = sorted(h % 360 for h in hues)
    extended = ordered + [ordered[0] + 360.0]
    gaps = [extended[i + 1] - extended[i] for i in range(len(ordered))]
    max_gap = max(gaps)
    return 360.0 - max_gap


def _circular_mean(hues: Sequence[float]) -> float:
    if not hues:
        return 0.0
    sin_sum = sum(math.sin(math.radians(h)) for h in hues)
    cos_sum = sum(math.cos(math.radians(h)) for h in hues)
    angle = math.degrees(math.atan2(sin_sum, cos_sum))
    return angle % 360.0


def _recommend_colour_space(advanced_stats: dict[str, object], base_stats: dict[str, object]) -> str:
    lightness_range = float(base_stats.get("lightness_range", 0.0))
    hue_spread = float(advanced_stats.get("hue_spread", 0.0))
    saturation_variance = float(advanced_stats.get("saturation_variance", 0.0))

    if lightness_range > 0.55 or hue_spread > 210 or saturation_variance > 0.08:
        return "linear_rgb"
    return "srgb"
