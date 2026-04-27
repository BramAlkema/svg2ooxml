"""Matrix classification and decomposition helpers for transform animations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.common.conversions.transforms import parse_numeric_list
from svg2ooxml.common.geometry.matrix import Matrix2D
from svg2ooxml.common.geometry.transforms.decompose import (
    classify_affine_matrix,
    dominant_affine_component,
    identity_payload_for_affine_component,
)
from svg2ooxml.drawingml.animation.handlers.transform_rotate import build_rotate_element
from svg2ooxml.drawingml.animation.handlers.transform_scale import build_scale_element

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition


class TransformMatrixMixin:
    """Matrix decomposition helpers used by ``TransformAnimationHandler``."""

    def _build_matrix_element(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
    ) -> tuple[etree._Element | None, str]:
        """Build animation element from matrix values.

        Returns (element, preset_class) or (None, "entr") on failure.
        """
        if not animation.values:
            return None, "entr"

        matrices: list[Matrix2D] = []
        for raw in animation.values:
            if not isinstance(raw, str):
                return None, "entr"
            values = parse_numeric_list(raw)
            if len(values) < 6:
                return None, "entr"
            matrices.append(Matrix2D.from_values(*values[:6]))

        matrix_type: str | None = None
        staged: list[tuple[str, object | None]] = []

        for matrix in matrices:
            current_type, payload = self._classify_matrix(matrix)
            if current_type is None:
                return None, "entr"
            if matrix_type is None:
                if current_type != "identity":
                    matrix_type = current_type
            else:
                if current_type not in {"identity", matrix_type}:
                    return None, "entr"
            staged.append((current_type, payload))

        if matrix_type is None:
            return None, "entr"

        classified: list[object] = []
        for current_type, payload in staged:
            if current_type == "identity":
                classified.append(self._identity_payload(matrix_type))
            else:
                classified.append(
                    payload
                    if payload is not None
                    else self._identity_payload(matrix_type)
                )

        if matrix_type == "translate":
            pairs = [(float(x), float(y)) for x, y in classified]
            return self._build_translate_element(animation, behavior_id, pairs), "path"
        if matrix_type == "scale":
            pairs = [(float(x), float(y)) for x, y in classified]
            return (
                build_scale_element(self._xml, animation, behavior_id, pairs),
                "entr",
            )
        if matrix_type == "rotate":
            angles = [float(angle) for angle in classified]
            return (
                build_rotate_element(
                    self._xml, self._processor, animation, behavior_id, angles
                ),
                "entr",
            )

        return None, "entr"

    @classmethod
    def _classify_matrix(
        cls,
        matrix: Matrix2D,
        *,
        tolerance: float = 1e-6,
    ) -> tuple[str | None, object | None]:
        return classify_affine_matrix(matrix, tolerance=tolerance)

    @staticmethod
    def _decompose_matrix(
        matrix: Matrix2D,
        *,
        tolerance: float = 1e-6,
    ) -> tuple[str, object] | None:
        return dominant_affine_component(matrix, tolerance=tolerance)

    @staticmethod
    def _identity_payload(matrix_type: str) -> object:
        return identity_payload_for_affine_component(matrix_type)
