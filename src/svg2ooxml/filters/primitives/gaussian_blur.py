"""Gaussian blur filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.common.conversions.opacity import opacity_to_ppt
from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.common.units import px_to_emu

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils.parsing import parse_length


@dataclass
class GaussianBlurParams:
    std_dev_x: float
    std_dev_y: float
    edge_mode: str
    input_name: str | None

    @property
    def is_isotropic(self) -> bool:
        return abs(self.std_dev_x - self.std_dev_y) < 1e-6


class GaussianBlurFilter(Filter):
    primitive_tags = ("feGaussianBlur",)
    filter_type = "gaussian_blur"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive, context)
        policy_options = context.policy
        primitive_policy = self._primitive_policy(policy_options)
        allow_anisotropic = bool(policy_options.get("allow_anisotropic_native", False))
        approximation_allowed = bool(policy_options.get("approximation_allowed", True))
        max_bitmap_stddev = policy_options.get("max_bitmap_stddev")
        group_mimic_enabled = self._group_mimic_enabled(context, primitive_policy)
        blur_strategy = self._resolve_blur_strategy(
            policy_options.get("blur_strategy"),
            primitive_policy,
            group_mimic_enabled,
        )
        radius_scale = self._resolve_radius_scale(
            primitive_policy,
            group_mimic_enabled,
        )

        metadata = {
            "filter_type": self.filter_type,
            "std_deviation_x": params.std_dev_x,
            "std_deviation_y": params.std_dev_y,
            "edge_mode": params.edge_mode,
            "input": params.input_name,
            "is_isotropic": params.is_isotropic,
            "native_support": params.is_isotropic,
            "blur_strategy": blur_strategy,
            "radius_scale": radius_scale,
        }
        if (
            params.input_name
            and params.input_name not in {"SourceGraphic", "SourceAlpha"}
            and not approximation_allowed
        ):
            metadata["native_support"] = False
            metadata["approximation_blocked"] = "intermediate_input"
            drawingml = "<!-- Intermediate Gaussian blur rendered via raster fallback -->"
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback="bitmap",
                metadata=metadata,
                warnings=["Intermediate Gaussian blur rendered via raster fallback"],
            )
        grouped_source = _source_is_grouped_reference(context)
        if grouped_source and not group_mimic_enabled:
            metadata["native_support"] = False
            metadata["approximation_blocked"] = "group_source"
            drawingml = "<!-- Group Gaussian blur rendered via raster fallback -->"
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback="bitmap",
                metadata=metadata,
                warnings=["Grouped Gaussian blur rendered via raster fallback"],
            )
        if grouped_source and group_mimic_enabled:
            metadata["approximation"] = "group_per_child"
            metadata["mimic_scope"] = "group_children"
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
            radius_emu = self._std_dev_to_emu(radius_source, radius_scale=radius_scale)
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

    def _parse_params(self, primitive: etree._Element, context: FilterContext) -> GaussianBlurParams:
        std_deviation = (primitive.get("stdDeviation") or "0").strip()
        if " " in std_deviation:
            sx_str, sy_str = std_deviation.split(" ", 1)
        else:
            sx_str = sy_str = std_deviation
        std_dev_x = max(0.0, parse_length(sx_str, context=context, axis="x"))
        std_dev_y = max(0.0, parse_length(sy_str, context=context, axis="y"))
        edge_mode = (primitive.get("edgeMode") or "duplicate").strip().lower()
        input_name = primitive.get("in")
        return GaussianBlurParams(
            std_dev_x=std_dev_x,
            std_dev_y=std_dev_y,
            edge_mode=edge_mode,
            input_name=input_name.strip() if isinstance(input_name, str) and input_name.strip() else None,
        )

    def _std_dev_to_emu(self, std_dev: float, *, radius_scale: float = 2.0) -> int:
        # PowerPoint blur radius is specified in EMUs; stdDeviation is roughly sigma.
        return int(max(0.0, std_dev * radius_scale * px_to_emu(1.0)))

    @staticmethod
    def _primitive_policy(policy_options: dict[str, object]) -> dict[str, object]:
        primitives = policy_options.get("primitives")
        if not isinstance(primitives, dict):
            return {}
        candidate = primitives.get("fegaussianblur")
        if not isinstance(candidate, dict):
            return {}
        return candidate

    @staticmethod
    def _group_mimic_enabled(
        context: FilterContext,
        primitive_policy: dict[str, object],
    ) -> bool:
        if not _source_is_grouped_reference(context):
            return False
        if not bool(context.policy.get("approximation_allowed", False)):
            return False
        return bool(primitive_policy.get("allow_group_mimic", False))

    @staticmethod
    def _resolve_blur_strategy(
        strategy_value: object | None,
        primitive_policy: dict[str, object],
        group_mimic_enabled: bool,
    ) -> str:
        if group_mimic_enabled:
            group_strategy = primitive_policy.get("group_blur_strategy")
            if group_strategy is not None:
                return GaussianBlurFilter._normalize_blur_strategy(group_strategy)
            if GaussianBlurFilter._normalize_blur_strategy(strategy_value) == "soft_edge":
                # For grouped content, native <a:blur> tracks PowerPoint's appearance
                # more closely than softEdge while remaining editable.
                return "blur"
        return GaussianBlurFilter._normalize_blur_strategy(strategy_value)

    @staticmethod
    def _resolve_radius_scale(
        primitive_policy: dict[str, object],
        group_mimic_enabled: bool,
    ) -> float:
        if group_mimic_enabled:
            group_scale = GaussianBlurFilter._coerce_positive_float(
                primitive_policy.get("group_radius_scale")
            )
            if group_scale is not None:
                return group_scale
        base_scale = GaussianBlurFilter._coerce_positive_float(
            primitive_policy.get("radius_scale")
        )
        if base_scale is not None:
            return base_scale
        return 2.0

    @staticmethod
    def _coerce_positive_float(value: object | None) -> float | None:
        try:
            scale = float(value)
        except (TypeError, ValueError):
            return None
        if scale <= 0:
            return None
        return scale

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
                    alpha = opacity_to_ppt(float(opacity))
        return color, alpha


def _source_is_grouped_reference(context: FilterContext) -> bool:
    options = context.options if isinstance(context.options, dict) else {}
    element = options.get("element")
    tag = getattr(element, "tag", None)
    if isinstance(tag, str):
        if local_name(tag) in {"use", "g"}:
            return True
    return False


__all__ = ["GaussianBlurFilter"]
