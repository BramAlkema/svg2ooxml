"""High-level helpers that convert SVG snippets into PPTX packages."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from svg2ooxml.core.animation import SMILParser, TimelineSampler, TimelineSamplingConfig
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.core.parser import ParserConfig, SVGParser
from svg2ooxml.core.slide_orchestrator import (
    build_fidelity_tier_variants,
    derive_variants_from_trace,
    expand_page_with_variants,
)
from svg2ooxml.core.tracing import ConversionTracer
from svg2ooxml.drawingml.result import DrawingMLRenderResult
from svg2ooxml.drawingml.writer import DrawingMLWriter
from svg2ooxml.io.pptx_assembly import ALLOWED_SLIDE_SIZE_MODES, PPTXPackageBuilder
from svg2ooxml.ir import convert_parser_output
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationScene,
    AnimationSummary,
    AnimationTiming,
    AnimationType,
    CalcMode,
    TransformType,
)
from svg2ooxml.policy import PolicyContext
from svg2ooxml.services import configure_services


class SvgConversionError(RuntimeError):
    """Raised when the SVG to PPTX conversion fails."""


@dataclass(frozen=True)
class SvgToPptxResult:
    """Result describing the generated PPTX artifact."""

    pptx_path: Path
    slide_count: int
    trace_report: dict[str, Any] | None = None


@dataclass(frozen=True)
class SvgPageSource:
    """Input payload describing a single SVG slide."""

    svg_text: str
    title: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SvgPageResult:
    """Per-page conversion result."""

    title: str | None
    trace_report: dict[str, Any]
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class SvgToPptxMultiResult:
    """Result describing a multi-slide PPTX conversion."""

    pptx_path: Path
    slide_count: int
    page_results: list[SvgPageResult]
    packaging_report: dict[str, Any]
    aggregated_trace_report: dict[str, Any]


class SvgToPptxExporter:
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
            self._geometry_mode = os.environ.get("SVG2OOXML_GEOMETRY_MODE", "resvg-only")

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

        self._builder = builder or PPTXPackageBuilder(slide_size_mode=self._slide_size_mode)

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

        return SvgToPptxResult(pptx_path=pptx_path, slide_count=1, trace_report=report_dict)

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
            raise SvgConversionError("At least one SVG page is required for multi-slide conversion.")

        packaging_tracer = tracer or ConversionTracer()

        if parallel and not render_tiers and not split_fallback_variants:
            return self._convert_pages_parallel(
                pages, output_path, packaging_tracer, max_workers=max_workers,
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
                        variant_overrides = (variant_page.metadata or {}).get("policy_overrides")
                        variant_tracer = ConversionTracer()
                        variant_source_path = (variant_page.metadata or {}).get("source_path")
                        variant_render, variant_scene = self._render_svg(
                            variant_page.svg_text,
                            variant_tracer,
                            variant_overrides,
                            source_path=variant_source_path,
                        )
                        variant_report = variant_tracer.report().to_dict()

                        variant_title = (
                            variant_page.title
                            or (
                                variant_scene.metadata.get("page_title")
                                if isinstance(variant_scene.metadata, dict)
                                else None
                            )
                            or variant_page.name
                            or f"Slide {index}"
                        )

                        variant_metadata: dict[str, Any] | None = None
                        if isinstance(variant_scene.metadata, dict):
                            variant_scene.metadata.setdefault("page_title", variant_title)
                            variant_scene.metadata.setdefault("trace_report", variant_report)
                            variant_scene.metadata.setdefault("variant", {}).setdefault(
                                "type",
                                variant_page.metadata.get("variant", {}).get("type", "variant"),
                            )
                            variant_metadata = variant_scene.metadata

                        stream.add_slide(variant_render)
                        slide_count += 1
                        del variant_render
                        page_results.append(
                            SvgPageResult(
                                title=variant_title,
                                trace_report=variant_report,
                                metadata=variant_metadata,
                            )
                        )
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

                slide_title = (
                    page.title
                    or (scene.metadata.get("page_title") if isinstance(scene.metadata, dict) else None)
                    or page.name
                    or f"Slide {index}"
                )

                scene_metadata: dict[str, Any] | None = None
                if isinstance(scene.metadata, dict):
                    scene.metadata.setdefault("page_title", slide_title)
                    scene.metadata.setdefault("trace_report", report_dict)
                    if page.metadata:
                        scene.metadata.setdefault("page_metadata", {}).update(page.metadata)
                    scene.metadata.setdefault("variant", {}).setdefault("type", "base")
                    scene_metadata = scene.metadata

                stream.add_slide(render_result)
                slide_count += 1
                del render_result
                page_results.append(
                    SvgPageResult(
                        title=slide_title,
                        trace_report=report_dict,
                        metadata=scene_metadata,
                    )
                )

                if split_fallback_variants:
                    variants = derive_variants_from_trace(report_dict, enable_split=True)
                    variant_pages = expand_page_with_variants(page, variants)
                    for variant_page in variant_pages:
                        variant_overrides = (variant_page.metadata or {}).get("policy_overrides")
                        variant_tracer = ConversionTracer()
                        variant_source_path = (variant_page.metadata or {}).get("source_path")
                        variant_render, variant_scene = self._render_svg(
                            variant_page.svg_text,
                            variant_tracer,
                            variant_overrides,
                            source_path=variant_source_path,
                        )
                        variant_report = variant_tracer.report().to_dict()

                        variant_title = (
                            variant_page.title
                            or (variant_scene.metadata.get("page_title") if isinstance(variant_scene.metadata, dict) else None)
                            or variant_page.name
                            or f"{slide_title} ({variant_page.metadata.get('variant', {}).get('type', 'variant')})"
                        )

                        variant_metadata: dict[str, Any] | None = None
                        if isinstance(variant_scene.metadata, dict):
                            variant_scene.metadata.setdefault("page_title", variant_title)
                            variant_scene.metadata.setdefault("trace_report", variant_report)
                            variant_scene.metadata.setdefault("variant", {}).setdefault(
                                "type",
                                variant_page.metadata.get("variant", {}).get("type", "variant"),
                            )
                            variant_metadata = variant_scene.metadata

                        stream.add_slide(variant_render)
                        slide_count += 1
                        del variant_render
                        page_results.append(
                            SvgPageResult(
                                title=variant_title,
                                trace_report=variant_report,
                                metadata=variant_metadata,
                            )
                        )

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

        parse_result = self._parser.parse(svg_text, tracer=tracer, source_path=source_path)
        if not parse_result.success or parse_result.svg_root is None:
            message = parse_result.error_message or "SVG parsing failed."
            raise SvgConversionError(message)

        # Use the parser's services which includes the StyleResolver with loaded CSS rules
        services_override = parse_result.services
        if services_override is None:
            services_override = configure_services(filter_strategy=self._filter_strategy)
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
            animation_parser = self._animation_parser_factory()
            animations = animation_parser.parse_svg_animations(parse_result.svg_root)
            animation_summary = animation_parser.get_animation_summary()
            animation_fallback_reasons = animation_parser.get_degradation_reasons()
            if animations:
                timeline_scenes = self._timeline_sampler.generate_scenes(animations)
            animation_parser.reset_summary()

        # Inject geometry_mode into policy_overrides
        effective_overrides = deepcopy(policy_overrides) if policy_overrides else {}
        if self._geometry_mode != "legacy":  # Only inject when not using legacy fallback
            geometry_overrides = effective_overrides.get("geometry", {})
            geometry_overrides["geometry_mode"] = self._geometry_mode
            effective_overrides["geometry"] = geometry_overrides

        policy_context = self._apply_policy_overrides(parse_result.policy_context, effective_overrides or None)
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
            animations = _enrich_animations_with_element_centers(animations, scene)
            animations = _compose_sampled_center_motions(animations, scene)
            _materialize_simple_line_paths(scene, animations)
            animations = _compose_simple_line_endpoint_animations(animations, scene)
            animations = _materialize_stroked_polyline_groups(scene, animations)
            _apply_immediate_motion_starts(scene, animations)
            animations = _coalesce_simple_position_motions(animations, scene)
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
                        "has_motion_paths": animation_meta["summary"]["has_motion_paths"],
                        "has_transforms": animation_meta["summary"]["has_transforms"],
                    },
                )
                for reason, count in sorted(animation_fallback_reasons.items()):
                    tracer.record_stage_event(
                        stage="animation",
                        action="parse_fallback",
                        metadata={"reason": reason, "count": count},
                    )

        animation_payload = scene.metadata.get("animation_raw") if isinstance(scene.metadata, dict) else None
        if hasattr(self._writer, "set_image_service"):
            self._writer.set_image_service(getattr(services_override, "image_service", None))
        render_result = self._writer.render_scene_from_ir(
            scene,
            tracer=tracer,
            animation_payload=animation_payload,
        )
        return render_result, scene

    def _convert_pages_parallel(
        self,
        pages: Sequence[SvgPageSource],
        output_path: Path,
        packaging_tracer: ConversionTracer,
        *,
        max_workers: int | None = None,
    ) -> SvgToPptxMultiResult:
        """Render pages in parallel, then package sequentially."""
        import os
        from concurrent.futures import ThreadPoolExecutor

        workers = max_workers or min(len(pages), os.cpu_count() or 1)

        futures: list[tuple[SvgPageSource, Any]] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for page in pages:
                overrides = (page.metadata or {}).get("policy_overrides")
                source_path = (page.metadata or {}).get("source_path")
                fut = pool.submit(
                    SvgToPptxExporter._render_page_isolated,
                    page.svg_text,
                    filter_strategy=self._filter_strategy,
                    geometry_mode=self._geometry_mode,
                    policy_overrides=overrides,
                    source_path=source_path,
                )
                futures.append((page, fut))

        page_results: list[SvgPageResult] = []
        slide_count = 0

        with self._builder.begin_streaming(tracer=packaging_tracer) as stream:
            for index, (page, fut) in enumerate(futures, start=1):
                render_result, scene, report_dict = fut.result()

                slide_title = (
                    page.title
                    or (scene.metadata.get("page_title") if isinstance(scene.metadata, dict) else None)
                    or page.name
                    or f"Slide {index}"
                )

                scene_metadata: dict[str, Any] | None = None
                if isinstance(scene.metadata, dict):
                    scene.metadata.setdefault("page_title", slide_title)
                    scene.metadata.setdefault("trace_report", report_dict)
                    if page.metadata:
                        scene.metadata.setdefault("page_metadata", {}).update(page.metadata)
                    scene.metadata.setdefault("variant", {}).setdefault("type", "base")
                    scene_metadata = scene.metadata

                stream.add_slide(render_result)
                slide_count += 1
                del render_result
                page_results.append(
                    SvgPageResult(
                        title=slide_title,
                        trace_report=report_dict,
                        metadata=scene_metadata,
                    )
                )

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

    @staticmethod
    def _render_page_isolated(
        svg_text: str,
        *,
        filter_strategy: str | None,
        geometry_mode: str,
        policy_overrides: dict[str, dict[str, Any]] | None = None,
        source_path: str | None = None,
    ) -> tuple[DrawingMLRenderResult, IRScene, dict[str, Any]]:
        """Thread-safe single-page render with fresh pipeline instances."""
        exporter = SvgToPptxExporter(
            filter_strategy=filter_strategy,
            geometry_mode=geometry_mode,
        )
        tracer = ConversionTracer()
        render_result, scene = exporter._render_svg(
            svg_text, tracer, policy_overrides, source_path=source_path,
        )
        return render_result, scene, tracer.report().to_dict()

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


def _merge_trace_reports(reports: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple trace report dictionaries into a single aggregate report."""

    geometry_totals: Counter[str] = Counter()
    paint_totals: Counter[str] = Counter()
    stage_totals: Counter[str] = Counter()
    resvg_metrics: Counter[str] = Counter()
    geometry_events: list[Any] = []
    paint_events: list[Any] = []
    stage_events: list[Any] = []

    for report in reports:
        if not report:
            continue
        geometry_totals.update(report.get("geometry_totals", {}))
        paint_totals.update(report.get("paint_totals", {}))
        stage_totals.update(report.get("stage_totals", {}))
        resvg_metrics.update(report.get("resvg_metrics", {}))
        geometry_events.extend(report.get("geometry_events", []))
        paint_events.extend(report.get("paint_events", []))
        stage_events.extend(report.get("stage_events", []))

    return {
        "geometry_totals": dict(geometry_totals),
        "paint_totals": dict(paint_totals),
        "stage_totals": dict(stage_totals),
        "resvg_metrics": dict(resvg_metrics),
        "geometry_events": geometry_events,
        "paint_events": paint_events,
        "stage_events": stage_events,
    }


def _build_animation_metadata(
    animations: list[AnimationDefinition],
    timeline_scenes: list[AnimationScene],
    summary: AnimationSummary | None,
    fallback_reasons: Mapping[str, int] | None,
    policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    summary_dict = _serialize_animation_summary(summary, fallback_reasons=fallback_reasons)
    timeline_payload = [_serialize_timeline_scene(scene) for scene in timeline_scenes]
    payload = {
        "definition_count": len(animations),
        "definitions": [_serialize_animation_definition(defn) for defn in animations],
        "timeline": timeline_payload,
        "summary": summary_dict,
    }
    if policy:
        payload["policy"] = dict(policy)
    return payload


def _serialize_animation_definition(definition: AnimationDefinition) -> dict[str, Any]:
    return {
        "element_id": definition.element_id,
        "animation_type": definition.animation_type.value,
        "target_attribute": definition.target_attribute,
        "values": list(definition.values),
        "timing": _serialize_animation_timing(definition.timing),
        "key_times": list(definition.key_times) if definition.key_times else None,
        "key_splines": [list(spline) for spline in definition.key_splines] if definition.key_splines else None,
        "calc_mode": definition.calc_mode.value if isinstance(definition.calc_mode, CalcMode) else definition.calc_mode,
        "transform_type": definition.transform_type.value if definition.transform_type else None,
        "additive": definition.additive,
        "accumulate": definition.accumulate,
        "element_heading_deg": definition.element_heading_deg,
        "motion_space_matrix": list(definition.motion_space_matrix) if definition.motion_space_matrix else None,
        "element_motion_offset_px": list(definition.element_motion_offset_px) if definition.element_motion_offset_px else None,
        "motion_viewport_px": list(definition.motion_viewport_px) if definition.motion_viewport_px else None,
    }


def _serialize_animation_timing(timing: AnimationTiming) -> dict[str, Any]:
    return {
        "begin": timing.begin,
        "duration": timing.duration,
        "repeat_count": timing.repeat_count,
        "fill_mode": timing.fill_mode.value,
    }


def _serialize_animation_summary(
    summary: AnimationSummary | None,
    *,
    fallback_reasons: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    if summary is None:
        return {
            "total_animations": 0,
            "complexity": "simple",
            "duration": 0.0,
            "has_transforms": False,
            "has_motion_paths": False,
            "has_color_animations": False,
            "has_easing": False,
            "has_sequences": False,
            "element_count": 0,
            "warnings": [],
            "fallback_reasons": {},
        }

    return {
        "total_animations": summary.total_animations,
        "complexity": summary.complexity.value,
        "duration": summary.duration,
        "has_transforms": summary.has_transforms,
        "has_motion_paths": summary.has_motion_paths,
        "has_color_animations": summary.has_color_animations,
        "has_easing": summary.has_easing,
        "has_sequences": summary.has_sequences,
        "element_count": summary.element_count,
        "warnings": list(summary.warnings),
        "fallback_reasons": dict(fallback_reasons or {}),
    }


def _serialize_timeline_scene(scene: AnimationScene) -> dict[str, Any]:
    return {
        "time": scene.time,
        "element_states": {element_id: dict(properties) for element_id, properties in scene.element_states.items()},
    }


def _enrich_animations_with_element_centers(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Populate geometry-derived animation metadata from scene graph bounds.

    This is needed so the rotate handler can compute orbital motion paths when
    the SVG rotation center (cx, cy) differs from the shape center, and so
    motion paths can be shifted into the absolute ``ppt_x``/``ppt_y`` space
    that PowerPoint stores in ``<p:animMotion path="...">``.
    """
    from dataclasses import replace as _replace

    from svg2ooxml.ir.animation import TransformType
    from svg2ooxml.ir.scene import Group
    from svg2ooxml.ir.text import TextFrame

    bbox_map: dict[str, tuple[float, float, float, float]] = {}
    center_map: dict[str, tuple[float, float]] = {}
    heading_map: dict[str, float] = {}
    text_origin_map: dict[str, tuple[float, float]] = {}

    def _walk(elements: list) -> None:
        for el in elements:
            meta = getattr(el, "metadata", None)
            bbox = getattr(el, "bbox", None)
            if isinstance(meta, dict):
                for eid in meta.get("element_ids", []):
                    if not isinstance(eid, str) or bbox is None:
                        continue
                    bbox_map.setdefault(
                        eid,
                        (bbox.x, bbox.y, bbox.width, bbox.height),
                    )
                    center_map.setdefault(
                        eid,
                        (bbox.x + bbox.width / 2.0, bbox.y + bbox.height / 2.0),
                    )
                    heading = _infer_element_heading_deg(el)
                    if heading is not None:
                        heading_map.setdefault(eid, heading)
                    if isinstance(el, TextFrame):
                        text_origin_map.setdefault(
                            eid,
                            (el.origin.x, el.origin.y),
                        )
            if isinstance(el, Group):
                _walk(getattr(el, "children", []))

    _walk(scene.elements)

    enriched = []
    viewport_size = None
    if getattr(scene, "width_px", None) and getattr(scene, "height_px", None):
        viewport_size = (float(scene.width_px), float(scene.height_px))
    for anim in animations:
        if (
            anim.transform_type in {TransformType.ROTATE, TransformType.SCALE}
            and anim.element_center_px is None
            and anim.element_id in center_map
        ):
            anim = _replace(anim, element_center_px=center_map[anim.element_id])
        if anim.element_heading_deg is None and anim.element_id in heading_map:
            anim = _replace(anim, element_heading_deg=heading_map[anim.element_id])
        if (
            anim.animation_type == AnimationType.ANIMATE_MOTION
            and anim.element_motion_offset_px is None
            and anim.element_id in bbox_map
        ):
            bbox_x, bbox_y, _, _ = bbox_map[anim.element_id]
            if anim.element_id in text_origin_map:
                origin_x, origin_y = text_origin_map[anim.element_id]
            elif anim.motion_space_matrix is not None:
                origin_x = anim.motion_space_matrix[4]
                origin_y = anim.motion_space_matrix[5]
            else:
                origin_x = 0.0
                origin_y = 0.0
            anim = _replace(
                anim,
                element_motion_offset_px=(bbox_x - origin_x, bbox_y - origin_y),
            )
        if anim.motion_viewport_px is None and viewport_size is not None:
            anim = _replace(anim, motion_viewport_px=viewport_size)
        enriched.append(anim)
    return enriched


def _materialize_simple_line_paths(
    scene: IRScene,
    animations: Sequence[AnimationDefinition],
) -> None:
    """Convert simple animated single-segment paths back into line IR."""

    from dataclasses import replace as _replace

    from svg2ooxml.ir.geometry import LineSegment
    from svg2ooxml.ir.scene import Group
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Line

    endpoint_target_ids = {
        animation.element_id
        for animation in animations
        if _is_simple_line_endpoint_animation(animation)
        and isinstance(animation.element_id, str)
    }
    if not endpoint_target_ids:
        return

    def _rewrite(element: Any):
        if isinstance(element, Group):
            return _replace(
                element,
                children=[_rewrite(child) for child in element.children],
            )
        if not isinstance(element, IRPath):
            return element
        if element.fill is not None or element.clip or element.mask or element.mask_instance:
            return element
        line_segments = [
            segment for segment in element.segments if isinstance(segment, LineSegment)
        ]
        if len(line_segments) != 1 or len(line_segments) != len(element.segments):
            return element
        metadata = getattr(element, "metadata", None)
        element_ids = metadata.get("element_ids", []) if isinstance(metadata, dict) else []
        if not any(
            isinstance(element_id, str) and element_id in endpoint_target_ids
            for element_id in element_ids
        ):
            return element
        segment = line_segments[0]
        return Line(
            start=segment.start,
            end=segment.end,
            stroke=element.stroke,
            opacity=element.opacity,
            effects=list(getattr(element, "effects", [])),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

    scene.elements = [_rewrite(element) for element in scene.elements]


def _materialize_stroked_polyline_groups(
    scene: IRScene,
    animations: list[AnimationDefinition],
) -> list[AnimationDefinition]:
    """Decompose stroked open paths into independently animated line segments."""

    from dataclasses import replace as _replace

    from svg2ooxml.ir.geometry import LineSegment
    from svg2ooxml.ir.scene import Group
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Line

    stroke_target_ids = {
        animation.element_id
        for animation in animations
        if (
            animation.animation_type == AnimationType.ANIMATE
            and animation.transform_type is None
            and animation.target_attribute == "stroke-width"
            and isinstance(animation.element_id, str)
        )
    }
    if not stroke_target_ids:
        return animations

    @dataclass(frozen=True)
    class _PolylineSegments:
        parent_center: tuple[float, float]
        segment_ids: list[str]
        segment_centers: list[tuple[float, float]]

    segment_map: dict[str, _PolylineSegments] = {}
    animations_by_target: dict[str, list[AnimationDefinition]] = {}
    for animation in animations:
        if isinstance(animation.element_id, str):
            animations_by_target.setdefault(animation.element_id, []).append(animation)

    def _is_supported_polyline_animation(animation: AnimationDefinition) -> bool:
        if (
            animation.animation_type == AnimationType.ANIMATE
            and animation.transform_type is None
            and animation.target_attribute == "stroke-width"
        ):
            return True
        if _is_polyline_segment_fade_animation(animation):
            return True
        if _is_simple_origin_rotate_animation(animation):
            return True
        if _is_simple_motion_sampling_candidate(animation):
            return True
        return False

    def _rewrite(element: Any):
        if isinstance(element, Group):
            return _replace(
                element,
                children=[_rewrite(child) for child in element.children],
            )
        if not isinstance(element, IRPath):
            return element
        if (
            element.fill is not None
            or element.clip
            or element.mask
            or element.mask_instance
            or getattr(element, "effects", None)
            or abs(float(getattr(element, "opacity", 1.0)) - 1.0) > 1e-6
        ):
            return element
        line_segments = [
            segment for segment in element.segments if isinstance(segment, LineSegment)
        ]
        if len(line_segments) < 2 or len(line_segments) != len(element.segments):
            return element
        metadata = getattr(element, "metadata", None)
        if not isinstance(metadata, dict):
            return element
        element_ids = [
            element_id
            for element_id in metadata.get("element_ids", [])
            if isinstance(element_id, str)
        ]
        target_ids = [element_id for element_id in element_ids if element_id in stroke_target_ids]
        if not target_ids:
            return element
        if any(
            not _is_supported_polyline_animation(animation)
            for element_id in element_ids
            for animation in animations_by_target.get(element_id, [])
        ):
            return element

        base_id = next(
            (element_id for element_id in element_ids if not element_id.startswith("anim-target-")),
            target_ids[0],
        )
        segment_ids: list[str] = []
        segment_centers: list[tuple[float, float]] = []
        segment_children: list[Any] = []
        for index, segment in enumerate(line_segments):
            segment_id = f"{base_id}__seg{index}"
            segment_ids.append(segment_id)
            segment_centers.append(
                (
                    (float(segment.start.x) + float(segment.end.x)) / 2.0,
                    (float(segment.start.y) + float(segment.end.y)) / 2.0,
                )
            )
            child_metadata = dict(metadata)
            child_metadata["element_ids"] = [segment_id]
            segment_children.append(
                Line(
                    start=segment.start,
                    end=segment.end,
                    stroke=element.stroke,
                    opacity=1.0,
                    effects=[],
                    metadata=child_metadata,
                )
            )
        polyline_segments = _PolylineSegments(
            parent_center=(
                float(element.bbox.x + element.bbox.width / 2.0),
                float(element.bbox.y + element.bbox.height / 2.0),
            ),
            segment_ids=list(segment_ids),
            segment_centers=segment_centers,
        )
        for element_id in element_ids:
            segment_map[element_id] = polyline_segments

        return Group(children=segment_children)

    scene.elements = [_rewrite(element) for element in scene.elements]
    if not segment_map:
        return animations

    rewritten: list[AnimationDefinition] = []
    for animation in animations:
        segment_info = segment_map.get(animation.element_id)
        if segment_info is None:
            rewritten.append(animation)
            continue
        segment_ids = segment_info.segment_ids
        if (
            animation.animation_type == AnimationType.ANIMATE
            and animation.transform_type is None
            and animation.target_attribute == "stroke-width"
        ):
            rewritten.extend(
                _replace(animation, element_id=segment_id)
                for segment_id in segment_ids
            )
            continue
        if _is_polyline_segment_fade_animation(animation):
            rewritten.extend(
                _replace(animation, element_id=segment_id)
                for segment_id in segment_ids
            )
            continue
        if _is_simple_origin_rotate_animation(animation):
            rewritten.extend(
                _replace(animation, element_id=segment_id)
                for segment_id in segment_ids
            )
            continue
        if _is_simple_motion_sampling_candidate(animation):
            motion_points = _parse_sampled_motion_points(animation.values[0])
            if len(motion_points) < 2:
                rewritten.append(animation)
                continue
            rotate_member = next(
                (
                    candidate
                    for candidate in animations_by_target.get(animation.element_id, [])
                    if _is_simple_origin_rotate_animation(candidate)
                ),
                None,
            )
            if rotate_member is None:
                rewritten.extend(
                    _replace(animation, element_id=segment_id)
                    for segment_id in segment_ids
                )
                continue
            start_angle, end_angle = _parse_rotate_bounds(rotate_member)
            for segment_id, segment_center in zip(
                segment_ids,
                segment_info.segment_centers,
                strict=False,
            ):
                offset = (
                    segment_center[0] - segment_info.parent_center[0],
                    segment_center[1] - segment_info.parent_center[1],
                )
                child_center_points: list[tuple[float, float]] = []
                for progress in _sample_progress_values():
                    motion_point = _sample_polyline_at_fraction(motion_points, progress)
                    angle = _lerp(start_angle, end_angle, progress)
                    rotated_offset = _rotate_point(offset, angle)
                    child_center_points.append(
                        (
                            segment_info.parent_center[0]
                            + motion_point[0]
                            + rotated_offset[0],
                            segment_info.parent_center[1]
                            + motion_point[1]
                            + rotated_offset[1],
                        )
                    )
                rewritten.append(
                    _replace(
                        _build_sampled_motion_replacement(
                            template=animation,
                            points=child_center_points,
                        ),
                        element_id=segment_id,
                    )
                )
            continue
        rewritten.append(animation)
    return rewritten


def _compose_simple_line_endpoint_animations(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Compose simple line endpoint changes into motion + scale fragments.

    Endpoint animations such as ``x1`` on a cloned line are geometry-local, not
    whole-shape translation. For simple line geometry, we can still approximate
    the authored SVG behavior by:

    1. translating the line center by the averaged endpoint delta
    2. scaling the line's local width/height around its center

    This prevents invalid native output such as treating ``x1`` and outer
    ``<use x>`` as duplicate full-shape motions.
    """
    from dataclasses import replace as _replace

    from svg2ooxml.ir.animation import TransformType
    from svg2ooxml.ir.geometry import LineSegment
    from svg2ooxml.ir.scene import Group
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Line

    alias_map: dict[str, tuple[str, ...]] = {}
    line_points_map: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}

    def _resolve_line_points(
        element: object,
    ) -> tuple[tuple[float, float], tuple[float, float]] | None:
        if isinstance(element, Line):
            return (
                (float(element.start.x), float(element.start.y)),
                (float(element.end.x), float(element.end.y)),
            )

        if isinstance(element, IRPath):
            line_segments = [
                segment
                for segment in element.segments
                if isinstance(segment, LineSegment)
            ]
            if len(line_segments) != 1:
                return None
            segment = line_segments[0]
            return (
                (float(segment.start.x), float(segment.start.y)),
                (float(segment.end.x), float(segment.end.y)),
            )

        return None

    def _walk(elements: list) -> None:
        for el in elements:
            meta = getattr(el, "metadata", None)
            if isinstance(meta, dict):
                element_ids = tuple(
                    dict.fromkeys(
                        eid
                        for eid in meta.get("element_ids", [])
                        if isinstance(eid, str) and eid
                    )
                )
                if element_ids:
                    for element_id in element_ids:
                        alias_map[element_id] = element_ids
                    line_points = _resolve_line_points(el)
                    if line_points is not None:
                        for element_id in element_ids:
                            line_points_map[element_id] = line_points
            if isinstance(el, Group):
                _walk(getattr(el, "children", []))

    _walk(scene.elements)

    group_map: dict[tuple[Any, ...], list[tuple[int, str, AnimationDefinition]]] = {}
    for index, animation in enumerate(animations):
        if animation.animation_type != AnimationType.ANIMATE:
            continue
        if animation.transform_type is not None:
            continue
        attr = animation.target_attribute
        if attr in {"x1", "x2", "y1", "y2"}:
            if not _is_simple_line_endpoint_animation(animation):
                continue
        elif _simple_position_axis(animation) is None:
            continue
        group_key = _animation_group_key(animation, alias_map)
        group_map.setdefault(group_key, []).append((index, attr, animation))

    replacements: dict[int, tuple[list[AnimationDefinition], set[int]]] = {}
    for members in group_map.values():
        endpoint_members = [
            member for member in members if member[1] in {"x1", "x2", "y1", "y2"}
        ]
        if not endpoint_members:
            continue

        base_animation = min(members, key=lambda member: member[0])[2]
        line_points = line_points_map.get(base_animation.element_id)
        if line_points is None:
            continue

        attr_to_member: dict[str, tuple[int, AnimationDefinition]] = {}
        duplicate_attr = False
        for index, attr, animation in endpoint_members:
            if attr in attr_to_member:
                duplicate_attr = True
                break
            attr_to_member[attr] = (index, animation)
        if duplicate_attr:
            continue

        x_members = [member for member in members if _simple_position_axis(member[2]) == "x"]
        y_members = [member for member in members if _simple_position_axis(member[2]) == "y"]
        if len(x_members) > 1 or len(y_members) > 1:
            continue

        def _delta_for(
            attr_name: str,
            _members: dict[str, tuple[int, AnimationDefinition]] = attr_to_member,
        ) -> float:
            member = _members.get(attr_name)
            if member is None:
                return 0.0
            try:
                return float(member[1].values[-1]) - float(member[1].values[0])
            except (TypeError, ValueError):
                raise ValueError(attr_name) from None

        try:
            dx1 = _delta_for("x1")
            dx2 = _delta_for("x2")
            dy1 = _delta_for("y1")
            dy2 = _delta_for("y2")
        except ValueError:
            continue

        try:
            world_dx = (
                float(x_members[0][2].values[-1]) - float(x_members[0][2].values[0])
                if x_members
                else 0.0
            )
            world_dy = (
                float(y_members[0][2].values[-1]) - float(y_members[0][2].values[0])
                if y_members
                else 0.0
            )
        except (TypeError, ValueError):
            continue

        (x1_start, y1_start), (x2_start, y2_start) = line_points
        x1_end = x1_start + dx1
        y1_end = y1_start + dy1
        x2_end = x2_start + dx2
        y2_end = y2_start + dy2

        start_width = abs(x1_start - x2_start)
        start_height = abs(y1_start - y2_start)
        end_width = abs(x1_end - x2_end)
        end_height = abs(y1_end - y2_end)

        start_dx_sign = x1_start - x2_start
        end_dx_sign = x1_end - x2_end
        start_dy_sign = y1_start - y2_start
        end_dy_sign = y1_end - y2_end
        if (
            abs(start_dx_sign) > 1e-6
            and abs(end_dx_sign) > 1e-6
            and start_dx_sign * end_dx_sign < 0
        ) or (
            abs(start_dy_sign) > 1e-6
            and abs(end_dy_sign) > 1e-6
            and start_dy_sign * end_dy_sign < 0
        ):
            continue
        if (start_width <= 1e-6 and end_width > 1e-6) or (
            start_height <= 1e-6 and end_height > 1e-6
        ):
            continue

        scale_x = end_width / start_width if start_width > 1e-6 else 1.0
        scale_y = end_height / start_height if start_height > 1e-6 else 1.0

        local_dx = (dx1 + dx2) / 2.0
        local_dy = (dy1 + dy2) / 2.0
        total_dx = world_dx + local_dx
        total_dy = world_dy + local_dy
        matrix_source = (
            x_members[0][2]
            if x_members
            else (y_members[0][2] if y_members else base_animation)
        )
        total_dx, total_dy = _project_linear_motion_delta(
            total_dx,
            total_dy,
            matrix_source,
        )

        if (
            abs(total_dx) <= 1e-6
            and abs(total_dy) <= 1e-6
            and abs(scale_x - 1.0) <= 1e-6
            and abs(scale_y - 1.0) <= 1e-6
        ):
            continue

        consumed = {member[0] for member in endpoint_members}
        if x_members:
            consumed.add(x_members[0][0])
        if y_members:
            consumed.add(y_members[0][0])

        viewport = base_animation.motion_viewport_px
        if viewport is None and x_members:
            viewport = x_members[0][2].motion_viewport_px
        if viewport is None and y_members:
            viewport = y_members[0][2].motion_viewport_px

        replacement_group: list[AnimationDefinition] = []
        if abs(total_dx) > 1e-6 or abs(total_dy) > 1e-6:
            path = (
                f"M 0 0 L {_format_motion_delta(total_dx)} "
                f"{_format_motion_delta(total_dy)} E"
            )
            replacement_group.append(
                _replace(
                    base_animation,
                    animation_type=AnimationType.ANIMATE_MOTION,
                    target_attribute="position",
                    values=[path],
                    key_times=None,
                    key_splines=None,
                    calc_mode=CalcMode.LINEAR,
                    transform_type=None,
                    additive="replace",
                    accumulate="none",
                    motion_rotate=None,
                    element_motion_offset_px=None,
                    motion_space_matrix=None,
                    motion_viewport_px=viewport,
                )
            )

        if abs(scale_x - 1.0) > 1e-6 or abs(scale_y - 1.0) > 1e-6:
            replacement_group.append(
                _replace(
                    base_animation,
                    animation_type=AnimationType.ANIMATE_TRANSFORM,
                    target_attribute="transform",
                    values=["1 1", f"{scale_x:.6g} {scale_y:.6g}"],
                    key_times=None,
                    key_splines=None,
                    calc_mode=CalcMode.LINEAR,
                    transform_type=TransformType.SCALE,
                    additive="replace",
                    accumulate="none",
                    motion_rotate=None,
                    element_motion_offset_px=None,
                    motion_space_matrix=None,
                    motion_viewport_px=viewport,
                )
            )

        if not replacement_group:
            continue

        first_index = min(consumed)
        replacements[first_index] = (replacement_group, consumed)

    composed: list[AnimationDefinition] = []
    consumed: set[int] = set()
    for index, animation in enumerate(animations):
        if index in consumed:
            continue
        replacement = replacements.get(index)
        if replacement is not None:
            composed.extend(replacement[0])
            consumed.update(replacement[1])
            continue
        composed.append(animation)
    return composed


def _animation_group_key(
    animation: AnimationDefinition,
    alias_map: dict[str, tuple[str, ...]],
) -> tuple[Any, ...]:
    timing = animation.timing
    begin_triggers = tuple(
        (
            getattr(getattr(trigger, "trigger_type", None), "value", None),
            float(getattr(trigger, "delay_seconds", 0.0)),
            getattr(trigger, "target_element_id", None),
        )
        for trigger in (timing.begin_triggers or [])
    )
    return (
        alias_map.get(animation.element_id, (animation.element_id,)),
        round(float(timing.begin), 6),
        round(float(timing.duration), 6),
        str(timing.repeat_count),
        timing.fill_mode.value,
        animation.additive,
        animation.accumulate,
        animation.calc_mode.value
        if isinstance(animation.calc_mode, CalcMode)
        else str(animation.calc_mode),
        begin_triggers,
    )


def _sampled_motion_group_key(
    animation: AnimationDefinition,
    alias_map: dict[str, tuple[str, ...]],
) -> tuple[Any, ...]:
    timing = animation.timing
    begin_triggers = tuple(
        (
            getattr(getattr(trigger, "trigger_type", None), "value", None),
            float(getattr(trigger, "delay_seconds", 0.0)),
            getattr(trigger, "target_element_id", None),
        )
        for trigger in (timing.begin_triggers or [])
    )
    return (
        alias_map.get(animation.element_id, (animation.element_id,)),
        round(float(timing.begin), 6),
        round(float(timing.duration), 6),
        str(timing.repeat_count),
        timing.fill_mode.value,
        begin_triggers,
    )


def _coalesce_simple_position_motions(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Merge simple x/y animations into one motion path per rendered shape.

    PowerPoint does not reliably compose concurrent one-axis ``animMotion``
    effects on the same target shape. When SVG expresses independent x/y
    animations that land on one rendered shape, collapse them into a single
    diagonal motion path before emitting timing XML.
    """
    from dataclasses import replace as _replace

    from svg2ooxml.ir.scene import Group

    alias_map: dict[str, tuple[str, ...]] = {}

    def _walk(elements: list) -> None:
        for el in elements:
            meta = getattr(el, "metadata", None)
            if isinstance(meta, dict):
                element_ids = tuple(
                    dict.fromkeys(
                        eid
                        for eid in meta.get("element_ids", [])
                        if isinstance(eid, str) and eid
                    )
                )
                if element_ids:
                    for element_id in element_ids:
                        alias_map[element_id] = element_ids
            if isinstance(el, Group):
                _walk(getattr(el, "children", []))

    _walk(scene.elements)

    group_map: dict[tuple[Any, ...], list[tuple[int, str, AnimationDefinition]]] = {}
    for index, animation in enumerate(animations):
        axis = _simple_position_axis(animation)
        if axis is None:
            continue

        group_key = _animation_group_key(animation, alias_map)
        group_map.setdefault(group_key, []).append((index, axis, animation))

    replacements: dict[int, tuple[AnimationDefinition, set[int]]] = {}
    for members in group_map.values():
        x_members = [member for member in members if member[1] == "x"]
        y_members = [member for member in members if member[1] == "y"]
        if len(x_members) != 1 or len(y_members) != 1:
            continue

        first_index = min(x_members[0][0], y_members[0][0])
        base_animation = animations[first_index]
        x_animation = x_members[0][2]
        y_animation = y_members[0][2]

        try:
            dx = float(x_animation.values[-1]) - float(x_animation.values[0])
            dy = float(y_animation.values[-1]) - float(y_animation.values[0])
        except (TypeError, ValueError):
            continue
        dx, dy = _project_linear_motion_delta(dx, dy, base_animation)

        path = (
            f"M 0 0 L {_format_motion_delta(dx)} "
            f"{_format_motion_delta(dy)} E"
        )
        replacement = _replace(
            base_animation,
            animation_type=AnimationType.ANIMATE_MOTION,
            target_attribute="position",
            values=[path],
            key_times=None,
            key_splines=None,
            calc_mode=CalcMode.LINEAR,
            transform_type=None,
            motion_rotate=None,
            element_motion_offset_px=None,
            motion_space_matrix=None,
            motion_viewport_px=(
                base_animation.motion_viewport_px
                or x_animation.motion_viewport_px
                or y_animation.motion_viewport_px
            ),
        )
        replacements[first_index] = (
            replacement,
            {x_members[0][0], y_members[0][0]},
        )

    coalesced: list[AnimationDefinition] = []
    consumed: set[int] = set()
    for index, animation in enumerate(animations):
        if index in consumed:
            continue
        replacement = replacements.get(index)
        if replacement is not None:
            coalesced.append(replacement[0])
            consumed.update(replacement[1])
            continue
        coalesced.append(animation)
    return coalesced


@dataclass(frozen=True)
class _SampledCenterMotionComposition:
    replacement_index: int
    consumed_indices: set[int]
    replacement_animation: AnimationDefinition
    updated_indices: dict[int, AnimationDefinition]
    start_center: tuple[float, float]
    element_id: str


def _compose_sampled_center_motions(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Compose known stacked transform/motion cases into sampled center paths.

    Some SVG stacks change the shape center in ways PowerPoint cannot infer by
    simply combining independent native effects. For those cases we:

    1. move the base IR element to the authored SVG start center
    2. replace the position-changing fragments with one sampled motion path
    3. keep the editable scale/rotate effect, but suppress its naive companion
       motion because the composed path already includes that center movement
    """
    from svg2ooxml.ir.scene import Group

    alias_map: dict[str, tuple[str, ...]] = {}
    element_map: dict[str, object] = {}
    center_map: dict[str, tuple[float, float]] = {}

    def _walk(elements: list) -> None:
        for el in elements:
            meta = getattr(el, "metadata", None)
            bbox = getattr(el, "bbox", None)
            if isinstance(meta, dict) and bbox is not None:
                element_ids = tuple(
                    dict.fromkeys(
                        eid
                        for eid in meta.get("element_ids", [])
                        if isinstance(eid, str) and eid
                    )
                )
                if element_ids:
                    center = (
                        float(bbox.x + bbox.width / 2.0),
                        float(bbox.y + bbox.height / 2.0),
                    )
                    for element_id in element_ids:
                        alias_map[element_id] = element_ids
                        element_map.setdefault(element_id, el)
                        center_map.setdefault(element_id, center)
            if isinstance(el, Group):
                _walk(getattr(el, "children", []))

    _walk(scene.elements)

    group_map: dict[tuple[Any, ...], list[tuple[int, AnimationDefinition]]] = {}
    for index, animation in enumerate(animations):
        group_key = _sampled_motion_group_key(animation, alias_map)
        group_map.setdefault(group_key, []).append((index, animation))

    compositions: list[_SampledCenterMotionComposition] = []
    for members in group_map.values():
        base_animation = min(members, key=lambda item: item[0])[1]
        element = element_map.get(base_animation.element_id)
        current_center = center_map.get(base_animation.element_id)
        if element is None or current_center is None:
            continue

        composition = _build_sampled_center_motion_composition(
            element=element,
            current_center=current_center,
            members=members,
        )
        if composition is not None:
            compositions.append(composition)

    if not compositions:
        return animations

    center_targets = {
        composition.element_id: composition.start_center
        for composition in compositions
    }
    scene.elements = [
        _translate_element_to_center_target(element, center_targets)
        for element in scene.elements
    ]

    replacements = {
        composition.replacement_index: composition
        for composition in compositions
    }
    updated_indices: dict[int, AnimationDefinition] = {}
    consumed_indices: set[int] = set()
    for composition in compositions:
        updated_indices.update(composition.updated_indices)
        consumed_indices.update(composition.consumed_indices)

    composed: list[AnimationDefinition] = []
    for index, animation in enumerate(animations):
        if index in replacements:
            composed.append(replacements[index].replacement_animation)
        if index in consumed_indices:
            continue
        composed.append(updated_indices.get(index, animation))
    return composed


def _build_sampled_center_motion_composition(
    *,
    element: object,
    current_center: tuple[float, float],
    members: list[tuple[int, AnimationDefinition]],
) -> _SampledCenterMotionComposition | None:
    from dataclasses import replace as _replace

    from svg2ooxml.ir.scene import Image
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Circle, Polygon, Polyline

    if isinstance(element, Circle):
        scale_member = _single_matching_member(
            members,
            lambda anim: (
                anim.animation_type == AnimationType.ANIMATE_TRANSFORM
                and anim.transform_type == TransformType.SCALE
                and _is_simple_linear_two_value_animation(anim)
            ),
        )
        if scale_member is None:
            return None

        numeric_members = {
            anim.target_attribute: (index, anim)
            for index, anim in members
            if _is_simple_linear_numeric_animation(anim)
            and anim.target_attribute in {"x", "y", "cx", "cy"}
        }
        if not numeric_members:
            return None

        matrix = _resolve_affine_matrix(
            [scale_member[1], *(anim for _, anim in numeric_members.values())]
        )
        local_center_x, local_center_y = _inverse_project_affine_point(
            current_center,
            matrix,
        )
        (from_sx, from_sy), (to_sx, to_sy) = _parse_scale_bounds(scale_member[1])

        x0, x1 = _numeric_bounds(numeric_members.get("x"), default=0.0)
        y0, y1 = _numeric_bounds(numeric_members.get("y"), default=0.0)
        cx0, cx1 = _numeric_bounds(numeric_members.get("cx"), default=local_center_x)
        cy0, cy1 = _numeric_bounds(numeric_members.get("cy"), default=local_center_y)

        samples = _sample_progress_values()
        center_points = []
        for progress in samples:
            sx = _lerp(from_sx, to_sx, progress)
            sy = _lerp(from_sy, to_sy, progress)
            tx = _lerp(x0, x1, progress)
            ty = _lerp(y0, y1, progress)
            cx = _lerp(cx0, cx1, progress)
            cy = _lerp(cy0, cy1, progress)
            center_points.append(
                _project_affine_point(
                    (tx + sx * cx, ty + sy * cy),
                    matrix,
                )
            )

        motion_template = min(numeric_members.values(), key=lambda item: item[0])[1]
        replacement_index = min(index for index, _ in numeric_members.values())
        consumed_indices = {index for index, _ in numeric_members.values()}
        updated_scale = _replace(scale_member[1], element_center_px=None)
        updated_indices = {scale_member[0]: updated_scale}
        return _SampledCenterMotionComposition(
            replacement_index=replacement_index,
            consumed_indices=consumed_indices,
            replacement_animation=_build_sampled_motion_replacement(
                template=motion_template,
                points=center_points,
            ),
            updated_indices=updated_indices,
            start_center=center_points[0],
            element_id=motion_template.element_id,
        )

    if isinstance(element, Image):
        scale_member = _single_matching_member(
            members,
            lambda anim: (
                anim.animation_type == AnimationType.ANIMATE_TRANSFORM
                and anim.transform_type == TransformType.SCALE
                and _is_simple_linear_two_value_animation(anim)
            ),
        )
        if scale_member is None:
            return None

        numeric_members = {
            anim.target_attribute: (index, anim)
            for index, anim in members
            if _is_simple_linear_numeric_animation(anim)
            and anim.target_attribute in {"x", "y"}
        }
        if not numeric_members:
            return None

        matrix = _resolve_affine_matrix(
            [scale_member[1], *(anim for _, anim in numeric_members.values())]
        )
        local_bbox = _inverse_project_affine_rect(element.bbox, matrix)
        viewport_rect, content_rect = _image_local_layout(element, local_bbox)
        (from_sx, from_sy), (to_sx, to_sy) = _parse_scale_bounds(scale_member[1])

        x0, x1 = _numeric_bounds(numeric_members.get("x"), default=viewport_rect.x)
        y0, y1 = _numeric_bounds(numeric_members.get("y"), default=viewport_rect.y)
        content_offset_x = float(content_rect.x - viewport_rect.x)
        content_offset_y = float(content_rect.y - viewport_rect.y)
        width = float(content_rect.width)
        height = float(content_rect.height)

        center_points = []
        for progress in _sample_progress_values():
            sx = _lerp(from_sx, to_sx, progress)
            sy = _lerp(from_sy, to_sy, progress)
            x = _lerp(x0, x1, progress)
            y = _lerp(y0, y1, progress)
            center_points.append(
                _project_affine_point(
                    (
                        sx * (x + content_offset_x + width / 2.0),
                        sy * (y + content_offset_y + height / 2.0),
                    ),
                    matrix,
                )
            )

        motion_template = min(numeric_members.values(), key=lambda item: item[0])[1]
        replacement_index = min(index for index, _ in numeric_members.values())
        consumed_indices = {index for index, _ in numeric_members.values()}
        updated_scale = _replace(scale_member[1], element_center_px=None)
        updated_indices = {scale_member[0]: updated_scale}
        return _SampledCenterMotionComposition(
            replacement_index=replacement_index,
            consumed_indices=consumed_indices,
            replacement_animation=_build_sampled_motion_replacement(
                template=motion_template,
                points=center_points,
            ),
            updated_indices=updated_indices,
            start_center=center_points[0],
            element_id=motion_template.element_id,
        )

    if isinstance(element, (IRPath, Polyline, Polygon)):
        motion_member = _single_matching_member(
            members,
            lambda anim: (
                anim.animation_type == AnimationType.ANIMATE_MOTION
                and _is_simple_motion_sampling_candidate(anim)
            ),
        )
        rotate_member = _single_matching_member(
            members,
            lambda anim: (
                anim.animation_type == AnimationType.ANIMATE_TRANSFORM
                and anim.transform_type == TransformType.ROTATE
                and _is_simple_origin_rotate_animation(anim)
            ),
        )
        if motion_member is None or rotate_member is None:
            return None

        matrix = _resolve_affine_matrix([motion_member[1], rotate_member[1]])
        local_center = _inverse_project_affine_point(current_center, matrix)
        motion_points = _parse_sampled_motion_points(motion_member[1].values[0])
        if len(motion_points) < 2:
            return None

        start_angle, end_angle = _parse_rotate_bounds(rotate_member[1])
        center_points = []
        for progress in _sample_progress_values():
            motion_point = _sample_polyline_at_fraction(motion_points, progress)
            angle = _lerp(start_angle, end_angle, progress)
            rotated = _rotate_point(
                (local_center[0] + motion_point[0], local_center[1] + motion_point[1]),
                angle,
            )
            center_points.append(_project_affine_point(rotated, matrix))

        return _SampledCenterMotionComposition(
            replacement_index=motion_member[0],
            consumed_indices={motion_member[0]},
            replacement_animation=_build_sampled_motion_replacement(
                template=motion_member[1],
                points=center_points,
            ),
            updated_indices={},
            start_center=center_points[0],
            element_id=motion_member[1].element_id,
        )

    return None


def _single_matching_member(
    members: list[tuple[int, AnimationDefinition]],
    predicate,
) -> tuple[int, AnimationDefinition] | None:
    matches = [(index, animation) for index, animation in members if predicate(animation)]
    if len(matches) != 1:
        return None
    return matches[0]


def _is_simple_linear_two_value_animation(animation: AnimationDefinition) -> bool:
    if len(animation.values) != 2:
        return False
    if animation.key_times or animation.key_splines:
        return False
    calc_mode = (
        animation.calc_mode.value
        if isinstance(animation.calc_mode, CalcMode)
        else str(animation.calc_mode).lower()
    )
    return calc_mode == CalcMode.LINEAR.value


def _is_simple_line_endpoint_animation(animation: AnimationDefinition) -> bool:
    return (
        animation.animation_type == AnimationType.ANIMATE
        and animation.transform_type is None
        and animation.target_attribute in {"x1", "x2", "y1", "y2"}
        and animation.additive == "replace"
        and _is_simple_linear_two_value_animation(animation)
    )


def _is_polyline_segment_fade_animation(animation: AnimationDefinition) -> bool:
    return (
        animation.animation_type == AnimationType.ANIMATE
        and animation.transform_type is None
        and animation.target_attribute in {"opacity", "fill-opacity", "stroke-opacity"}
    )


def _is_simple_linear_numeric_animation(animation: AnimationDefinition) -> bool:
    return (
        animation.animation_type == AnimationType.ANIMATE
        and animation.transform_type is None
        and animation.additive == "replace"
        and _is_simple_linear_two_value_animation(animation)
    )


def _is_simple_motion_sampling_candidate(animation: AnimationDefinition) -> bool:
    if animation.animation_type != AnimationType.ANIMATE_MOTION:
        return False
    if animation.key_times or animation.key_splines:
        return False
    calc_mode = (
        animation.calc_mode.value
        if isinstance(animation.calc_mode, CalcMode)
        else str(animation.calc_mode).lower()
    )
    return calc_mode in {CalcMode.LINEAR.value, CalcMode.PACED.value}


def _is_simple_origin_rotate_animation(animation: AnimationDefinition) -> bool:
    from svg2ooxml.common.conversions.transforms import parse_numeric_list

    if animation.animation_type != AnimationType.ANIMATE_TRANSFORM:
        return False
    if animation.transform_type != TransformType.ROTATE:
        return False
    if not _is_simple_linear_two_value_animation(animation):
        return False
    for value in animation.values:
        if len(parse_numeric_list(value)) >= 3:
            return False
    return True


def _parse_scale_bounds(
    animation: AnimationDefinition,
) -> tuple[tuple[float, float], tuple[float, float]]:
    from svg2ooxml.common.conversions.transforms import parse_scale_pair

    return (
        parse_scale_pair(animation.values[0]),
        parse_scale_pair(animation.values[-1]),
    )


def _parse_rotate_bounds(animation: AnimationDefinition) -> tuple[float, float]:
    from svg2ooxml.common.conversions.transforms import parse_numeric_list

    start_numbers = parse_numeric_list(animation.values[0])
    end_numbers = parse_numeric_list(animation.values[-1])
    start_angle = start_numbers[0] if start_numbers else 0.0
    end_angle = end_numbers[0] if end_numbers else start_angle
    return (start_angle, end_angle)


def _numeric_bounds(
    member: tuple[int, AnimationDefinition] | None,
    *,
    default: float,
) -> tuple[float, float]:
    if member is None:
        return (default, default)
    try:
        return (float(member[1].values[0]), float(member[1].values[-1]))
    except (TypeError, ValueError):
        return (default, default)


def _sample_progress_values(steps: int = 12) -> list[float]:
    return [step / steps for step in range(steps + 1)]


def _lerp(start: float, end: float, progress: float) -> float:
    return start + (end - start) * progress


def _resolve_affine_matrix(
    animations: Sequence[AnimationDefinition],
) -> tuple[float, float, float, float, float, float] | None:
    for animation in animations:
        if animation.motion_space_matrix is not None:
            return animation.motion_space_matrix
    return None


def _project_affine_point(
    point: tuple[float, float],
    matrix: tuple[float, float, float, float, float, float] | None,
) -> tuple[float, float]:
    x, y = point
    if matrix is None:
        return (x, y)
    a, b, c, d, e, f = matrix
    return (a * x + c * y + e, b * x + d * y + f)


def _inverse_project_affine_point(
    point: tuple[float, float],
    matrix: tuple[float, float, float, float, float, float] | None,
) -> tuple[float, float]:
    x, y = point
    if matrix is None:
        return (x, y)
    a, b, c, d, e, f = matrix
    det = (a * d) - (b * c)
    if abs(det) <= 1e-9:
        return (x, y)
    px = x - e
    py = y - f
    return ((d * px - c * py) / det, (-b * px + a * py) / det)


def _inverse_project_affine_rect(
    rect: Any,
    matrix: tuple[float, float, float, float, float, float] | None,
):
    from svg2ooxml.ir.geometry import Rect

    corners = (
        (float(rect.x), float(rect.y)),
        (float(rect.x + rect.width), float(rect.y)),
        (float(rect.x), float(rect.y + rect.height)),
        (float(rect.x + rect.width), float(rect.y + rect.height)),
    )
    local_corners = [_inverse_project_affine_point(corner, matrix) for corner in corners]
    xs = [corner[0] for corner in local_corners]
    ys = [corner[1] for corner in local_corners]
    return Rect(
        min(xs),
        min(ys),
        max(xs) - min(xs),
        max(ys) - min(ys),
    )


def _image_local_layout(
    element: Any,
    local_bbox: Any,
):
    from svg2ooxml.ir.geometry import Rect

    metadata = getattr(element, "metadata", None)
    if not isinstance(metadata, dict):
        return local_bbox, local_bbox
    layout = metadata.get("image_layout")
    if not isinstance(layout, dict):
        return local_bbox, local_bbox

    viewport = layout.get("viewport")
    content_offset = layout.get("content_offset")
    content_size = layout.get("content_size")
    if not (
        isinstance(viewport, dict)
        and isinstance(content_offset, dict)
        and isinstance(content_size, dict)
    ):
        return local_bbox, local_bbox

    try:
        viewport_rect = Rect(
            float(viewport["x"]),
            float(viewport["y"]),
            float(viewport["width"]),
            float(viewport["height"]),
        )
        content_rect = Rect(
            viewport_rect.x + float(content_offset["x"]),
            viewport_rect.y + float(content_offset["y"]),
            float(content_size["width"]),
            float(content_size["height"]),
        )
    except (KeyError, TypeError, ValueError):
        return local_bbox, local_bbox

    return viewport_rect, content_rect


def _rotate_point(point: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    radians = math.radians(angle_deg)
    cos_v = math.cos(radians)
    sin_v = math.sin(radians)
    x, y = point
    return (x * cos_v - y * sin_v, x * sin_v + y * cos_v)


def _build_sampled_motion_replacement(
    *,
    template: AnimationDefinition,
    points: list[tuple[float, float]],
) -> AnimationDefinition:
    from dataclasses import replace as _replace

    relative_points = _relative_motion_points(points)
    path = _build_motion_path_from_relative_points(relative_points)
    return _replace(
        template,
        animation_type=AnimationType.ANIMATE_MOTION,
        target_attribute="position",
        values=[path],
        key_times=None,
        key_splines=None,
        calc_mode=CalcMode.LINEAR,
        transform_type=None,
        additive="replace",
        accumulate="none",
        motion_rotate=None,
        element_motion_offset_px=None,
        motion_space_matrix=None,
    )


def _relative_motion_points(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    deduped: list[tuple[float, float]] = []
    start_x, start_y = points[0]
    for x, y in points:
        pair = (x - start_x, y - start_y)
        if (
            not deduped
            or abs(deduped[-1][0] - pair[0]) > 1e-6
            or abs(deduped[-1][1] - pair[1]) > 1e-6
        ):
            deduped.append(pair)
    if len(deduped) == 1:
        deduped.append(deduped[0])
    return deduped


def _build_motion_path_from_relative_points(
    points: list[tuple[float, float]],
) -> str:
    segments = []
    for index, (x, y) in enumerate(points):
        command = "M" if index == 0 else "L"
        segments.append(
            f"{command} {_format_motion_delta(x)} {_format_motion_delta(y)}"
        )
    return " ".join(segments) + " E"


def _parse_sampled_motion_points(path_value: str) -> list[tuple[float, float]]:
    from svg2ooxml.common.geometry.paths import PathParseError, parse_path_data
    from svg2ooxml.common.geometry.paths.segments import BezierSegment, LineSegment
    from svg2ooxml.ir.geometry import Point

    try:
        segments = parse_path_data(path_value)
    except PathParseError:
        return []
    if not segments:
        return []

    points: list[Point] = [segments[0].start]
    for segment in segments:
        if isinstance(segment, LineSegment):
            points.append(segment.end)
        elif isinstance(segment, BezierSegment):
            for step in range(1, 21):
                t = step / 20.0
                mt = 1.0 - t
                points.append(
                    Point(
                        x=(
                            mt**3 * segment.start.x
                            + 3 * mt**2 * t * segment.control1.x
                            + 3 * mt * t**2 * segment.control2.x
                            + t**3 * segment.end.x
                        ),
                        y=(
                            mt**3 * segment.start.y
                            + 3 * mt**2 * t * segment.control1.y
                            + 3 * mt * t**2 * segment.control2.y
                            + t**3 * segment.end.y
                        ),
                    )
                )

    deduped: list[tuple[float, float]] = []
    for point in points:
        pair = (float(point.x), float(point.y))
        if (
            not deduped
            or abs(deduped[-1][0] - pair[0]) > 1e-6
            or abs(deduped[-1][1] - pair[1]) > 1e-6
        ):
            deduped.append(pair)
    return deduped


def _sample_polyline_at_fraction(
    points: list[tuple[float, float]],
    fraction: float,
) -> tuple[float, float]:
    if fraction <= 0.0:
        return points[0]
    if fraction >= 1.0:
        return points[-1]

    cumulative = [0.0]
    total = 0.0
    for index in range(1, len(points)):
        x0, y0 = points[index - 1]
        x1, y1 = points[index]
        total += math.hypot(x1 - x0, y1 - y0)
        cumulative.append(total)
    if total <= 1e-9:
        return points[0]

    target = total * fraction
    for index in range(1, len(points)):
        prev_dist = cumulative[index - 1]
        curr_dist = cumulative[index]
        if target <= curr_dist:
            span = curr_dist - prev_dist
            if span <= 1e-9:
                return points[index]
            t = (target - prev_dist) / span
            x0, y0 = points[index - 1]
            x1, y1 = points[index]
            return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
    return points[-1]


def _simple_position_axis(animation: AnimationDefinition) -> str | None:
    if animation.animation_type != AnimationType.ANIMATE:
        return None
    if animation.transform_type is not None:
        return None
    if len(animation.values) != 2:
        return None
    if animation.key_times or animation.key_splines:
        return None
    if animation.additive != "replace":
        return None

    calc_mode = (
        animation.calc_mode.value
        if isinstance(animation.calc_mode, CalcMode)
        else str(animation.calc_mode).lower()
    )
    if calc_mode != CalcMode.LINEAR.value:
        return None

    if animation.target_attribute in {"x", "cx", "ppt_x"}:
        return "x"
    if animation.target_attribute in {"y", "cy", "ppt_y"}:
        return "y"
    return None


def _format_motion_delta(value: float) -> str:
    if abs(value) < 1e-10:
        return "0"
    return f"{value:.6g}"


def _project_linear_motion_delta(
    dx: float,
    dy: float,
    animation: AnimationDefinition,
) -> tuple[float, float]:
    matrix = animation.motion_space_matrix
    if matrix is None:
        return (dx, dy)
    a, b, c, d, _e, _f = matrix
    return (a * dx + c * dy, b * dx + d * dy)


def _infer_element_heading_deg(element: Any) -> float | None:
    from svg2ooxml.ir.geometry import LineSegment
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Line, Polygon, Polyline

    if isinstance(element, Line):
        dx = element.end.x - element.start.x
        dy = element.end.y - element.start.y
        if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
            return None
        return _angle_deg(dx, dy)

    if isinstance(element, Polyline):
        return _infer_heading_from_points(
            [(point.x, point.y) for point in element.points],
            closed=False,
        )

    if isinstance(element, Polygon):
        return _infer_heading_from_points(
            [(point.x, point.y) for point in element.points],
            closed=True,
        )

    if isinstance(element, IRPath):
        points: list[tuple[float, float]] = []
        for segment in element.segments:
            start = getattr(segment, "start", None)
            end = getattr(segment, "end", None)
            if start is not None:
                points.append((float(start.x), float(start.y)))
            if isinstance(segment, LineSegment) and end is not None:
                points.append((float(end.x), float(end.y)))
        return _infer_heading_from_points(points, closed=element.is_closed)

    return None


def _infer_heading_from_points(
    points: list[tuple[float, float]],
    *,
    closed: bool,
) -> float | None:
    vertices = _dedupe_motion_vertices(points, closed=closed)
    if len(vertices) < 2:
        return None

    if closed and len(vertices) >= 3:
        centroid_x = sum(x for x, _y in vertices) / len(vertices)
        centroid_y = sum(y for _x, y in vertices) / len(vertices)
        ranked = sorted(
            (
                ((x - centroid_x) ** 2 + (y - centroid_y) ** 2, x, y)
                for x, y in vertices
            ),
            reverse=True,
        )
        if ranked[0][0] > 1e-6:
            if len(ranked) == 1 or ranked[0][0] - ranked[1][0] > ranked[0][0] * 0.05:
                _distance_sq, tip_x, tip_y = ranked[0]
                return _angle_deg(tip_x - centroid_x, tip_y - centroid_y)

    start_x, start_y = vertices[0]
    end_x, end_y = vertices[-1]
    dx = end_x - start_x
    dy = end_y - start_y
    if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
        return None
    return _angle_deg(dx, dy)


def _dedupe_motion_vertices(
    points: list[tuple[float, float]],
    *,
    closed: bool,
) -> list[tuple[float, float]]:
    deduped: list[tuple[float, float]] = []
    for x, y in points:
        if not deduped or abs(deduped[-1][0] - x) > 1e-6 or abs(deduped[-1][1] - y) > 1e-6:
            deduped.append((x, y))
    if (
        closed
        and len(deduped) > 1
        and abs(deduped[0][0] - deduped[-1][0]) <= 1e-6
        and abs(deduped[0][1] - deduped[-1][1]) <= 1e-6
    ):
        deduped.pop()
    return deduped


def _angle_deg(dx: float, dy: float) -> float:
    return float(math.degrees(math.atan2(dy, dx)))


def _apply_immediate_motion_starts(
    scene: IRScene,
    animations: list[AnimationDefinition],
) -> None:
    """Pre-position begin=0 motion targets at their SVG path start points."""
    start_positions: dict[str, tuple[float, float]] = {}
    for animation in animations:
        if animation.animation_type != AnimationType.ANIMATE_MOTION:
            continue
        if (
            animation.target_attribute == "position"
            and animation.motion_space_matrix is None
            and animation.element_motion_offset_px is None
        ):
            # Synthesized relative delta paths already start from the authored
            # base geometry in the scene. Re-applying a motion-start probe
            # would incorrectly snap those shapes to (0, 0).
            continue
        if abs(animation.timing.begin) > 1e-9:
            continue
        first_point = _first_motion_point(animation)
        if first_point is None:
            continue
        start_positions[animation.element_id] = _project_motion_point(first_point, animation)

    if not start_positions:
        return

    scene.elements = [
        _translate_element_to_motion_start(element, start_positions)
        for element in scene.elements
    ]


def _first_motion_point(
    animation: AnimationDefinition,
) -> tuple[float, float] | None:
    from svg2ooxml.common.geometry.paths import PathParseError, parse_path_data

    if not animation.values:
        return None

    path_value = animation.values[0].strip()
    if not path_value:
        return None

    try:
        segments = parse_path_data(path_value)
    except PathParseError:
        return None

    if segments:
        start = getattr(segments[0], "start", None)
        if start is not None:
            return (float(start.x), float(start.y))

    return None


def _project_motion_point(
    point: tuple[float, float],
    animation: AnimationDefinition,
) -> tuple[float, float]:
    x, y = point
    if animation.motion_space_matrix is not None:
        a, b, c, d, e, f = animation.motion_space_matrix
        x, y = (a * x + c * y + e, b * x + d * y + f)

    if animation.element_motion_offset_px is not None:
        offset_x, offset_y = animation.element_motion_offset_px
        x += offset_x
        y += offset_y

    return (x, y)


def _translate_element_to_center_target(
    element: Any,
    center_targets: Mapping[str, tuple[float, float]],
):
    from dataclasses import replace as _replace

    from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect
    from svg2ooxml.ir.scene import Group, Image
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Circle, Ellipse, Line, Polygon, Polyline, Rectangle
    from svg2ooxml.ir.text import TextFrame

    metadata = getattr(element, "metadata", None)
    element_ids = metadata.get("element_ids", []) if isinstance(metadata, dict) else []
    bbox = getattr(element, "bbox", None)

    dx = 0.0
    dy = 0.0
    if bbox is not None:
        current_center = (bbox.x + bbox.width / 2.0, bbox.y + bbox.height / 2.0)
        for element_id in element_ids:
            if element_id in center_targets:
                target_x, target_y = center_targets[element_id]
                dx = target_x - current_center[0]
                dy = target_y - current_center[1]
                break

    def _move_point(point: Point) -> Point:
        return Point(point.x + dx, point.y + dy)

    def _move_rect(rect: Rect) -> Rect:
        return Rect(rect.x + dx, rect.y + dy, rect.width, rect.height)

    if isinstance(element, Group):
        moved_children = [
            _translate_element_to_center_target(child, center_targets)
            for child in element.children
        ]
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            moved_children = [
                _translate_element_by_delta(child, dx, dy)
                for child in moved_children
            ]
        return _replace(element, children=moved_children)

    if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
        return element

    if isinstance(element, IRPath):
        moved_segments = []
        for segment in element.segments:
            if isinstance(segment, LineSegment):
                moved_segments.append(
                    LineSegment(
                        start=_move_point(segment.start),
                        end=_move_point(segment.end),
                    )
                )
            elif isinstance(segment, BezierSegment):
                moved_segments.append(
                    BezierSegment(
                        start=_move_point(segment.start),
                        control1=_move_point(segment.control1),
                        control2=_move_point(segment.control2),
                        end=_move_point(segment.end),
                    )
                )
            else:
                moved_segments.append(segment)
        return _replace(element, segments=moved_segments)
    if isinstance(element, Rectangle):
        return _replace(element, bounds=_move_rect(element.bounds))
    if isinstance(element, Circle):
        return _replace(element, center=_move_point(element.center))
    if isinstance(element, Ellipse):
        return _replace(element, center=_move_point(element.center))
    if isinstance(element, Line):
        return _replace(
            element,
            start=_move_point(element.start),
            end=_move_point(element.end),
        )
    if isinstance(element, Polyline):
        return _replace(
            element,
            points=[_move_point(point) for point in element.points],
        )
    if isinstance(element, Polygon):
        return _replace(
            element,
            points=[_move_point(point) for point in element.points],
        )
    if isinstance(element, TextFrame):
        return _replace(
            element,
            origin=_move_point(element.origin),
            bbox=_move_rect(element.bbox),
        )
    if isinstance(element, Image):
        return _replace(
            element,
            origin=_move_point(element.origin),
        )
    return element


def _translate_element_to_motion_start(
    element: Any,
    start_positions: Mapping[str, tuple[float, float]],
):
    from dataclasses import replace as _replace

    from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect
    from svg2ooxml.ir.scene import Group, Image
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Circle, Ellipse, Line, Polygon, Polyline, Rectangle
    from svg2ooxml.ir.text import TextFrame

    metadata = getattr(element, "metadata", None)
    element_ids = metadata.get("element_ids", []) if isinstance(metadata, dict) else []
    bbox = getattr(element, "bbox", None)

    dx = 0.0
    dy = 0.0
    if bbox is not None:
        for element_id in element_ids:
            if element_id in start_positions:
                target_x, target_y = start_positions[element_id]
                dx = target_x - bbox.x
                dy = target_y - bbox.y
                break

    def _move_point(point: Point) -> Point:
        return Point(point.x + dx, point.y + dy)

    def _move_rect(rect: Rect) -> Rect:
        return Rect(rect.x + dx, rect.y + dy, rect.width, rect.height)

    if isinstance(element, Group):
        moved_children = [
            _translate_element_to_motion_start(child, start_positions)
            for child in element.children
        ]
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            moved_children = [
                _translate_element_by_delta(child, dx, dy)
                for child in moved_children
            ]
        return _replace(element, children=moved_children)

    if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
        return element

    if isinstance(element, IRPath):
        moved_segments = []
        for segment in element.segments:
            if isinstance(segment, LineSegment):
                moved_segments.append(
                    LineSegment(
                        start=_move_point(segment.start),
                        end=_move_point(segment.end),
                    )
                )
            elif isinstance(segment, BezierSegment):
                moved_segments.append(
                    BezierSegment(
                        start=_move_point(segment.start),
                        control1=_move_point(segment.control1),
                        control2=_move_point(segment.control2),
                        end=_move_point(segment.end),
                    )
                )
            else:
                moved_segments.append(segment)
        return _replace(element, segments=moved_segments)
    if isinstance(element, Rectangle):
        return _replace(element, bounds=_move_rect(element.bounds))
    if isinstance(element, Circle):
        return _replace(element, center=_move_point(element.center))
    if isinstance(element, Ellipse):
        return _replace(element, center=_move_point(element.center))
    if isinstance(element, Line):
        return _replace(
            element,
            start=_move_point(element.start),
            end=_move_point(element.end),
        )
    if isinstance(element, Polyline):
        return _replace(
            element,
            points=[_move_point(point) for point in element.points],
        )
    if isinstance(element, Polygon):
        return _replace(
            element,
            points=[_move_point(point) for point in element.points],
        )
    if isinstance(element, TextFrame):
        return _replace(
            element,
            origin=_move_point(element.origin),
            bbox=_move_rect(element.bbox),
        )
    if isinstance(element, Image):
        return _replace(
            element,
            origin=_move_point(element.origin),
        )
    return element


def _translate_element_by_delta(element: Any, dx: float, dy: float):
    from dataclasses import replace as _replace

    from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect
    from svg2ooxml.ir.scene import Group, Image
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Circle, Ellipse, Line, Polygon, Polyline, Rectangle
    from svg2ooxml.ir.text import TextFrame

    def _move_point(point: Point) -> Point:
        return Point(point.x + dx, point.y + dy)

    def _move_rect(rect: Rect) -> Rect:
        return Rect(rect.x + dx, rect.y + dy, rect.width, rect.height)

    if isinstance(element, Group):
        return _replace(
            element,
            children=[_translate_element_by_delta(child, dx, dy) for child in element.children],
        )
    if isinstance(element, IRPath):
        moved_segments = []
        for segment in element.segments:
            if isinstance(segment, LineSegment):
                moved_segments.append(
                    LineSegment(
                        start=_move_point(segment.start),
                        end=_move_point(segment.end),
                    )
                )
            elif isinstance(segment, BezierSegment):
                moved_segments.append(
                    BezierSegment(
                        start=_move_point(segment.start),
                        control1=_move_point(segment.control1),
                        control2=_move_point(segment.control2),
                        end=_move_point(segment.end),
                    )
                )
            else:
                moved_segments.append(segment)
        return _replace(element, segments=moved_segments)
    if isinstance(element, Rectangle):
        return _replace(element, bounds=_move_rect(element.bounds))
    if isinstance(element, Circle):
        return _replace(element, center=_move_point(element.center))
    if isinstance(element, Ellipse):
        return _replace(element, center=_move_point(element.center))
    if isinstance(element, Line):
        return _replace(
            element,
            start=_move_point(element.start),
            end=_move_point(element.end),
        )
    if isinstance(element, Polyline):
        return _replace(element, points=[_move_point(point) for point in element.points])
    if isinstance(element, Polygon):
        return _replace(element, points=[_move_point(point) for point in element.points])
    if isinstance(element, TextFrame):
        return _replace(element, origin=_move_point(element.origin), bbox=_move_rect(element.bbox))
    if isinstance(element, Image):
        return _replace(element, origin=_move_point(element.origin))
    return element


__all__ = [
    "SvgConversionError",
    "SvgToPptxExporter",
    "SvgToPptxResult",
    "SvgToPptxMultiResult",
    "SvgPageSource",
    "SvgPageResult",
]
