"""Affine transform decomposition utilities."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import atan2, cos, degrees, isfinite, radians, sin, sqrt
from typing import Literal

from svg2ooxml.common.geometry.matrix import Matrix2D
from svg2ooxml.ir.geometry import Point


@dataclass
class DecomposedTransform:
    translation: Point
    rotation_deg: float
    scale_x: float
    scale_y: float
    shear: float


AffineComponent = Literal["identity", "translate", "scale", "rotate"]
AffinePayload = tuple[float, float] | float | None
AffineClassification = tuple[AffineComponent | None, AffinePayload]
ComponentPriority = Sequence[Literal["translate", "rotate", "scale"]]
DEFAULT_COMPONENT_PRIORITY: ComponentPriority = ("translate", "rotate", "scale")


def decompose_matrix(matrix: Matrix2D) -> DecomposedTransform:
    determinant = matrix.a * matrix.d - matrix.b * matrix.c
    if determinant == 0:
        raise ValueError("Matrix is not invertible, cannot decompose")

    scale_x = sqrt(matrix.a ** 2 + matrix.b ** 2)
    rotation = atan2(matrix.b, matrix.a)

    shear = (matrix.a * matrix.c + matrix.b * matrix.d) / max(scale_x ** 2, 1e-12)
    scale_y = sqrt((matrix.c ** 2 + matrix.d ** 2) - shear ** 2 * scale_x ** 2)

    return DecomposedTransform(
        translation=Point(matrix.e, matrix.f),
        rotation_deg=degrees(rotation),
        scale_x=scale_x,
        scale_y=scale_y,
        shear=shear,
    )


def compose_matrix(transform: DecomposedTransform) -> Matrix2D:
    angle = radians(transform.rotation_deg)
    cos_a = cos(angle)
    sin_a = sin(angle)

    a = cos_a * transform.scale_x
    b = sin_a * transform.scale_x
    c = -sin_a * transform.scale_y + transform.shear * cos_a * transform.scale_x
    d = cos_a * transform.scale_y + transform.shear * sin_a * transform.scale_x

    return Matrix2D(
        a=a,
        b=b,
        c=c,
        d=d,
        e=transform.translation.x,
        f=transform.translation.y,
    )


def classify_affine_matrix(
    matrix: Matrix2D,
    *,
    tolerance: float = 1e-6,
    component_priority: ComponentPriority = DEFAULT_COMPONENT_PRIORITY,
) -> AffineClassification:
    if not all(
        isfinite(v)
        for v in (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f)
    ):
        return (None, None)

    if matrix.is_identity(tolerance=tolerance):
        return ("identity", None)

    if (
        abs(matrix.a - 1.0) <= tolerance
        and abs(matrix.d - 1.0) <= tolerance
        and abs(matrix.b) <= tolerance
        and abs(matrix.c) <= tolerance
    ):
        return ("translate", (matrix.e, matrix.f))

    if (
        abs(matrix.b) <= tolerance
        and abs(matrix.c) <= tolerance
        and abs(matrix.e) <= tolerance
        and abs(matrix.f) <= tolerance
    ):
        return ("scale", (matrix.a, matrix.d))

    if (
        abs(matrix.e) <= tolerance
        and abs(matrix.f) <= tolerance
        and abs(matrix.c + matrix.b) <= tolerance
        and abs(matrix.a - matrix.d) <= tolerance
        and abs(matrix.a * matrix.a + matrix.b * matrix.b - 1.0) <= tolerance
        and abs(matrix.c * matrix.c + matrix.d * matrix.d - 1.0) <= tolerance
    ):
        return ("rotate", degrees(atan2(matrix.b, matrix.a)))

    dominant = dominant_affine_component(
        matrix,
        tolerance=tolerance,
        component_priority=component_priority,
    )
    if dominant is not None:
        return dominant
    return (None, None)


def dominant_affine_component(
    matrix: Matrix2D,
    *,
    tolerance: float = 1e-6,
    component_priority: ComponentPriority = DEFAULT_COMPONENT_PRIORITY,
) -> tuple[Literal["translate", "rotate", "scale"], tuple[float, float] | float] | None:
    tx, ty = matrix.e, matrix.f

    sx = sqrt(matrix.a**2 + matrix.b**2)
    if sx < tolerance:
        return None

    angle_deg = degrees(atan2(matrix.b, matrix.a))
    det = matrix.a * matrix.d - matrix.b * matrix.c
    sy = det / sx

    cos_a = cos(radians(angle_deg))
    sin_a = sin(radians(angle_deg))
    expected_c = -sy * sin_a
    expected_d = sy * cos_a

    if (
        abs(matrix.c - expected_c) > tolerance
        or abs(matrix.d - expected_d) > tolerance
    ):
        return None

    components: dict[str, tuple[float, float] | float] = {}
    if abs(tx) > tolerance or abs(ty) > tolerance:
        components["translate"] = (tx, ty)
    if abs(angle_deg) > tolerance:
        components["rotate"] = angle_deg
    if abs(sx - 1.0) > tolerance or abs(sy - 1.0) > tolerance:
        components["scale"] = (sx, sy)

    for component in component_priority:
        payload = components.get(component)
        if payload is not None:
            return (component, payload)
    return None


def identity_payload_for_affine_component(component: str) -> tuple[float, float] | float:
    if component == "translate":
        return (0.0, 0.0)
    if component == "scale":
        return (1.0, 1.0)
    if component == "rotate":
        return 0.0
    return (0.0, 0.0)


__all__ = [
    "AffineClassification",
    "AffineComponent",
    "AffinePayload",
    "ComponentPriority",
    "DEFAULT_COMPONENT_PRIORITY",
    "DecomposedTransform",
    "classify_affine_matrix",
    "compose_matrix",
    "decompose_matrix",
    "dominant_affine_component",
    "identity_payload_for_affine_component",
]
