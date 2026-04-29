"""Dependency-free helpers shared by full and lightweight filter planners."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from svg2ooxml.common.math_utils import (
    coerce_float as _coerce_float,
)
from svg2ooxml.common.math_utils import (
    coerce_positive_float as _coerce_positive_float,
)
from svg2ooxml.common.math_utils import (
    finite_float as _finite_float,
)

VECTOR_HINT_TAGS = {
    "fecomponenttransfer",
    "fedisplacementmap",
    "feturbulence",
    "feconvolvematrix",
    "fecolormatrix",
    "fecomposite",
    "feblend",
    "femerge",
    "fetile",
    "fediffuselighting",
    "fespecularlighting",
}
RASTER_HINT_TAGS = {
    "feimage",
}


def finite_float(value: Any) -> float | None:
    return _finite_float(value)


def coerce_float(value: Any, default: float) -> float:
    return _coerce_float(value, default)


def coerce_positive_float(value: Any, default: float) -> float:
    return _coerce_positive_float(value, default)


def is_finite_number(value: Any) -> bool:
    return finite_float(value) is not None


def is_positive_finite(value: Any) -> bool:
    number = finite_float(value)
    return number is not None and number > 0


def is_identity_color_matrix(values: list[float], *, tol: float = 1e-6) -> bool:
    """Return whether an SVG 4x5 color matrix is identity."""

    if len(values) != 20:
        return False
    identity = [
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
    ]
    return all(abs(a - b) <= tol for a, b in zip(values, identity, strict=True))


def numeric_region(region: Mapping[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(region, Mapping):
        return None
    numeric: dict[str, float] = {}
    for key in ("x", "y", "width", "height"):
        value = finite_float(region.get(key))
        if value is not None:
            numeric[key] = value
    return numeric or None


def finite_bounds(payload: Mapping[str, Any] | None) -> dict[str, float] | None:
    return numeric_region(payload)


def infer_descriptor_strategy(
    descriptor: Mapping[str, Any],
    *,
    strategy_hint: str,
) -> str | None:
    tags = descriptor.get("primitive_tags")
    if not isinstance(tags, Iterable):
        return None
    lowered = {str(tag).strip().lower() for tag in tags if tag}
    if not lowered:
        return "vector" if strategy_hint in {"vector", "emf"} else None

    if any(tag in RASTER_HINT_TAGS for tag in lowered):
        return "raster"
    if any(tag in VECTOR_HINT_TAGS for tag in lowered):
        return "vector"

    if strategy_hint in {"vector", "emf"}:
        return "vector"
    if strategy_hint == "raster":
        return "raster"
    return None


def serialize_descriptor(descriptor: Any) -> dict[str, Any]:
    primitives = getattr(descriptor, "primitives", ()) or ()
    region = getattr(descriptor, "region", {}) or {}
    return {
        "filter_id": getattr(descriptor, "filter_id", None),
        "filter_units": getattr(descriptor, "filter_units", None),
        "primitive_units": getattr(descriptor, "primitive_units", None),
        "primitive_count": len(primitives),
        "primitive_tags": [primitive.tag for primitive in primitives],
        "filter_region": dict(region),
        "primitive_metadata": [
            dict(getattr(primitive, "extras", {}) or {}) for primitive in primitives
        ],
    }


def policy_flag(config: Mapping[str, Any], name: str) -> dict[str, bool]:
    if name not in config:
        return {}
    raw = config.get(name)
    if isinstance(raw, str):
        token = raw.strip().lower()
        if token in {"true", "1", "yes", "on"}:
            return {name: True}
        if token in {"false", "0", "no", "off"}:
            return {name: False}
    elif isinstance(raw, bool):
        return {name: raw}
    elif raw is not None:
        return {name: bool(raw)}
    return {}


def policy_limit(
    config: Mapping[str, Any],
    name: str,
    cast_type: type = int,
) -> dict[str, Any]:
    if name not in config:
        return {}
    try:
        value = cast_type(config.get(name))
    except (OverflowError, TypeError, ValueError):
        return {}
    if isinstance(value, (int, float)) and (
        value < 0 or not math.isfinite(float(value))
    ):
        return {}
    return {name: value}


__all__ = [
    "RASTER_HINT_TAGS",
    "VECTOR_HINT_TAGS",
    "coerce_float",
    "coerce_positive_float",
    "finite_bounds",
    "finite_float",
    "infer_descriptor_strategy",
    "is_identity_color_matrix",
    "is_finite_number",
    "is_positive_finite",
    "numeric_region",
    "policy_flag",
    "policy_limit",
    "serialize_descriptor",
]
