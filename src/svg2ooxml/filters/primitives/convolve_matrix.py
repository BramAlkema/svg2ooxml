"""feConvolveMatrix filter primitive."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_number


@dataclass
class ConvolveMatrixParams:
    order_x: int
    order_y: int
    kernel: List[float]
    divisor: float
    bias: float
    target_x: int
    target_y: int
    edge_mode: str
    preserve_alpha: bool
    kernel_unit_length: tuple[float | None, float | None]


class ConvolveMatrixFilter(Filter):
    primitive_tags = ("feConvolveMatrix",)
    filter_type = "convolve_matrix"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive)
        metadata = {
            "filter_type": self.filter_type,
            "order": (params.order_x, params.order_y),
            "divisor": params.divisor,
            "bias": params.bias,
            "target": (params.target_x, params.target_y),
            "edge_mode": params.edge_mode,
            "preserve_alpha": params.preserve_alpha,
        }
        metadata["kernel"] = list(params.kernel)
        metadata["kernel_unit_length"] = params.kernel_unit_length
        metadata["kernel_source"] = (primitive.get("kernelMatrix") or "").strip()
        return FilterResult(
            success=True,
            drawingml="",
            fallback="emf",
            metadata=metadata,
            warnings=["feConvolveMatrix rendered via EMF fallback"],
        )

    def _parse_params(self, primitive: etree._Element) -> ConvolveMatrixParams:
        order_attr = (primitive.get("order") or "3").strip()
        if " " in order_attr:
            ox_str, oy_str = order_attr.split(" ", 1)
        else:
            ox_str = order_attr
            oy_str = order_attr
        order_x = max(1, int(parse_number(ox_str, default=3.0)))
        order_y = max(1, int(parse_number(oy_str, default=3.0)))
        kernel = self._parse_float_list(primitive.get("kernelMatrix"))
        divisor = parse_number(primitive.get("divisor"), default=1.0)
        bias = parse_number(primitive.get("bias"))
        target_x = int(parse_number(primitive.get("targetX"), default=(order_x - 1) / 2))
        target_y = int(parse_number(primitive.get("targetY"), default=(order_y - 1) / 2))
        edge_mode = (primitive.get("edgeMode") or "duplicate").strip().lower()
        preserve_alpha = (primitive.get("preserveAlpha") or "false").strip().lower() == "true"
        kernel_unit = primitive.get("kernelUnitLength")
        if kernel_unit and " " in kernel_unit:
            kx_str, ky_str = kernel_unit.split(" ", 1)
        else:
            kx_str = ky_str = kernel_unit
        kernel_unit_length = (
            parse_number(kx_str) if kx_str else None,
            parse_number(ky_str) if ky_str else None,
        )
        return ConvolveMatrixParams(
            order_x=order_x,
            order_y=order_y,
            kernel=kernel,
            divisor=divisor,
            bias=bias,
            target_x=target_x,
            target_y=target_y,
            edge_mode=edge_mode,
            preserve_alpha=preserve_alpha,
            kernel_unit_length=kernel_unit_length,
        )

    def _parse_float_list(self, payload: str | None) -> List[float]:
        if not payload:
            return []
        values: List[float] = []
        for token in payload.replace(",", " ").split():
            try:
                values.append(float(token))
            except ValueError:
                continue
        return values

__all__ = ["ConvolveMatrixFilter"]
