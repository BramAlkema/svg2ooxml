"""Helpers for SVG filter input-surface metadata."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

PAINT_INPUT_NAMES = ("FillPaint", "StrokePaint")


def paint_input_descriptors(
    filter_inputs: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Return explicit or SourceGraphic-derived paint input descriptors."""

    if not isinstance(filter_inputs, Mapping):
        return {}

    source_graphic = filter_inputs.get("SourceGraphic")
    descriptors: dict[str, dict[str, Any]] = {}
    for input_name in PAINT_INPUT_NAMES:
        explicit = filter_inputs.get(input_name)
        if isinstance(explicit, dict):
            descriptors[input_name] = copy.deepcopy(explicit)
            continue
        derived = derive_paint_input_descriptor(source_graphic, input_name)
        if derived is not None:
            descriptors[input_name] = derived
    return descriptors


def derive_paint_input_descriptor(
    source_graphic: Any,
    input_name: str,
) -> dict[str, Any] | None:
    """Derive a paint-only descriptor from a SourceGraphic descriptor."""

    if input_name not in PAINT_INPUT_NAMES or not isinstance(source_graphic, dict):
        return None
    descriptor = copy.deepcopy(source_graphic)
    if input_name == "FillPaint":
        descriptor["stroke"] = None
    else:
        descriptor["fill"] = None
    descriptor["paint_source"] = input_name
    return descriptor


__all__ = [
    "PAINT_INPUT_NAMES",
    "derive_paint_input_descriptor",
    "paint_input_descriptors",
]
