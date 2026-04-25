"""feConvolveMatrix filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.common.units import px_to_emu

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_float_list, parse_number
from svg2ooxml.filters.utils.parsing import parse_length


@dataclass
class ConvolveMatrixParams:
    order_x: int
    order_y: int
    kernel: list[float]
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
        params = self._parse_params(primitive, context)
        policy_options = context.policy
        approximation_allowed = bool(policy_options.get("approximation_allowed", True))
        blur_strategy = str(policy_options.get("blur_strategy") or "soft_edge").strip().lower()

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

        if self._is_identity_kernel(params):
            metadata["native_support"] = True
            metadata["no_op"] = True
            metadata["reason"] = "identity_kernel"
            return FilterResult(
                success=True,
                drawingml="",
                fallback=None,
                metadata=metadata,
            )

        if approximation_allowed and self._is_box_blur(params):
            drawingml = self._approximate_blur(params, blur_strategy=blur_strategy)
            metadata["native_support"] = True
            metadata["approximation"] = "box_blur"
            metadata["blur_strategy"] = blur_strategy
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback=None,
                metadata=metadata,
            )

        return FilterResult(
            success=True,
            drawingml="",
            fallback="emf",
            metadata=metadata,
            warnings=["feConvolveMatrix rendered via EMF fallback"],
        )

    def _parse_params(self, primitive: etree._Element, context: FilterContext) -> ConvolveMatrixParams:
        order_attr = (primitive.get("order") or "3").strip()
        order_values = parse_float_list(order_attr)
        if len(order_values) >= 2:
            order_x = max(1, int(order_values[0]))
            order_y = max(1, int(order_values[1]))
        elif order_values:
            order_x = order_y = max(1, int(order_values[0]))
        else:
            order_x = order_y = 3
        kernel = parse_float_list(primitive.get("kernelMatrix"))
        default_divisor = sum(kernel) if kernel else 1.0
        if abs(default_divisor) <= 1e-12:
            default_divisor = 1.0
        divisor = parse_number(primitive.get("divisor"), default=default_divisor)
        bias = parse_number(primitive.get("bias"))
        target_x = int(parse_number(primitive.get("targetX"), default=order_x // 2))
        target_y = int(parse_number(primitive.get("targetY"), default=order_y // 2))
        edge_mode = (primitive.get("edgeMode") or "duplicate").strip().lower()
        preserve_alpha = (primitive.get("preserveAlpha") or "false").strip().lower() == "true"
        kernel_unit = primitive.get("kernelUnitLength")
        kernel_unit_values = (kernel_unit or "").replace(",", " ").split()
        if len(kernel_unit_values) >= 2:
            kx_str, ky_str = kernel_unit_values[0], kernel_unit_values[1]
        else:
            kx_str = ky_str = kernel_unit
        kernel_unit_length = (
            parse_length(kx_str, context=context, axis="x") if kx_str else None,
            parse_length(ky_str, context=context, axis="y") if ky_str else None,
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

    def _is_identity_kernel(self, params: ConvolveMatrixParams) -> bool:
        kernel = params.kernel
        if not kernel:
            return False
        expected_len = params.order_x * params.order_y
        if len(kernel) != expected_len:
            return False
        if params.divisor == 0:
            return False
        if abs(params.bias) > 1e-6:
            return False
        target_index = params.target_y * params.order_x + params.target_x
        if target_index < 0 or target_index >= len(kernel):
            return False
        tol = 1e-6
        normalized = [val / params.divisor for val in kernel]
        for idx, val in enumerate(normalized):
            expected = 1.0 if idx == target_index else 0.0
            if abs(val - expected) > tol:
                return False
        return True

    def _is_box_blur(self, params: ConvolveMatrixParams) -> bool:
        kernel = params.kernel
        if not kernel:
            return False
        expected_len = params.order_x * params.order_y
        if len(kernel) != expected_len:
            return False
        if params.divisor == 0:
            return False
        if abs(params.bias) > 1e-6:
            return False
        if any(val < 0 for val in kernel):
            return False
        first = kernel[0]
        tol = 1e-6
        if any(abs(val - first) > tol for val in kernel[1:]):
            return False
        return True

    def _approximate_blur(self, params: ConvolveMatrixParams, *, blur_strategy: str) -> str:
        radius_px = max(params.order_x, params.order_y) / 2.0
        kx, ky = params.kernel_unit_length
        if isinstance(kx, (int, float)):
            radius_px *= max(0.0, float(kx))
        if isinstance(ky, (int, float)):
            radius_px *= max(0.0, float(ky))
        radius_emu = int(px_to_emu(max(0.0, radius_px)))
        effectLst = a_elem("effectLst")
        if blur_strategy in {"blur", "soft_edge", "softedge"}:
            if blur_strategy == "blur":
                a_sub(effectLst, "blur", rad=radius_emu)
            else:
                a_sub(effectLst, "softEdge", rad=radius_emu)
        else:
            a_sub(effectLst, "softEdge", rad=radius_emu)
        return to_string(effectLst)

__all__ = ["ConvolveMatrixFilter"]
