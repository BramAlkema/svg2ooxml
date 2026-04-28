"""High-level helpers that convert SVG snippets into PPTX packages."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from svg2ooxml.core.animation import SMILParser, TimelineSampler, TimelineSamplingConfig
from svg2ooxml.core.export.animation_processor import (
    _build_animation_metadata,
    _compose_sampled_center_motions,
    _enrich_animations_with_element_centers,
    _expand_deterministic_repeat_triggers,
    _lower_safe_group_transform_targets_with_animated_descendants,
    _prepare_scene_for_native_opacity_effects,
)
from svg2ooxml.core.export.motion_geometry import _apply_immediate_motion_starts
from svg2ooxml.core.export.polyline_materialization import (
    _materialize_stroked_polyline_groups,
)
from svg2ooxml.core.export.variant_expansion import (
    _coalesce_simple_position_motions,
    _compose_simple_line_endpoint_animations,
    _materialize_simple_line_paths,
    _merge_trace_reports,
)
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.core.parser import ParserConfig, SVGParser
from svg2ooxml.core.pptx_exporter_pages import build_page_result, page_variant_type
from svg2ooxml.core.pptx_exporter_parallel import SvgToPptxParallelMixin
from svg2ooxml.core.pptx_exporter_types import (
    SvgConversionError,
    SvgPageResult,
    SvgPageSource,
    SvgToPptxMultiResult,
    SvgToPptxResult,
)
from svg2ooxml.core.slide_orchestrator import (
    build_fidelity_tier_variants,
    derive_variants_from_trace,
    expand_page_with_variants,
)
from svg2ooxml.core.tracing import ConversionTracer
from svg2ooxml.drawingml.animation.visibility_compiler import (
    assign_missing_visibility_source_ids,
    rewrite_visibility_animations,
)
from svg2ooxml.drawingml.result import DrawingMLRenderResult
from svg2ooxml.drawingml.writer import DrawingMLWriter
from svg2ooxml.io.pptx_assembly import ALLOWED_SLIDE_SIZE_MODES, PPTXPackageBuilder
from svg2ooxml.ir import convert_parser_output
from svg2ooxml.ir.animation import AnimationScene, AnimationSummary
from svg2ooxml.policy import PolicyContext
from svg2ooxml.services import configure_services


class SvgToPptxExporter(SvgToPptxParallelMixin):
    """Facade around the parsing and packaging pipeline used by the CLI."""

    def __init__(
        self,
        parser: SVGParser | None = None,
        writer: DrawingMLWriter | None = None,
        builder: PPTXPackageBuilder | None = None,
        *,
        animation_parser_factory: type[SMILParser] | None = None,
        timeline_sampler: TimelineSampler | None = None,
        timeline_config: TimelineSamplingConfig | None = None,
        filter_strategy: str | None = None,
        geometry_mode: str | None = None,
        slide_size_mode: str | None = None,
    ) -> None:
        """Initialize the SVG to PPTX exporter.

        Args:
            parser: Optional custom SVG parser
            writer: Optional custom DrawingML writer
            builder: Optional custom PPTX builder
            animation_parser_factory: Optional animation parser factory
            timeline_sampler: Optional timeline sampler
            timeline_config: Optional timeline config
            filter_strategy: Optional filter strategy
            geometry_mode: Geometry extraction mode: "legacy", "resvg", or "resvg-only".
                          Defaults to "resvg-only". Can also be set via
                          SVG2OOXML_GEOMETRY_MODE environment variable.
        """
        import os

        custom_parallel_components = []
        if parser is not None:
            custom_parallel_components.append("parser")
        if writer is not None:
            custom_parallel_components.append("writer")
        if animation_parser_factory is not None:
            custom_parallel_components.append("animation_parser_factory")
        if timeline_sampler is not None:
            custom_parallel_components.append("timeline_sampler")
        if timeline_config is not None:
            custom_parallel_components.append("timeline_config")
        self._parallel_unsupported_components = tuple(custom_parallel_components)

        self._parser = parser or SVGParser(ParserConfig())
        self._writer = writer or DrawingMLWriter()
        self._animation_parser_factory = animation_parser_factory or SMILParser
        if timeline_sampler is not None:
            self._timeline_sampler = timeline_sampler
        else:
            self._timeline_sampler = TimelineSampler(timeline_config)
        self._filter_strategy = filter_strategy

        # Geometry mode: check parameter, then env var, then default to "resvg-only"
        if geometry_mode is not None:
            self._geometry_mode = geometry_mode
        else:
            self._geometry_mode = os.environ.get(
                "SVG2OOXML_GEOMETRY_MODE", "resvg-only"
            )

        # Validate geometry_mode
        if self._geometry_mode not in ("legacy", "resvg", "resvg-only"):
            raise ValueError(
                f"Invalid geometry_mode: {self._geometry_mode!r}. "
                f"Must be 'legacy', 'resvg', or 'resvg-only'."
            )

        env_slide_mode = os.environ.get("SVG2OOXML_SLIDE_SIZE_MODE")
        mode = slide_size_mode or env_slide_mode or "same"
        if mode not in ALLOWED_SLIDE_SIZE_MODES:
            raise ValueError(
                f"Invalid slide_size_mode: {mode!r}. "
                f"Must be one of {sorted(ALLOWED_SLIDE_SIZE_MODES)}."
            )
        self._slide_size_mode = mode

        self._builder = builder or PPTXPackageBuilder(
            slide_size_mode=self._slide_size_mode
        )

    # ------------------------------------------------------------------
    # Single document conversion
    # ------------------------------------------------------------------

    def convert_file(
        self,
        input_path: Path,
        output_path: Path | None = None,
        *,
        tracer: ConversionTracer | None = None,
        policy_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> SvgToPptxResult:
        """Convert the SVG located at *input_path* into a PPTX package."""

        if not input_path.exists():
            raise SvgConversionError(f"Input file does not exist: {input_path}")

        svg_text = input_path.read_text(encoding="utf-8")
        target_path = output_path or input_path.with_suffix(".pptx")
        return self.convert_string(
            svg_text,
            target_path,
            tracer=tracer,
            source_path=str(input_path),
            policy_overrides=policy_overrides,
        )

    def convert_string(
        self,
        svg_text: str,
        output_path: Path,
        *,
        tracer: ConversionTracer | None = None,
        source_path: str | None = None,
        policy_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> SvgToPptxResult:
        """Convert an SVG payload into a PPTX written to *output_path*."""

        active_tracer = tracer or ConversionTracer()
        render_result, scene = self._render_svg(
            svg_text,
            active_tracer,
            source_path=source_path,
            policy_overrides=policy_overrides,
        )
        pptx_path = self._builder.build_from_results(
            [render_result],
            output_path,
            tracer=active_tracer,
            slide_size_mode=self._slide_size_mode,
        )

        report_dict = active_tracer.report().to_dict()
        if isinstance(scene.metadata, dict):
            scene.metadata["trace_report"] = report_dict

        return SvgToPptxResult(
            pptx_path=pptx_path, slide_count=1, trace_report=report_dict
        )

    # ------------------------------------------------------------------
    # Multi document conversion
    # ------------------------------------------------------------------

    def convert_pages(
        self,
        pages: Sequence[SvgPageSource],
        output_path: Path,
        *,
        tracer: ConversionTracer | None = None,
        split_fallback_variants: bool = False,
        render_tiers: bool = False,
        parallel: bool = False,
        max_workers: int | None = None,
    ) -> SvgToPptxMultiResult:
        """Convert multiple SVG payloads into a multi-slide PPTX."""

        if not pages:
            raise SvgConversionError(
                "At least one SVG page is required for multi-slide conversion."
            )

        packaging_tracer = tracer or ConversionTracer()

        if parallel and not render_tiers and not split_fallback_variants:
            return self._convert_pages_parallel(
                pages,
                output_path,
                packaging_tracer,
                max_workers=max_workers,
            )

        page_results: list[SvgPageResult] = []
        slide_count = 0

        with self._builder.begin_streaming(tracer=packaging_tracer) as stream:
            for index, page in enumerate(pages, start=1):
                if render_tiers:
                    tier_variants = build_fidelity_tier_variants()
                    page_seed = page
                    if not page.title and not page.name:
                        page_seed = SvgPageSource(
                            svg_text=page.svg_text,
                            title=f"Slide {index}",
                            name=page.name,
                            metadata=page.metadata,
                        )
                    variant_pages = expand_page_with_variants(page_seed, tier_variants)
                    for variant_page in variant_pages:
                        variant_overrides = (variant_page.metadata or {}).get(
                            "policy_overrides"
                        )
                        variant_tracer = ConversionTracer()
                        variant_source_path = (variant_page.metadata or {}).get(
                            "source_path"
                        )
                        variant_render, variant_scene = self._render_svg(
                            variant_page.svg_text,
                            variant_tracer,
                            variant_overrides,
                            source_path=variant_source_path,
                        )
                        variant_report = variant_tracer.report().to_dict()
                        page_result = build_page_result(
                            variant_page,
                            variant_scene,
                            variant_report,
                            fallback_title=f"Slide {index}",
                            variant_type=page_variant_type(variant_page),
                        )

                        stream.add_slide(variant_render)
                        slide_count += 1
                        del variant_render
                        page_results.append(page_result)
                    continue

                base_overrides = (page.metadata or {}).get("policy_overrides")
                base_tracer = ConversionTracer()
                source_path = (page.metadata or {}).get("source_path")
                render_result, scene = self._render_svg(
                    page.svg_text,
                    base_tracer,
                    base_overrides,
                    source_path=source_path,
                )
                report_dict = base_tracer.report().to_dict()
                page_result = build_page_result(
                    page,
                    scene,
                    report_dict,
                    fallback_title=f"Slide {index}",
                    variant_type="base",
                    include_page_metadata=True,
                )

                stream.add_slide(render_result)
                slide_count += 1
                del render_result
                page_results.append(page_result)

                if split_fallback_variants:
                    variants = derive_variants_from_trace(
                        report_dict, enable_split=True
                    )
                    variant_pages = expand_page_with_variants(page, variants)
                    for variant_page in variant_pages:
                        variant_overrides = (variant_page.metadata or {}).get(
                            "policy_overrides"
                        )
                        variant_tracer = ConversionTracer()
                        variant_source_path = (variant_page.metadata or {}).get(
                            "source_path"
                        )
                        variant_render, variant_scene = self._render_svg(
                            variant_page.svg_text,
                            variant_tracer,
                            variant_overrides,
                            source_path=variant_source_path,
                        )
                        variant_report = variant_tracer.report().to_dict()
                        variant_type = page_variant_type(variant_page)
                        variant_page_result = build_page_result(
                            variant_page,
                            variant_scene,
                            variant_report,
                            fallback_title=f"{page_result.title} ({variant_type})",
                            variant_type=variant_type,
                        )

                        stream.add_slide(variant_render)
                        slide_count += 1
                        del variant_render
                        page_results.append(variant_page_result)

            pptx_path = stream.finalize(output_path)

        packaging_report = packaging_tracer.report().to_dict()

        aggregate_trace = _merge_trace_reports(
            [result.trace_report for result in page_results] + [packaging_report]
        )

        return SvgToPptxMultiResult(
            pptx_path=pptx_path,
            slide_count=slide_count,
            page_results=page_results,
            packaging_report=packaging_report,
            aggregated_trace_report=aggregate_trace,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_svg(
        self,
        svg_text: str,
        tracer: ConversionTracer,
        policy_overrides: dict[str, dict[str, Any]] | None = None,
        *,
        source_path: str | None = None,
    ) -> tuple[DrawingMLRenderResult, IRScene]:
        """Convert SVG text into a rendered DrawingML payload."""

        if self._filter_strategy and tracer is not None:
            tracer.record_stage_event(
                stage="filter",
                action="strategy_configured",
                metadata={"strategy": self._filter_strategy},
            )

        parse_result = self._parser.parse(
            svg_text, tracer=tracer, source_path=source_path
        )
        if not parse_result.success or parse_result.svg_root is None:
            message = parse_result.error_message or "SVG parsing failed."
            raise SvgConversionError(message)

        # Use the parser's services which includes the StyleResolver with loaded CSS rules
        services_override = parse_result.services
        if services_override is None:
            services_override = configure_services(
                filter_strategy=self._filter_strategy
            )
        elif self._filter_strategy and services_override.filter_service is not None:
            services_override.filter_service.set_strategy(self._filter_strategy)

        if parse_result.width_px is not None:
            services_override.viewport_width = parse_result.width_px
        if parse_result.height_px is not None:
            services_override.viewport_height = parse_result.height_px

        animations = []
        timeline_scenes: list[AnimationScene] = []
        animation_summary: AnimationSummary | None = None
        animation_fallback_reasons: dict[str, int] = {}
        animation_policy_options: dict[str, Any] | None = None

        if parse_result.svg_root is not None:
            assign_missing_visibility_source_ids(parse_result.svg_root)
            animation_parser = self._animation_parser_factory()
            animations = animation_parser.parse_svg_animations(parse_result.svg_root)
            animation_summary = animation_parser.get_animation_summary()
            animation_fallback_reasons = animation_parser.get_degradation_reasons()
            if animations:
                timeline_scenes = self._timeline_sampler.generate_scenes(animations)
            animation_parser.reset_summary()

        # Inject geometry_mode into policy_overrides
        effective_overrides = deepcopy(policy_overrides) if policy_overrides else {}
        if (
            self._geometry_mode != "legacy"
        ):  # Only inject when not using legacy fallback
            geometry_overrides = effective_overrides.get("geometry", {})
            geometry_overrides["geometry_mode"] = self._geometry_mode
            effective_overrides["geometry"] = geometry_overrides

        policy_context = self._apply_policy_overrides(
            parse_result.policy_context, effective_overrides or None
        )
        if policy_context is not None:
            animation_policy_options = policy_context.get("animation")
        scene = convert_parser_output(
            parse_result,
            services=services_override,
            policy_engine=parse_result.policy_engine,
            policy_context=policy_context,
            overrides=effective_overrides or None,
            tracer=tracer,
        )
        if scene.metadata is None:
            scene.metadata = {}
        if animation_policy_options:
            policy_meta = scene.metadata.setdefault("policy", {})
            policy_meta["animation"] = dict(animation_policy_options)
        if animations:
            animations = _expand_deterministic_repeat_triggers(animations)
            animations = rewrite_visibility_animations(
                animations,
                scene,
                parse_result.svg_root,
            )
            animations = _lower_safe_group_transform_targets_with_animated_descendants(
                animations, scene
            )
            animations = _enrich_animations_with_element_centers(animations, scene)
            animations = _compose_sampled_center_motions(animations, scene)
            _materialize_simple_line_paths(scene, animations)
            animations = _compose_simple_line_endpoint_animations(animations, scene)
            animations = _materialize_stroked_polyline_groups(scene, animations)
            _apply_immediate_motion_starts(scene, animations)
            animations = _coalesce_simple_position_motions(animations, scene)
            _prepare_scene_for_native_opacity_effects(scene, animations)
            timeline_scenes = self._timeline_sampler.generate_scenes(animations)
            scene.animations = animations
            animation_meta = _build_animation_metadata(
                animations,
                timeline_scenes,
                animation_summary,
                animation_fallback_reasons,
                animation_policy_options,
            )
            raw_payload = {
                "definitions": animations,
                "timeline": timeline_scenes,
                "summary": animation_summary,
                "fallback_reasons": dict(animation_fallback_reasons),
            }
            if animation_policy_options:
                raw_payload["policy"] = dict(animation_policy_options)
            scene.metadata.setdefault("animation_raw", raw_payload)
            scene.metadata.setdefault("animation", animation_meta)
            if tracer is not None:
                tracer.record_stage_event(
                    stage="animation",
                    action="parsed",
                    metadata={
                        "animation_count": len(animations),
                        "timeline_frames": len(animation_meta.get("timeline", [])),
                        "duration": animation_meta["summary"]["duration"],
                        "has_motion_paths": animation_meta["summary"][
                            "has_motion_paths"
                        ],
                        "has_transforms": animation_meta["summary"]["has_transforms"],
                    },
                )
                for reason, count in sorted(animation_fallback_reasons.items()):
                    tracer.record_stage_event(
                        stage="animation",
                        action="parse_fallback",
                        metadata={"reason": reason, "count": count},
                    )

        animation_payload = (
            scene.metadata.get("animation_raw")
            if isinstance(scene.metadata, dict)
            else None
        )
        if hasattr(self._writer, "set_image_service"):
            self._writer.set_image_service(
                getattr(services_override, "image_service", None)
            )
        render_result = self._writer.render_scene_from_ir(
            scene,
            tracer=tracer,
            animation_payload=animation_payload,
        )
        return render_result, scene

    @staticmethod
    def _apply_policy_overrides(
        context: PolicyContext | None,
        overrides: dict[str, dict[str, Any]] | None,
    ) -> PolicyContext | None:
        if not overrides:
            return context

        base_selections: dict[str, dict[str, Any]] = {}
        if context is not None:
            for key, value in context.selections.items():
                base_selections[key] = dict(value)

        for target, values in overrides.items():
            merged = base_selections.get(target, {}).copy()
            merged.update(values)
            base_selections[target] = merged

        return PolicyContext(selections=base_selections)


__all__ = [
    "SvgConversionError",
    "SvgToPptxExporter",
    "SvgToPptxResult",
    "SvgToPptxMultiResult",
    "SvgPageSource",
    "SvgPageResult",
]
