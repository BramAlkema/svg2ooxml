"""Small availability and metadata helpers for resvg shape conversion."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.common.math_utils import coerce_float


def _coerce_float(value: float | None, default: float) -> float:
    return coerce_float(value, default)


class ResvgUtilityMixin:
    @staticmethod
    def _append_metadata_element_id(
        metadata: dict[str, Any],
        element_id: str | None,
    ) -> None:
        if not isinstance(element_id, str) or not element_id:
            return
        element_ids = metadata.setdefault("element_ids", [])
        if not isinstance(element_ids, list):
            element_ids = []
            metadata["element_ids"] = element_ids
        if element_id not in element_ids:
            element_ids.append(element_id)

    def _resvg_miss_reason(self, element: etree._Element) -> str:
        if getattr(self, "_resvg_tree", None) is None:
            return "resvg_tree_missing"
        resvg_lookup = getattr(self, "_resvg_element_lookup", {})
        if element not in resvg_lookup:
            return "resvg_node_missing"
        return "resvg_conversion_failed"

    def _trace_resvg_only_miss(self, element: etree._Element, reason: str) -> None:
        self._trace_geometry_decision(
            element,
            "resvg_only_skip",
            {"reason": reason, "geometry_mode": "resvg-only"},
        )

    def _can_use_resvg(self, element: etree._Element) -> bool:
        """Return whether a matching resvg node is available for this element."""
        if getattr(self, "_resvg_tree", None) is None:
            return False

        resvg_lookup = getattr(self, "_resvg_element_lookup", {})
        return element in resvg_lookup

    @staticmethod
    def _matrix2d_from_resvg(matrix: Any | None) -> Matrix2D:
        if matrix is None:
            return Matrix2D.identity()
        if isinstance(matrix, Matrix2D):
            return matrix
        return Matrix2D.from_values(
            _coerce_float(getattr(matrix, "a", None), 1.0),
            _coerce_float(getattr(matrix, "b", None), 0.0),
            _coerce_float(getattr(matrix, "c", None), 0.0),
            _coerce_float(getattr(matrix, "d", None), 1.0),
            _coerce_float(getattr(matrix, "e", None), 0.0),
            _coerce_float(getattr(matrix, "f", None), 0.0),
        )

    @staticmethod
    def _geometry_fallback_flags(policy: Mapping[str, Any] | None) -> tuple[bool, bool]:
        if not policy:
            return True, True
        allow_emf = bool(policy.get("allow_emf_fallback", True)) or bool(
            policy.get("force_emf")
        )
        allow_bitmap = bool(policy.get("allow_bitmap_fallback", True)) or bool(
            policy.get("force_bitmap")
        )
        return allow_emf, allow_bitmap


__all__ = ["ResvgUtilityMixin"]
