"""Neutral filter primitive detection shared by full and lightweight planners."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from svg2ooxml.common.units.lengths import parse_number
from svg2ooxml.filters.planner_common import is_identity_color_matrix
from svg2ooxml.filters.utils import parse_float_list


class NeutralPrimitiveMixin:
    """Detect no-op filter descriptors without requiring render backends."""

    def descriptor_is_neutral(self, descriptor: Any | None) -> bool:
        primitives = getattr(descriptor, "primitives", None)
        if descriptor is None or not primitives:
            return False
        return all(self._primitive_is_neutral(primitive) for primitive in primitives)

    def _primitive_is_neutral(self, primitive: Any) -> bool:
        tag = (getattr(primitive, "tag", "") or "").strip().lower()
        attrs = getattr(primitive, "attributes", {}) or {}
        if tag == "fegaussianblur":
            raw = self._attribute(attrs, "stdDeviation")
            std_values = parse_float_list(raw)
            if not std_values:
                return True
            return all(abs(value) <= 1e-6 for value in std_values[:2])
        if tag == "feoffset":
            dx = self._parse_float(self._attribute(attrs, "dx")) or 0.0
            dy = self._parse_float(self._attribute(attrs, "dy")) or 0.0
            return abs(dx) <= 1e-6 and abs(dy) <= 1e-6
        if tag == "fecolormatrix":
            matrix_type = (self._attribute(attrs, "type") or "matrix").strip().lower()
            if matrix_type != "matrix":
                return False
            values = parse_float_list(self._attribute(attrs, "values"))
            if not values:
                return True
            return self._is_identity_matrix(values)
        return False

    @staticmethod
    def _attribute(attributes: Mapping[str, Any], name: str) -> str | None:
        if name in attributes:
            return str(attributes[name])
        lowered = name.lower()
        for key, value in attributes.items():
            if str(key).lower() == lowered:
                return str(value)
        return None

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        parsed = parse_number(value, float("nan"))
        return None if parsed != parsed else parsed

    @staticmethod
    def _is_identity_matrix(values: list[float]) -> bool:
        return is_identity_color_matrix(values)


__all__ = ["NeutralPrimitiveMixin"]
