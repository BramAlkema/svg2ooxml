"""SVG render assembly for the PPTX exporter."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from svg2ooxml.core.pptx_exporter_types import SvgConversionError
from svg2ooxml.policy.fidelity import PolicyOverrides

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.ir.converter import IRScene
    from svg2ooxml.core.tracing import ConversionTracer
    from svg2ooxml.drawingml.result import DrawingMLRenderResult
    from svg2ooxml.policy import PolicyContext


class SvgToPptxRenderMixin:
    """Parse SVG, apply policy, process animations, and render DrawingML."""

    def _render_svg(
        self,
        svg_text: str,
        tracer: ConversionTracer,
        policy_overrides: PolicyOverrides | None = None,
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

        services_override = parse_result.services
        if services_override is None:
            from svg2ooxml.services import configure_services

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
        timeline_scenes = []
        animation_summary = None
        animation_fallback_reasons: dict[str, int] = {}
        animation_policy_options: dict[str, Any] | None = None

        should_parse_animations = parse_result.svg_root is not None and (
            parse_result.animations is None or bool(parse_result.animations)
        )
        if should_parse_animations:
            from svg2ooxml.drawingml.animation.visibility_compiler import (
                assign_missing_visibility_source_ids,
            )

            assign_missing_visibility_source_ids(parse_result.svg_root)
            animation_parser = self._animation_parser_factory()
            animations = animation_parser.parse_svg_animations(parse_result.svg_root)
            animation_summary = animation_parser.get_animation_summary()
            animation_fallback_reasons = animation_parser.get_degradation_reasons()
            if animations:
                timeline_scenes = self._timeline_sampler.generate_scenes(animations)
            animation_parser.reset_summary()

        effective_overrides = deepcopy(policy_overrides) if policy_overrides else {}
        if self._geometry_mode != "legacy":
            geometry_overrides = effective_overrides.get("geometry", {})
            geometry_overrides["geometry_mode"] = self._geometry_mode
            effective_overrides["geometry"] = geometry_overrides

        policy_context = self._apply_policy_overrides(
            parse_result.policy_context, effective_overrides or None
        )
        if policy_context is not None:
            animation_policy_options = policy_context.get("animation")
        from svg2ooxml.ir import convert_parser_output

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
            self._attach_animation_metadata(
                animations=animations,
                timeline_scenes=timeline_scenes,
                animation_summary=animation_summary,
                animation_fallback_reasons=animation_fallback_reasons,
                animation_policy_options=animation_policy_options,
                scene=scene,
                svg_root=parse_result.svg_root,
                tracer=tracer,
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

    def _attach_animation_metadata(
        self,
        *,
        animations: list[Any],
        timeline_scenes: list[Any],
        animation_summary: Any,
        animation_fallback_reasons: dict[str, int],
        animation_policy_options: dict[str, Any] | None,
        scene: IRScene,
        svg_root: Any,
        tracer: ConversionTracer,
    ) -> None:
        from svg2ooxml.core.export.animation_processor import (
            _build_animation_metadata,
            _compose_sampled_center_motions,
            _enrich_animations_with_element_centers,
            _expand_deterministic_repeat_triggers,
            _lower_safe_group_transform_targets_with_animated_descendants,
            _prepare_scene_for_native_opacity_effects,
        )
        from svg2ooxml.core.export.motion_geometry import (
            _apply_immediate_motion_starts,
        )
        from svg2ooxml.core.export.polyline_materialization import (
            _materialize_stroked_polyline_groups,
        )
        from svg2ooxml.core.export.variant_expansion import (
            _coalesce_simple_position_motions,
            _compose_simple_line_endpoint_animations,
            _materialize_simple_line_paths,
        )
        from svg2ooxml.drawingml.animation.visibility_compiler import (
            rewrite_visibility_animations,
        )

        animations = _expand_deterministic_repeat_triggers(animations)
        animations = rewrite_visibility_animations(animations, scene, svg_root)
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

    @staticmethod
    def _apply_policy_overrides(
        context: PolicyContext | None,
        overrides: PolicyOverrides | None,
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

        from svg2ooxml.policy import PolicyContext

        return PolicyContext(selections=base_selections)


__all__ = ["SvgToPptxRenderMixin"]
