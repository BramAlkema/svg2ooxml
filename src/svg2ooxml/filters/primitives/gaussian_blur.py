"""Gaussian blur filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_number
from svg2ooxml.units.conversion import px_to_emu


@dataclass
class GaussianBlurParams:
    std_dev_x: float
    std_dev_y: float
    edge_mode: str

    @property
    def is_isotropic(self) -> bool:
        return abs(self.std_dev_x - self.std_dev_y) < 1e-6


class GaussianBlurFilter(Filter):
    primitive_tags = ("feGaussianBlur",)
    filter_type = "gaussian_blur"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive)
        policy_options = {}
        if isinstance(context.options, dict):
            policy_options = context.options.get("policy") or {}
        allow_anisotropic = bool(policy_options.get("allow_anisotropic_native", False))
        max_bitmap_stddev = policy_options.get("max_bitmap_stddev")

        metadata = {
            "filter_type": self.filter_type,
            "std_deviation_x": params.std_dev_x,
            "std_deviation_y": params.std_dev_y,
            "edge_mode": params.edge_mode,
            "is_isotropic": params.is_isotropic,
            "native_support": params.is_isotropic,
        }
        effective_std = max(params.std_dev_x, params.std_dev_y)
        if max_bitmap_stddev is not None and effective_std > float(max_bitmap_stddev):
            metadata["native_support"] = False
            drawingml = f"<!-- Gaussian blur exceeds policy limit ({effective_std} > {max_bitmap_stddev}) -->"
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback="bitmap",
                metadata=metadata,
                warnings=["Blur exceeds policy threshold; raster fallback required"],
            )

        if params.is_isotropic or allow_anisotropic:
            radius_source = (
                (params.std_dev_x + params.std_dev_y) / 2.0 if allow_anisotropic and not params.is_isotropic else params.std_dev_x
            )
            radius_emu = self._std_dev_to_emu(radius_source)
            drawingml = f'<a:effectLst><a:blur rad="{radius_emu}"/></a:effectLst>'
            if allow_anisotropic and not params.is_isotropic:
                metadata["anisotropic_mode"] = "approx_native"
                metadata["native_support"] = True
            return FilterResult(success=True, drawingml=drawingml, metadata=metadata)

        # Fallback path for anisotropic blur (currently unsupported)
        drawingml = f"<!-- Anisotropic Gaussian blur fallback for stdDeviation=({params.std_dev_x}, {params.std_dev_y}) -->"
        return FilterResult(
            success=True,
            drawingml=drawingml,
            fallback="bitmap",
            metadata=metadata,
            warnings=["Anisotropic blur approximated via raster fallback"],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_params(self, primitive: etree._Element) -> GaussianBlurParams:
        std_deviation = (primitive.get("stdDeviation") or "0").strip()
        if " " in std_deviation:
            sx_str, sy_str = std_deviation.split(" ", 1)
        else:
            sx_str = sy_str = std_deviation
        std_dev_x = max(0.0, parse_number(sx_str))
        std_dev_y = max(0.0, parse_number(sy_str))
        edge_mode = (primitive.get("edgeMode") or "duplicate").strip().lower()
        return GaussianBlurParams(std_dev_x=std_dev_x, std_dev_y=std_dev_y, edge_mode=edge_mode)

    def _std_dev_to_emu(self, std_dev: float) -> int:
        # PowerPoint blur radius is specified in EMUs; stdDeviation is roughly sigma.
        # Empirical mapping: radius ≈ std_dev * 2 * px_to_emu(1)
        return int(max(0.0, std_dev * 2.0 * px_to_emu(1.0)))


__all__ = ["GaussianBlurFilter"]
