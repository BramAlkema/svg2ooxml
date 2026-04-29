"""Shared FilterResult helper utilities for filter primitives."""

from __future__ import annotations

from svg2ooxml.color.utils import rgb_channels_to_hex
from svg2ooxml.filters.base import FilterResult
from svg2ooxml.filters.metadata import (
    FilterFallbackAssetPayload,
    collect_fallback_asset_payloads,
)

_FALLBACK_PRECEDENCE = {"bitmap": 3, "raster": 3, "emf": 2, "vector": 1}


def merge_fallback_mode(current: str | None, new_value: str | None) -> str | None:
    if new_value is None:
        return current
    if current is None:
        return new_value
    current_rank = _FALLBACK_PRECEDENCE.get(current, 0)
    new_rank = _FALLBACK_PRECEDENCE.get(new_value, 0)
    return new_value if new_rank > current_rank else current


def collect_fallback_assets(
    *results: FilterResult | None,
) -> list[FilterFallbackAssetPayload]:
    assets: list[FilterFallbackAssetPayload] = []
    for result in results:
        if result is None:
            continue
        assets.extend(collect_fallback_asset_payloads(result.metadata))
    return assets


def approximate_gradient_color(
    stops: list[dict[str, object]],
) -> tuple[str, float] | None:
    parsed: list[tuple[float, int, int, int, float]] = []
    total = len(stops)
    for index, stop in enumerate(stops):
        if not isinstance(stop, dict):
            continue
        rgb = stop.get("rgb")
        if not isinstance(rgb, str):
            continue
        token = rgb.strip().lstrip("#").upper()
        if len(token) == 3:
            token = "".join(ch * 2 for ch in token)
        if len(token) != 6:
            continue
        try:
            r = int(token[0:2], 16)
            g = int(token[2:4], 16)
            b = int(token[4:6], 16)
        except ValueError:
            continue
        try:
            offset = float(stop.get("offset", index / max(1, total - 1)))
        except (TypeError, ValueError):
            offset = index / max(1, total - 1)
        offset = max(0.0, min(1.0, offset))
        try:
            opacity = float(stop.get("opacity", 1.0))
        except (TypeError, ValueError):
            opacity = 1.0
        opacity = max(0.0, min(1.0, opacity))
        parsed.append((offset, r, g, b, opacity))

    if not parsed:
        return None
    parsed.sort(key=lambda item: item[0])
    if parsed[0][0] > 0.0:
        parsed.insert(0, (0.0, parsed[0][1], parsed[0][2], parsed[0][3], parsed[0][4]))
    if parsed[-1][0] < 1.0:
        parsed.append((1.0, parsed[-1][1], parsed[-1][2], parsed[-1][3], parsed[-1][4]))

    total_weight = 0.0
    sum_r = sum_g = sum_b = 0.0
    sum_opacity = 0.0
    for idx in range(len(parsed) - 1):
        o0, r0, g0, b0, a0 = parsed[idx]
        o1, r1, g1, b1, a1 = parsed[idx + 1]
        weight = max(0.0, o1 - o0)
        if weight <= 0:
            continue
        avg_r = (r0 + r1) / 2.0
        avg_g = (g0 + g1) / 2.0
        avg_b = (b0 + b1) / 2.0
        avg_a = (a0 + a1) / 2.0
        sum_r += avg_r * weight
        sum_g += avg_g * weight
        sum_b += avg_b * weight
        sum_opacity += avg_a * weight
        total_weight += weight

    if total_weight <= 0:
        return None
    r = int(round(sum_r / total_weight))
    g = int(round(sum_g / total_weight))
    b = int(round(sum_b / total_weight))
    avg_opacity = max(0.0, min(1.0, sum_opacity / total_weight))
    return rgb_channels_to_hex(r, g, b, scale="byte"), avg_opacity


__all__ = [
    "approximate_gradient_color",
    "collect_fallback_assets",
    "merge_fallback_mode",
]
