"""Shared gradient stop remapping helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence


def remap_stops_for_radial_focal_radius[T](
    stops: Sequence[T],
    *,
    radius: float,
    focal_radius: float | None,
    offset_of: Callable[[T], float],
    with_offset: Callable[[T, float], T],
) -> list[T]:
    """Approximate SVG2 radial-gradient ``fr`` by flattening initial stops."""

    items = list(stops)
    if focal_radius is None or focal_radius <= 1e-6 or len(items) < 2:
        return items

    ratio = max(0.0, min(1.0, focal_radius / max(radius, 1e-6)))
    if ratio <= 1e-6:
        return items

    first = items[0]
    if ratio >= 1.0 - 1e-6:
        return [with_offset(first, 0.0), with_offset(first, 1.0)]

    adjusted = [with_offset(first, 0.0), with_offset(first, ratio)]
    for stop in items[1:]:
        source_offset = max(0.0, min(1.0, offset_of(stop)))
        adjusted.append(with_offset(stop, ratio + source_offset * (1.0 - ratio)))
    return adjusted


__all__ = ["remap_stops_for_radial_focal_radius"]
