"""Gaussian blur filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_number
from svg2ooxml.units.conversion import px_to_emu

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string


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
        blur_strategy = self._normalize_blur_strategy(policy_options.get("blur_strategy"))

        metadata = {
            "filter_type": self.filter_type,
            "std_deviation_x": params.std_dev_x,
            "std_deviation_y": params.std_dev_y,
            "edge_mode": params.edge_mode,
            "is_isotropic": params.is_isotropic,
            "native_support": params.is_isotropic,
            "blur_strategy": blur_strategy,
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
                (params.std_dev_x + params.std_dev_y) / 2.0
                if allow_anisotropic and not params.is_isotropic
                else params.std_dev_x
            )
            radius_emu = self._std_dev_to_emu(radius_source)
            effectLst = a_elem("effectLst")
            if blur_strategy == "outer_shadow":
                color, alpha = self._shadow_color_from_context(context)
                shadow = a_sub(
                    effectLst,
                    "outerShdw",
                    blurRad=radius_emu,
                    dist="0",
                    dir="0",
                    algn="ctr",
                    rotWithShape="0",
                )
                srgb = a_sub(shadow, "srgbClr", val=color)
                if alpha < 100000:
                    a_sub(srgb, "alpha", val=alpha)
                metadata["mimic_strategy"] = "outer_shadow"
            elif blur_strategy == "inner_shadow":
                color, alpha = self._shadow_color_from_context(context)
                shadow = a_sub(
                    effectLst,
                    "innerShdw",
                    blurRad=radius_emu,
                    dist="0",
                    dir="0",
                    algn="ctr",
                    rotWithShape="0",
                )
                srgb = a_sub(shadow, "srgbClr", val=color)
                if alpha < 100000:
                    a_sub(srgb, "alpha", val=alpha)
                metadata["mimic_strategy"] = "inner_shadow"
            elif blur_strategy == "blur":
                a_sub(effectLst, "blur", rad=radius_emu)
            else:
                # LibreOffice ignores <a:blur> in some cases; <a:softEdge> renders more consistently.
                a_sub(effectLst, "softEdge", rad=radius_emu)
            drawingml = to_string(effectLst)
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

    @staticmethod
    def _normalize_blur_strategy(value: object | None) -> str:
        token = str(value).strip().lower() if value is not None else ""
        token = token.replace("-", "_")
        if token in {"outer_shadow", "outershdw", "shadow", "drop_shadow"}:
            return "outer_shadow"
        if token in {"inner_shadow", "innershdw", "inner"}:
            return "inner_shadow"
        if token in {"blur"}:
            return "blur"
        return "soft_edge"

    @staticmethod
    def _shadow_color_from_context(context: FilterContext) -> tuple[str, int]:
        color = "000000"
        alpha = 100000
        pipeline = context.pipeline_state or {}
        source = pipeline.get("SourceGraphic")
        metadata = source.metadata if isinstance(source, FilterResult) else None
        if isinstance(metadata, dict):
            fill = metadata.get("fill")
            stroke = metadata.get("stroke")
            paint = None
            if isinstance(fill, dict) and fill.get("type") == "solid":
                paint = fill
            elif isinstance(stroke, dict):
                paint = stroke.get("paint")
            if isinstance(paint, dict):
                rgb = paint.get("rgb")
                if isinstance(rgb, str):
                    token = rgb.strip().lstrip("#")
                    if len(token) == 3:
                        token = "".join(ch * 2 for ch in token)
                    if len(token) == 6:
                        color = token.upper()
                opacity = paint.get("opacity")
                if isinstance(opacity, (int, float)):
                    alpha = int(max(0.0, min(float(opacity), 1.0)) * 100000)
        return color, alpha


__all__ = ["GaussianBlurFilter"]
