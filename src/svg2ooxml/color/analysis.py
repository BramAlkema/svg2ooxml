"""Utilities for analysing colour palettes."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from svg2ooxml.common.math_utils import population_variance

from .bridge import (
    ADVANCED_COLOR_ENGINE_AVAILABLE,
    ensure_advanced_color_engine,
    to_advanced_color,
)
from .models import Color
from .parsers import coerce_color, parse_color

MAX_OKLAB_DISTANCE = 0.5  # Empirical scale factor for complexity normalisation
_MAX_STAT_SAMPLES = 256  # Subsample cap for statistical computation

__all__ = ["summarize_palette", "MAX_OKLAB_DISTANCE"]


def summarize_palette(values: Iterable[str | Color]) -> dict[str, object]:
    """Summarise an iterable of colour values."""

    colours: list[Color] = []
    hex_values: list[str] = []
    for value in values:
        colour = coerce_color(value)
        if colour is None:
            colour = parse_color(value)
        if colour is None:
            continue
        colours.append(colour)
        hex_values.append(colour.to_hex().upper())

    unique_palette = list(dict.fromkeys(hex_values))
    count = len(colours)
    stats: dict[str, object] = {
        "palette": unique_palette,
        "count": count,
        "unique": len(unique_palette),
        "has_transparency": any(colour.a < 1.0 for colour in colours),
        "recommended_space": "srgb",
        "advanced_available": False,
    }

    if not colours:
        stats["complexity"] = 0.0
        return stats

    if len(colours) > _MAX_STAT_SAMPLES:
        stride = len(colours) / _MAX_STAT_SAMPLES
        colours = [colours[int(i * stride)] for i in range(_MAX_STAT_SAMPLES)]

    l_values: list[float] = []
    a_values: list[float] = []
    b_values: list[float] = []
    oklab_values: list[tuple[float, float, float]] = []

    for colour in colours:
        l, a, b = colour.to_oklab()  # noqa: E741 -- OKLab spec notation for lightness
        oklab_values.append((l, a, b))
        l_values.append(l)
        a_values.append(a)
        b_values.append(b)

    n = len(l_values)
    mean_l = sum(l_values) / n
    mean_a = sum(a_values) / n
    mean_b = sum(b_values) / n

    variance = _mean_squared_distance(oklab_values, (mean_l, mean_a, mean_b))
    lightness_range = max(l_values) - min(l_values)

    # Derive complexity from variance (O(n)) instead of max pairwise distance (O(n^2))
    stats["complexity"] = min(1.0, math.sqrt(variance) / (MAX_OKLAB_DISTANCE / 2))

    stats.update(
        _advanced_palette_statistics(colours, lightness_range=lightness_range)
    )
    return stats


def _advanced_palette_statistics(
    colours: Sequence[Color],
    *,
    lightness_range: float,
) -> dict[str, object]:
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

    oklch_values = [colour.oklch() for colour in advanced_colours]
    hue_values = [value[2] for value in oklch_values]
    chroma_values = [value[1] for value in oklch_values]

    hue_spread = _circular_spread(hue_values)
    saturation_variance = population_variance(chroma_values)

    recommended_space = _recommend_colour_space(
        lightness_range=lightness_range,
        hue_spread=hue_spread,
        saturation_variance=saturation_variance,
    )

    return {
        "advanced_available": True,
        "hue_spread": hue_spread,
        "recommended_space": recommended_space,
    }


def _mean_squared_distance(values: Sequence[tuple[float, float, float]], center: tuple[float, float, float]) -> float:
    if not values:
        return 0.0
    total = 0.0
    c0, c1, c2 = center
    for v in values:
        total += (v[0] - c0) ** 2 + (v[1] - c1) ** 2 + (v[2] - c2) ** 2
    return total / len(values)


def _circular_spread(hues: Sequence[float]) -> float:
    if not hues:
        return 0.0
    ordered = sorted(h % 360 for h in hues)
    extended = ordered + [ordered[0] + 360.0]
    gaps = [extended[i + 1] - extended[i] for i in range(len(ordered))]
    max_gap = max(gaps)
    return 360.0 - max_gap


def _recommend_colour_space(
    *,
    lightness_range: float,
    hue_spread: float,
    saturation_variance: float,
) -> str:
    if lightness_range > 0.55 or hue_spread > 210 or saturation_variance > 0.08:
        return "linear_rgb"
    return "srgb"
