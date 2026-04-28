"""Affine transform decomposition utilities."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import asin, atan2, cos, degrees, isfinite, radians, sin, sqrt
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


@dataclass(frozen=True)
class LinearTransformClass:
    """SVD-based classification of the linear part of a 2D affine transform."""

    non_uniform: bool
    has_shear: bool
    det_sign: int
    s1: float
    s2: float
    ratio: float
    scale_x: float = 0.0
    scale_y: float = 0.0
    shear_factor: float = 0.0
    shear_degrees: float = 0.0


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


def classify_linear_transform(
    a: float,
    b: float,
    c: float,
    d: float,
    eps: float = 1e-6,
) -> LinearTransformClass:
    """Classify a 2D linear transform from matrix elements ``[[a, c], [b, d]]``."""

    square_x = a * a + b * b
    shear_term = a * c + b * d
    square_y = c * c + d * d
    trace = square_x + square_y
    determinant = a * d - b * c
    discriminant = max(trace * trace - 4.0 * (determinant * determinant), 0.0)
    sqrt_discriminant = discriminant**0.5

    lambda_plus = 0.5 * (trace + sqrt_discriminant)
    lambda_minus = 0.5 * (trace - sqrt_discriminant)
    singular_1 = lambda_plus**0.5 if lambda_plus > 0 else 0.0
    singular_2 = lambda_minus**0.5 if lambda_minus > 0 else 0.0
    if singular_2 > singular_1:
        singular_1, singular_2 = singular_2, singular_1

    ratio = max(singular_1, singular_2) / max(min(singular_1, singular_2), eps)
    scale_x = sqrt(square_x)
    scale_y = sqrt(square_y)
    shear_factor = 0.0
    if scale_x > eps and scale_y > eps:
        shear_factor = abs(shear_term) / (scale_x * scale_y)
    shear_degrees = abs(degrees(asin(min(1.0, shear_factor))))
    has_shear = abs(shear_term) > eps * (square_x + square_y + 1.0)
    det_sign = -1 if determinant < -eps else (1 if determinant > eps else 0)
    non_uniform = abs(singular_1 - singular_2) > eps * max(
        singular_1,
        singular_2,
        1.0,
    )

    return LinearTransformClass(
        non_uniform=non_uniform,
        has_shear=has_shear,
        det_sign=det_sign,
        s1=singular_1,
        s2=singular_2,
        ratio=ratio,
        scale_x=scale_x,
        scale_y=scale_y,
        shear_factor=shear_factor,
        shear_degrees=shear_degrees,
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
    "LinearTransformClass",
    "classify_affine_matrix",
    "classify_linear_transform",
    "compose_matrix",
    "decompose_matrix",
    "dominant_affine_component",
    "identity_payload_for_affine_component",
]
