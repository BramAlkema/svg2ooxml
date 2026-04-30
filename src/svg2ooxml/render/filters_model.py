"""Shared filter model objects and primitive capability constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from svg2ooxml.common.numpy_compat import require_numpy
from svg2ooxml.core.resvg.usvg_tree import FilterNode, FilterPrimitive

np = require_numpy("svg2ooxml.render requires NumPy; install the 'render' extra.")

REGISTERED_FILTER_PRIMITIVES = {
    "fegaussianblur",
    "feoffset",
    "feflood",
    "fecolormatrix",
    "fecomposite",
    "feblend",
    "femerge",
    "fecomponenttransfer",
    "femorphology",
    "fetile",
    "feimage",
    "fedisplacementmap",
    "feturbulence",
    "fediffuselighting",
    "fespecularlighting",
    "feconvolvematrix",
    "fedropshadow",
    "feglow",
}

RESVG_SUPPORTED_PRIMITIVES = {
    "fegaussianblur",
    "feoffset",
    "feflood",
    "fecolormatrix",
    "fecomposite",
    "feblend",
    "femerge",
    "fecomponenttransfer",
    "femorphology",
    "fetile",
    "feimage",
    "fedisplacementmap",
    "feturbulence",
    "fediffuselighting",
    "fespecularlighting",
}

# Primitives registered in the legacy FilterRegistry but not yet handled by the
# resvg pipeline. Callers can surface this list for telemetry or logging so we
# know which tags still fall back to EMF/raster rendering.
_ADDITIONAL_UNSUPPORTED = {
    "fedropshadow",
    "feglow",
}

UNSUPPORTED_FILTER_PRIMITIVES = tuple(
    sorted(
        (REGISTERED_FILTER_PRIMITIVES - RESVG_SUPPORTED_PRIMITIVES)
        | _ADDITIONAL_UNSUPPORTED
    )
)


class UnsupportedPrimitiveError(RuntimeError):
    """Raised when a filter primitive cannot be handled by the resvg pipeline."""

    def __init__(
        self, tag: str, reason: str, *, primitive: FilterPrimitive | None = None
    ) -> None:
        message = f"{tag}: {reason}"
        super().__init__(message)
        self.tag = tag
        self.reason = reason
        self.primitive = primitive


@dataclass(slots=True)
class PrimitiveUnitScale:
    """Represent unit scaling for a filter primitive in pixel space."""

    scale_x: float
    scale_y: float
    bbox_width: float
    bbox_height: float


@dataclass(slots=True)
class ComponentTransferFunction:
    """Normalised feComponentTransfer channel function."""

    func_type: str
    values: np.ndarray | None = None
    slope: float = 1.0
    intercept: float = 0.0


@dataclass(slots=True)
class ComponentTransferPlan:
    red: ComponentTransferFunction
    green: ComponentTransferFunction
    blue: ComponentTransferFunction
    alpha: ComponentTransferFunction


@dataclass(slots=True)
class FilterPrimitivePlan:
    primitive: FilterPrimitive
    tag: str
    inputs: tuple[str | None, ...] = ()
    result_name: str | None = None
    color_mode: str = "sRGB"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FilterPlan:
    filter_node: FilterNode
    primitives: list[FilterPrimitivePlan]
    input_descriptors: dict[str, dict[str, Any]] = field(default_factory=dict)


__all__ = [
    "ComponentTransferFunction",
    "ComponentTransferPlan",
    "FilterPlan",
    "FilterPrimitivePlan",
    "PrimitiveUnitScale",
    "REGISTERED_FILTER_PRIMITIVES",
    "RESVG_SUPPORTED_PRIMITIVES",
    "UNSUPPORTED_FILTER_PRIMITIVES",
    "UnsupportedPrimitiveError",
]
