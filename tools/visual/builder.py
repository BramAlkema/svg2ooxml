"""Helpers for building PPTX packages from SVG fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from svg2ooxml.core.parser import ParserConfig, SVGParser
from svg2ooxml.core.pptx_exporter import (
    _apply_immediate_motion_starts,
    _coalesce_simple_position_motions,
    _compose_sampled_center_motions,
    _compose_simple_line_endpoint_animations,
    _enrich_animations_with_element_centers,
)
from svg2ooxml.core.slide_orchestrator import resolve_fidelity_tier_variant
from svg2ooxml.drawingml.writer import DrawingMLWriter
from svg2ooxml.io.pptx_assembly import PPTXPackageBuilder
from svg2ooxml.ir.entrypoints import convert_parser_output
from svg2ooxml.services import configure_services


class VisualBuildError(RuntimeError):
    """Raised when a visual test cannot build the PPTX fixture."""


@dataclass
class PptxBuildResult:
    pptx_path: Path
    slide_count: int


class PptxBuilder:
    """Build PPTX packages from SVG snippets using the svg2ooxml pipeline."""

    def __init__(
        self,
        *,
        filter_strategy: str | None = "resvg",
        geometry_mode: str | None = "resvg",
        slide_size_mode: str | None = "same",
        allow_promotion: bool = True,
        fidelity_tier: str | None = None,
    ) -> None:
        self._parser = SVGParser(ParserConfig())
        self._writer = DrawingMLWriter()
        self._builder = PPTXPackageBuilder(slide_size_mode=slide_size_mode)
        self._filter_strategy = filter_strategy
        self._geometry_mode = geometry_mode
        self._slide_size_mode = slide_size_mode or "same"
        self._allow_promotion = allow_promotion
        self._fidelity_tier = fidelity_tier.strip().lower() if isinstance(fidelity_tier, str) and fidelity_tier.strip() else None

    def build_from_svg(
        self,
        svg_text: str,
        output_path: Path,
        *,
        source_path: Path | None = None,
        tracer: Any | None = None,
        animations: list | None = None,
    ) -> PptxBuildResult:
        """Parse *svg_text*, convert to IR, and materialise a PPTX file."""

        parse_result = self._parser.parse(
            svg_text,
            source_path=str(source_path) if source_path else None,
            tracer=tracer,
        )
        if not parse_result.success or parse_result.svg_root is None:
            raise VisualBuildError(f"SVG parsing failed: {parse_result.error_message}")

        tier_variant = (
            resolve_fidelity_tier_variant(self._fidelity_tier)
            if self._fidelity_tier is not None
            else None
        )
        tier_filter_policy = (
            dict(tier_variant.policy_overrides.get("filter", {}))
            if tier_variant is not None
            else {}
        )
        tier_filter_strategy = None
        if isinstance(tier_filter_policy.get("strategy"), str):
            tier_filter_strategy = str(tier_filter_policy["strategy"])

        # Use the parser's services which includes the StyleResolver with loaded CSS rules.
        services = parse_result.services
        if services is None:
            services = configure_services(
                filter_strategy=tier_filter_strategy or self._filter_strategy,
                geometry_mode=self._geometry_mode,
            )
        else:
            _register_source_asset_root(services, source_path)
            effective_filter_strategy = tier_filter_strategy or self._filter_strategy
            if effective_filter_strategy and services.filter_service is not None:
                services.filter_service.set_strategy(effective_filter_strategy)

        policy_context = getattr(services, "policy_context", None)
        effective_overrides: dict[str, dict[str, object]] = {}
        if policy_context:
            # Update geometry policy
            if self._geometry_mode:
                geometry_policy = policy_context.get("geometry", {})
                if isinstance(geometry_policy, dict):
                    geometry_policy["geometry_mode"] = self._geometry_mode

            # Update filter policy to disable promotions if requested
            if not self._allow_promotion:
                filter_policy = policy_context.get("filter", {})
                if isinstance(filter_policy, dict):
                    # Disable global promotion
                    filter_policy["allow_promotion"] = False
                    # Also disable promotion for all primitives
                    primitives = filter_policy.setdefault("primitives", {})
                    # Apply to common primitives
                    for p in ["fediffuselighting", "fespecularlighting", "fegaussianblur", "feoffset", "fecomposite", "feblend"]:
                        primitives.setdefault(p, {})["allow_promotion"] = False

            if tier_variant is not None:
                for category, overrides in tier_variant.policy_overrides.items():
                    bucket = policy_context.get(category, {})
                    if not isinstance(bucket, dict):
                        continue
                    bucket.update(overrides)

        if tier_variant is not None:
            for category, overrides in tier_variant.policy_overrides.items():
                effective_overrides[category] = dict(overrides)

        if not self._allow_promotion:
            filter_overrides = dict(effective_overrides.get("filter", {}))
            filter_overrides["allow_promotion"] = False
            primitives = dict(filter_overrides.get("primitives", {}))
            for primitive_name in [
                "fediffuselighting",
                "fespecularlighting",
                "fegaussianblur",
                "feoffset",
                "fecomposite",
                "feblend",
            ]:
                primitive_policy = dict(primitives.get(primitive_name, {}))
                primitive_policy["allow_promotion"] = False
                primitives[primitive_name] = primitive_policy
            filter_overrides["primitives"] = primitives
            effective_overrides["filter"] = filter_overrides

        if parse_result.width_px is not None:
            services.viewport_width = parse_result.width_px
        if parse_result.height_px is not None:
            services.viewport_height = parse_result.height_px

        scene = convert_parser_output(
            parse_result,
            services=services,
            tracer=tracer,
            overrides=effective_overrides or None,
        )

        active_animations = (
            list(animations)
            if animations is not None
            else list(scene.animations or [])
        )
        if active_animations:
            active_animations = _enrich_animations_with_element_centers(
                active_animations,
                scene,
            )
            active_animations = _compose_sampled_center_motions(
                active_animations,
                scene,
            )
            active_animations = _compose_simple_line_endpoint_animations(
                active_animations,
                scene,
            )
            _apply_immediate_motion_starts(scene, active_animations)
            active_animations = _coalesce_simple_position_motions(
                active_animations,
                scene,
            )
            scene.animations = active_animations
        elif animations is not None:
            scene.animations = []

        render_result = self._writer.render_scene_from_ir(
            scene,
            tracer=tracer,
        )

        pptx_path = self._builder.build_from_results(
            [render_result],
            output_path,
            slide_size_mode=self._slide_size_mode,
        )
        return PptxBuildResult(pptx_path=pptx_path, slide_count=1)


def infer_source_asset_root(source_path: Path | None) -> Path | None:
    """Infer the local corpus root for SVG-adjacent image/font resources."""

    if source_path is None:
        return None
    try:
        resolved = Path(source_path).expanduser().resolve()
    except OSError:
        resolved = Path(source_path).expanduser().absolute()

    base_dir = resolved.parent
    for candidate in (base_dir, *base_dir.parents):
        if (candidate / "images").is_dir() or (candidate / "resources").is_dir():
            return candidate
    return base_dir


def _register_source_asset_root(services: Any, source_path: Path | None) -> None:
    resolver = getattr(services, "resolve", None)
    registrar = getattr(services, "register", None)
    if not callable(resolver) or not callable(registrar):
        return
    if resolver("asset_root") or resolver("root_dir") or resolver("source_root"):
        return
    asset_root = infer_source_asset_root(source_path)
    if asset_root is not None:
        registrar("asset_root", str(asset_root))


__all__ = [
    "PptxBuilder",
    "PptxBuildResult",
    "VisualBuildError",
    "infer_source_asset_root",
]
