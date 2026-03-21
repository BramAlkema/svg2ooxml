"""Style extraction helpers for IR conversion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D, parse_transform_list
from svg2ooxml.common.style.resolver import StyleResolver
from svg2ooxml.drawingml.bridges.resvg_paint_bridge import (
    GradientDescriptor,
    LinearGradientDescriptor,
    MeshGradientDescriptor,
    PatternDescriptor,
)
from svg2ooxml.elements.gradient_processor import GradientComplexity
from svg2ooxml.elements.pattern_processor import PatternComplexity, PatternType
from svg2ooxml.ir.effects import Effect
from svg2ooxml.ir.paint import (
    GradientPaintRef,
    GradientStop,
    LinearGradientPaint,
    PatternPaint,
    RadialGradientPaint,
    SolidPaint,
    Stroke,
    StrokeCap,
    StrokeJoin,
)
from svg2ooxml.core.styling.style_helpers import (
    apply_matrix_to_point,
    apply_stroke_opacity,
    clean_color,
    descriptor_stop_colors,
    extract_url_id as _extract_url_id,
    local_name,
    matrix2d_to_numpy,
    matrix_tuple_is_identity,
    normalize_hex as _normalize_hex,
    parse_dash_array as _parse_dash_array,
    parse_offset,
    parse_optional_float as _parse_optional_float,
    parse_percentage,
    parse_stop_color,
    parse_style_attr,
)
from svg2ooxml.policy.constants import FALLBACK_EMF, geometry_fallback_for
from svg2ooxml.services import ConversionServices

if TYPE_CHECKING:  # pragma: no cover - hint only
    from svg2ooxml.core.tracing import ConversionTracer


@dataclass(slots=True)
class StyleResult:
    fill: SolidPaint | GradientPaintRef | PatternPaint | None
    stroke: Stroke | None
    opacity: float
    effects: list[Effect]
    metadata: dict[str, Any]


class StyleExtractor:
    """Convert SVG presentation attributes into IR paint structures."""

    def __init__(self, style_resolver: StyleResolver) -> None:
        self._resolver = style_resolver
        self._unit_converter = getattr(style_resolver, "_unit_converter", None)
        self._tracer: ConversionTracer | None = None
        self._paint_cache: dict[etree._Element, dict[str, Any]] = {}

    def set_tracer(self, tracer: ConversionTracer | None) -> None:
        self._tracer = tracer

    def clear_cache(self) -> None:
        self._paint_cache.clear()

    def extract(self, element: etree._Element, services: ConversionServices, *, context: Any | None = None) -> StyleResult:
        paint_style = self._compute_paint_style_with_inheritance(element, context=context)
        metadata: dict[str, Any] = {}

        fill_opacity = float(paint_style.get("fill_opacity", 1.0))
        fill_opacity = max(0.0, min(1.0, fill_opacity))

        fill = self._resolve_paint(
            element,
            paint_style.get("fill"),
            opacity=fill_opacity,
            services=services,
            context=context,
            metadata=metadata,
            role="fill",
        )

        stroke = self._resolve_stroke(
            element,
            paint_style,
            services=services,
            context=context,
            metadata=metadata,
        )

        opacity = float(paint_style.get("opacity", 1.0))
        opacity = max(0.0, min(1.0, opacity))
        effects = self._resolve_effects(element, services, metadata, context)

        # Parse paint-order (SVG2): "stroke fill markers", "fill stroke", etc.
        paint_order = paint_style.get("paint_order") or element.get("paint-order", "").strip()
        if paint_order and paint_order != "normal":
            metadata["paint_order"] = paint_order

        return StyleResult(fill=fill, stroke=stroke, opacity=opacity, effects=effects, metadata=metadata)

    def _compute_paint_style_with_inheritance(
        self,
        element: etree._Element,
        context: Any | None,
    ) -> dict[str, Any]:
        cached = self._paint_cache.get(element)
        if cached is not None:
            return dict(cached)

        parent_style: dict[str, Any] | None = None
        parent = element.getparent()
        if isinstance(parent, etree._Element) and isinstance(parent.tag, str):
            parent_style = self._compute_paint_style_with_inheritance(parent, context)

        style = self._resolver.compute_paint_style(element, context=context, parent_style=parent_style)
        self._paint_cache[element] = dict(style)
        return dict(style)

    # ------------------------------------------------------------------
    # Paint/stroke helpers
    # ------------------------------------------------------------------

    def _resolve_paint(
        self,
        element: etree._Element,
        token: str | None,
        *,
        opacity: float,
        services: ConversionServices,
        context: Any | None,
        metadata: dict[str, Any],
        role: str,
    ) -> SolidPaint | GradientPaintRef | PatternPaint | None:
        if token is None:
            return None
        stripped = token.strip()
        if not stripped or stripped.lower() == "none":
            return None
        paint_id = _extract_url_id(stripped)
        if paint_id:
            gradient_service = services.gradient_service
            descriptor = gradient_service.get(paint_id) if gradient_service else None
            if descriptor is not None:
                if isinstance(descriptor, MeshGradientDescriptor):
                    self._record_mesh_gradient_metadata(
                        gradient_id=paint_id,
                        descriptor=descriptor,
                        services=services,
                        metadata=metadata,
                        role=role,
                        context=context,
                    )
                    return GradientPaintRef(gradient_id=paint_id, gradient_type="mesh")

                gradient_paint = self._build_gradient_paint(
                    gradient_id=paint_id,
                    services=services,
                    element=element,
                    opacity=opacity,
                    context=context,
                )

                self._record_gradient_metadata(
                    gradient_id=paint_id,
                    descriptor=descriptor,
                    gradient_service=gradient_service,
                    services=services,
                    metadata=metadata,
                    role=role,
                    context=context,
                )

                if gradient_paint is not None:
                    return gradient_paint
                return GradientPaintRef(gradient_id=paint_id, gradient_type="auto")
            pattern_service = services.pattern_service
            pattern_descriptor = pattern_service.get(paint_id) if pattern_service else None
            if pattern_descriptor is not None:
                pattern_paint = self._build_pattern_paint(
                    pattern_id=paint_id,
                    services=services,
                    context=context,
                )
                if pattern_paint is not None:
                    self._record_pattern_metadata(
                        pattern_id=paint_id,
                        descriptor=pattern_descriptor,
                        pattern_service=pattern_service,
                        services=services,
                        metadata=metadata,
                        role=role,
                        context=context,
                    )
                    return pattern_paint
                return PatternPaint(pattern_id=paint_id)
            # Unknown paint reference – fall through to solid paint with raw token.
        hex_color = _normalize_hex(stripped)
        if hex_color is None:
            return None
        solid = SolidPaint(rgb=hex_color, opacity=opacity)
        self._record_solid_paint(element=element, role=role, paint=solid)
        return solid

    def _record_solid_paint(
        self,
        *,
        element: etree._Element,
        role: str,
        paint: SolidPaint,
    ) -> None:
        tracer = self._tracer
        if tracer is None:
            return

        element_id = element.get("id")
        paint_id = f"{role}:{element_id}" if element_id else f"{role}:{paint.rgb}"
        tracer.record_paint_decision(
            paint_type="solid",
            paint_id=paint_id,
            decision="native",
            metadata={
                "role": role,
                "color": paint.rgb,
                "opacity": paint.opacity,
                "element_id": element_id,
            },
        )
        tracer.record_stage_event(
            stage="paint",
            action="solid",
            subject=element_id,
            metadata={
                "role": role,
                "color": paint.rgb,
                "opacity": paint.opacity,
            },
        )

    def _resolve_stroke(
        self,
        element: etree._Element,
        paint_style: dict[str, Any],
        *,
        services: ConversionServices,
        context: Any | None,
        metadata: dict[str, Any],
    ) -> Stroke | None:
        stroke_token = paint_style.get("stroke")
        if stroke_token is None:
            return None
        stripped = stroke_token.strip()
        if not stripped or stripped.lower() == "none":
            return None

        stroke_paint = self._resolve_paint(
            element,
            stripped,
            opacity=float(paint_style.get("stroke_opacity", 1.0)),
            services=services,
            context=context,
            metadata=metadata,
            role="stroke",
        )
        if stroke_paint is None:
            return None

        stroke_width = float(paint_style.get("stroke_width_px", 1.0))
        join_attr = (element.get("stroke-linejoin") or "miter").lower()
        cap_attr = (element.get("stroke-linecap") or "butt").lower()

        stroke_join = {
            "round": StrokeJoin.ROUND,
            "bevel": StrokeJoin.BEVEL,
        }.get(join_attr, StrokeJoin.MITER)

        stroke_cap = {
            "round": StrokeCap.ROUND,
            "square": StrokeCap.SQUARE,
        }.get(cap_attr, StrokeCap.BUTT)

        dash_array = _parse_dash_array(element.get("stroke-dasharray"))
        dash_offset = _parse_optional_float(element.get("stroke-dashoffset")) or 0.0
        miter_limit = _parse_optional_float(element.get("stroke-miterlimit")) or 4.0
        stroke_opacity = float(paint_style.get("stroke_opacity", 1.0) or 0.0)
        stroke_opacity = max(0.0, min(1.0, stroke_opacity))

        stroke_paint = self._apply_stroke_opacity(stroke_paint, stroke_opacity)

        stroke_obj = Stroke(
            paint=stroke_paint,
            width=stroke_width,
            join=stroke_join,
            cap=stroke_cap,
            dash_array=dash_array,
            dash_offset=dash_offset,
            opacity=stroke_opacity,
            miter_limit=miter_limit,
        )
        tracer = self._tracer
        if tracer is not None:
            tracer.record_stage_event(
                stage="paint",
                action="stroke",
                subject=element.get("id"),
                metadata={
                    "width": stroke_width,
                    "opacity": stroke_opacity,
                    "dash_pattern": bool(dash_array),
                    "join": stroke_join.value,
                    "cap": stroke_cap.value,
                },
            )
        return stroke_obj

    def _resolve_effects(
        self,
        element: etree._Element,
        services: ConversionServices,
        metadata: dict[str, Any],
        context: Any | None,
    ) -> list[Effect]:
        filter_attr = element.get("filter")
        if not filter_attr:
            return []

        filter_service = services.filter_service
        if filter_service and hasattr(filter_service, "resolve_effects"):
            try:
                effects = filter_service.resolve_effects(filter_attr, context=context)  # type: ignore[call-arg]
                if effects:
                    filter_id = _extract_url_id(filter_attr) or filter_attr
                    metadata.setdefault("filter_ids", []).append(filter_id)
                    return list(effects)
            except Exception:  # pragma: no cover - defensive
                pass

        filter_id = _extract_url_id(filter_attr) or filter_attr
        metadata.setdefault("filter_ids", []).append(filter_id)
        return []

    # ------------------------------------------------------------------
    # Gradient & pattern helpers
    # ------------------------------------------------------------------

    def _build_gradient_paint(
        self,
        *,
        gradient_id: str,
        services: ConversionServices,
        element: etree._Element,
        opacity: float,
        context: Any | None,
    ) -> LinearGradientPaint | RadialGradientPaint | None:
        gradient_service = services.gradient_service
        if gradient_service is None:
            return None
        descriptor_chain = gradient_service.resolve_chain(gradient_id, include_self=True)
        if not descriptor_chain:
            descriptor = gradient_service.get(gradient_id)
            if descriptor is None:
                return None
            descriptor_chain = [descriptor]

        materialized_chain = [
            gradient_service.as_element(descriptor) for descriptor in descriptor_chain
        ]

        gradient_type = self._gradient_attr(materialized_chain, "__tag__")
        if gradient_type not in {"linearGradient", "radialGradient"}:
            return None

        stops = self._collect_gradient_stops(materialized_chain, opacity)
        if len(stops) < 2:
            return None

        gradient_units = self._gradient_attr(materialized_chain, "gradientUnits", default="objectBoundingBox")
        gradient_transform = self._gradient_attr(materialized_chain, "gradientTransform")
        transform_matrix: Matrix2D | None = None
        if gradient_transform:
            try:
                transform_matrix = parse_transform_list(gradient_transform)
            except Exception:
                transform_matrix = None

        conversion = getattr(context, "conversion", None) if context else None

        if gradient_type == "linearGradient":
            start = self._resolve_gradient_point(
                materialized_chain,
                "x1",
                "y1",
                default=("0%", "0%"),
                units=gradient_units,
                conversion=conversion,
                axis_defaults=("x", "y"),
            )
            end = self._resolve_gradient_point(
                materialized_chain,
                "x2",
                "y2",
                default=("100%", "0%"),
                units=gradient_units,
                conversion=conversion,
                axis_defaults=("x", "y"),
            )

            if transform_matrix is not None:
                start = self._apply_matrix_to_point(transform_matrix, start)
                end = self._apply_matrix_to_point(transform_matrix, end)

            transform_np = self._matrix2d_to_numpy(transform_matrix)
            return LinearGradientPaint(
                stops=stops,
                start=start,
                end=end,
                transform=transform_np,
                gradient_id=gradient_id,
            )

        # radial gradient
        center = self._resolve_gradient_point(
            materialized_chain,
            "cx",
            "cy",
            default=("50%", "50%"),
            units=gradient_units,
            conversion=conversion,
            axis_defaults=("x", "y"),
        )
        radius = self._resolve_gradient_length(
            materialized_chain,
            "r",
            default="50%",
            units=gradient_units,
            conversion=conversion,
            axis="x",
        )
        if gradient_units == "userSpaceOnUse":
            default_focal = (str(center[0]), str(center[1]))
        else:
            default_focal = (f"{center[0] * 100}%", f"{center[1] * 100}%")
        focal = self._resolve_gradient_point(
            materialized_chain,
            "fx",
            "fy",
            default=default_focal,
            units=gradient_units,
            conversion=conversion,
            axis_defaults=("x", "y"),
        )

        if transform_matrix is not None:
            center = self._apply_matrix_to_point(transform_matrix, center)
            if focal is not None:
                focal = self._apply_matrix_to_point(transform_matrix, focal)

        transform_np = self._matrix2d_to_numpy(transform_matrix)
        return RadialGradientPaint(
            stops=stops,
            center=center,
            radius=radius,
            focal_point=focal,
            transform=transform_np,
            gradient_id=gradient_id,
        )

    def _build_pattern_paint(
        self,
        *,
        pattern_id: str,
        services: ConversionServices,
        context: Any | None = None,
    ) -> PatternPaint | None:
        pattern_service = services.pattern_service
        if pattern_service is None:
            return None
        pattern_descriptor = pattern_service.get(pattern_id)
        if pattern_descriptor is None:
            return None
        pattern_element = pattern_service.as_element(pattern_descriptor)
        transform_attr = pattern_element.get("patternTransform")
        transform_matrix = None
        if transform_attr:
            try:
                transform_matrix = parse_transform_list(transform_attr)
            except Exception:
                transform_matrix = None

        preset = None
        foreground = None
        background = None
        processor = self._get_pattern_processor(services)
        if processor is not None:
            try:
                analysis = processor.analyze_pattern_element(pattern_element, context)
                preset = analysis.preset_candidate
                palette_values: list[str] = []
                if isinstance(analysis.color_statistics, dict):
                    palette_values = analysis.color_statistics.get("palette") or []
                elif hasattr(analysis, "colors_used"):
                    palette_values = analysis.colors_used or []
                cleaned: list[str] = []
                for value in palette_values:
                    colour = self._clean_color(value)
                    if colour:
                        cleaned.append(colour)
                if cleaned:
                    foreground = cleaned[0]
                if len(cleaned) > 1:
                    background = cleaned[1]
            except Exception:  # pragma: no cover - defensive
                pass

        if foreground is None:
            foreground = "000000"
        if background is None:
            background = "FFFFFF"
        preset = preset or "pct5"

        return PatternPaint(
            pattern_id=pattern_id,
            transform=self._matrix2d_to_numpy(transform_matrix),
            preset=preset,
            foreground=foreground,
            background=background,
        )

    def _get_gradient_processor(self, services: ConversionServices):
        processor = services.resolve("gradient_processor")
        if processor is None and services.gradient_service is not None:
            processor = getattr(services.gradient_service, "processor", None)
        return processor

    @staticmethod
    def _clean_color(value: str | None, fallback: str | None = None) -> str | None:
        return clean_color(value, fallback)

    def _apply_stroke_opacity(self, paint, opacity: float):
        return apply_stroke_opacity(paint, opacity)

    def _descriptor_is_mesh(self, descriptor: Any) -> bool:
        return isinstance(descriptor, MeshGradientDescriptor)

    def _get_pattern_processor(self, services: ConversionServices):
        processor = services.resolve("pattern_processor")
        if processor is None and services.pattern_service is not None:
            processor = getattr(services.pattern_service, "processor", None)
        return processor

    def _ensure_paint_policy(self, metadata: dict[str, Any], role: str) -> dict[str, Any]:
        policy = metadata.setdefault("policy", {})
        paint_policy = policy.setdefault("paint", {})
        entry = paint_policy.setdefault(role, {})
        return entry

    def _maybe_set_geometry_fallback(self, metadata: dict[str, Any], fallback: str) -> None:
        normalized = geometry_fallback_for(fallback)
        if normalized is None:
            return
        geometry_policy = metadata.setdefault("policy", {}).setdefault("geometry", {})
        if geometry_policy.get("suggest_fallback") is None:
            geometry_policy["suggest_fallback"] = normalized
            tracer = self._tracer
            if tracer is not None:
                tracer.record_stage_event(
                    stage="geometry",
                    action="fallback_requested",
                    metadata={"fallback": normalized},
                )

    def _record_gradient_metadata(
        self,
        *,
        gradient_id: str,
        descriptor: GradientDescriptor,
        gradient_service: Any,
        services: ConversionServices,
        metadata: dict[str, Any],
        role: str,
        context: Any | None,
    ) -> None:
        stop_count = len(getattr(descriptor, "stops", ()))
        descriptor_colors = self._descriptor_stop_colors(descriptor)
        gradient_kind = "linear" if isinstance(descriptor, LinearGradientDescriptor) else "radial"
        analysis_entry: dict[str, Any] = {
            "id": gradient_id,
            "type": gradient_kind,
            "stop_count": stop_count,
            "powerpoint_compatible": True,
            "complexity": "unknown",
        }

        transform = getattr(descriptor, "transform", None)
        if isinstance(transform, tuple) and len(transform) == 6:
            analysis_entry["has_transforms"] = not matrix_tuple_is_identity(transform)

        if descriptor_colors:
            analysis_entry["colors_used"] = descriptor_colors

        processor = self._get_gradient_processor(services)
        analysis = None
        if processor is not None and gradient_service is not None:
            try:
                gradient_element = gradient_service.as_element(descriptor)
            except Exception:  # pragma: no cover - defensive
                gradient_element = None
            if gradient_element is not None:
                try:
                    analysis = processor.analyze_gradient_element(gradient_element, context)
                except Exception:  # pragma: no cover - defensive
                    analysis = None

        colors_from_analysis = None
        color_stats = None
        if analysis is not None:
            analysis_entry["type"] = getattr(analysis, "gradient_type", analysis_entry["type"])
            complexity_attr = getattr(analysis, "complexity", None)
            if complexity_attr is not None:
                analysis_entry["complexity"] = getattr(complexity_attr, "value", str(complexity_attr))
            stop_count_attr = getattr(analysis, "stop_count", None)
            if stop_count_attr is not None:
                analysis_entry["stop_count"] = stop_count_attr
            has_transform_attr = getattr(analysis, "has_transforms", None)
            if has_transform_attr is not None:
                analysis_entry["has_transforms"] = has_transform_attr
            analysis_entry["powerpoint_compatible"] = getattr(analysis, "powerpoint_compatible", True)

            optimizations = getattr(analysis, "optimization_opportunities", None)
            if optimizations:
                analysis_entry["optimizations"] = [getattr(opt, "value", str(opt)) for opt in optimizations]

            metrics = getattr(analysis, "metrics", None)
            if metrics is not None:
                analysis_entry["metrics"] = {
                    "stop_count": getattr(metrics, "stop_count", None),
                    "color_complexity": getattr(metrics, "color_complexity", None),
                    "transform_complexity": getattr(metrics, "transform_complexity", None),
                    "memory_usage": getattr(metrics, "memory_usage", None),
                    "processing_time": getattr(metrics, "processing_time", None),
                }

            colors_from_analysis = getattr(analysis, "colors_used", None)
            if colors_from_analysis:
                analysis_entry["colors_used"] = list(colors_from_analysis)

            color_spaces = getattr(analysis, "color_spaces_used", None)
            if color_spaces:
                analysis_entry["color_spaces_used"] = list(color_spaces)

            color_stats = getattr(analysis, "color_statistics", None)
            if isinstance(color_stats, dict) and color_stats:
                analysis_entry["color_statistics"] = color_stats

        metadata.setdefault("paint_analysis", {}).setdefault(role, {})["gradient"] = analysis_entry

        paint_policy = self._ensure_paint_policy(metadata, role)
        paint_policy.setdefault("type", "gradient")
        paint_policy.setdefault("id", gradient_id)
        paint_policy.setdefault("complexity", analysis_entry.get("complexity", "unknown"))

        palette_source = colors_from_analysis or analysis_entry.get("colors_used")
        if palette_source:
            paint_policy.setdefault("palette", list(palette_source))

        if isinstance(color_stats, dict):
            recommended_space = color_stats.get("recommended_space")
            if recommended_space:
                paint_policy.setdefault("recommended_color_space", recommended_space)

        if analysis is not None:
            complexity = getattr(analysis, "complexity", None)
            # Keep gradient fallback decisions tied to demonstrated structural complexity.
            # The processor's generic "powerpoint_compatible" flag is conservative and
            # marks several supported features (e.g. spreadMethod/gradientUnits) as
            # incompatible, which can force unnecessary EMF fallback.
            if complexity in {GradientComplexity.COMPLEX, GradientComplexity.UNSUPPORTED}:
                paint_policy["suggest_fallback"] = FALLBACK_EMF
                self._maybe_set_geometry_fallback(metadata, FALLBACK_EMF)

        tracer = self._tracer
        if tracer is not None:
            decision = "emf" if paint_policy.get("suggest_fallback") == FALLBACK_EMF else "native"
            tracer.record_paint_decision(
                paint_type="gradient",
                paint_id=gradient_id,
                decision=decision,
                metadata={
                    "analysis": analysis_entry,
                    "policy": paint_policy,
                },
            )

    def _record_mesh_gradient_metadata(
        self,
        *,
        gradient_id: str,
        descriptor: MeshGradientDescriptor,
        services: ConversionServices,
        metadata: dict[str, Any],
        role: str,
        context: Any | None,
    ) -> None:
        analysis_entry: dict[str, Any] = {
            "id": gradient_id,
            "type": "mesh",
            "mesh_rows": descriptor.rows,
            "mesh_columns": descriptor.columns,
            "patch_count": descriptor.patch_count,
            "stop_count": descriptor.stop_count,
            "powerpoint_compatible": False,
        }
        if descriptor.colors:
            analysis_entry["colors_used"] = list(descriptor.colors)

        metadata.setdefault("paint_analysis", {}).setdefault(role, {})["gradient"] = analysis_entry

        paint_policy = self._ensure_paint_policy(metadata, role)
        paint_policy.setdefault("type", "gradient")
        paint_policy.setdefault("id", gradient_id)
        paint_policy["gradient_kind"] = "mesh"
        paint_policy["suggest_fallback"] = FALLBACK_EMF
        paint_policy["patch_count"] = descriptor.patch_count
        self._maybe_set_geometry_fallback(metadata, FALLBACK_EMF)

        tracer = self._tracer
        if tracer is not None:
            tracer.record_paint_decision(
                paint_type="gradient",
                paint_id=gradient_id,
                decision="emf",
                metadata={
                    "mesh_rows": descriptor.rows,
                    "mesh_columns": descriptor.columns,
                    "patch_count": descriptor.patch_count,
                },
            )

    def _record_pattern_metadata(
        self,
        *,
        pattern_id: str,
        descriptor: PatternDescriptor,
        pattern_service: Any,
        services: ConversionServices,
        metadata: dict[str, Any],
        role: str,
        context: Any | None,
    ) -> None:
        analysis_entry: dict[str, Any] = {
            "id": pattern_id,
            "type": PatternType.CUSTOM.value,
            "complexity": PatternComplexity.SIMPLE.value,
            "child_count": len(descriptor.children),
            "powerpoint_compatible": True,
            "emf_fallback_recommended": False,
        }

        geometry_entry = {
            "tile_width": descriptor.width,
            "tile_height": descriptor.height,
            "units": descriptor.units,
            "content_units": descriptor.content_units,
        }
        if descriptor.transform and not matrix_tuple_is_identity(descriptor.transform):
            geometry_entry["transform_matrix"] = descriptor.transform
        analysis_entry["geometry"] = geometry_entry

        processor = self._get_pattern_processor(services)
        analysis = None
        if processor is not None and pattern_service is not None:
            try:
                pattern_element = pattern_service.as_element(descriptor)
            except Exception:  # pragma: no cover - defensive
                pattern_element = None
            if pattern_element is not None:
                try:
                    analysis = processor.analyze_pattern_element(pattern_element, context)
                except Exception:  # pragma: no cover - defensive
                    analysis = None

        colors = None
        color_stats = None
        preset_candidate = None
        if analysis is not None:
            pattern_type = getattr(analysis, "pattern_type", None)
            if pattern_type is not None:
                analysis_entry["type"] = getattr(pattern_type, "value", str(pattern_type))

            complexity_attr = getattr(analysis, "complexity", None)
            if complexity_attr is not None:
                analysis_entry["complexity"] = getattr(complexity_attr, "value", str(complexity_attr))

            analysis_entry["child_count"] = getattr(analysis, "child_count", analysis_entry["child_count"])
            analysis_entry["powerpoint_compatible"] = getattr(analysis, "powerpoint_compatible", True)
            analysis_entry["emf_fallback_recommended"] = getattr(analysis, "emf_fallback_recommended", False)

            geometry = getattr(analysis, "geometry", None)
            if geometry is not None:
                geometry_entry = {
                    "tile_width": getattr(geometry, "tile_width", None),
                    "tile_height": getattr(geometry, "tile_height", None),
                    "aspect_ratio": getattr(geometry, "aspect_ratio", None),
                    "units": getattr(geometry, "units", None),
                    "content_units": getattr(geometry, "content_units", None),
                    "transform_matrix": getattr(geometry, "transform_matrix", None),
                }
                analysis_entry["geometry"] = geometry_entry

            colors = getattr(analysis, "colors_used", None)
            if colors:
                analysis_entry["colors_used"] = list(colors)

            color_stats = getattr(analysis, "color_statistics", None)
            if isinstance(color_stats, dict) and color_stats:
                analysis_entry["color_statistics"] = color_stats

            preset_candidate = getattr(analysis, "preset_candidate", None)
            if preset_candidate:
                analysis_entry["preset_candidate"] = preset_candidate

        metadata.setdefault("paint_analysis", {}).setdefault(role, {})["pattern"] = analysis_entry

        paint_policy = self._ensure_paint_policy(metadata, role)
        paint_policy.setdefault("type", "pattern")
        paint_policy.setdefault("id", pattern_id)
        paint_policy.setdefault("complexity", analysis_entry.get("complexity", PatternComplexity.SIMPLE.value))

        if colors:
            paint_policy.setdefault("palette", list(colors))
        if preset_candidate:
            paint_policy.setdefault("preset_candidate", preset_candidate)
        if isinstance(color_stats, dict):
            recommended_space = color_stats.get("recommended_space")
            if recommended_space:
                paint_policy.setdefault("recommended_color_space", recommended_space)

        requires_emf = analysis_entry.get("emf_fallback_recommended", False)
        powerpoint_ok = analysis_entry.get("powerpoint_compatible", True)
        if requires_emf or not powerpoint_ok:
            paint_policy["suggest_fallback"] = FALLBACK_EMF
            self._maybe_set_geometry_fallback(metadata, FALLBACK_EMF)

        tracer = self._tracer
        if tracer is not None:
            decision = "emf" if paint_policy.get("suggest_fallback") == FALLBACK_EMF else "native"
            tracer.record_paint_decision(
                paint_type="pattern",
                paint_id=pattern_id,
                decision=decision,
                metadata={
                    "analysis": analysis_entry,
                    "policy": paint_policy,
                },
            )

    # -- gradient helpers ------------------------------------------------

    def _gradient_attr(
        self,
        chain: list[etree._Element],
        attribute: str,
        *,
        default: str | None = None,
    ) -> str | None:
        if attribute == "__tag__":
            return local_name(chain[0].tag)
        for element in chain:
            value = element.get(attribute)
            if value is not None:
                return value
        return default

    def _collect_gradient_stops(
        self,
        chain: list[etree._Element],
        opacity: float,
    ) -> list[GradientStop]:
        for element in chain:
            stops = list(element.findall(".//{http://www.w3.org/2000/svg}stop"))
            if not stops:
                stops = list(element.findall(".//stop"))
            if stops:
                parsed = self._parse_stops(stops, opacity)
                if len(parsed) == 1:
                    first = parsed[0]
                    return [
                        GradientStop(offset=0.0, rgb=first.rgb, opacity=first.opacity),
                        GradientStop(offset=1.0, rgb=first.rgb, opacity=first.opacity),
                    ]
                return parsed
        return []

    def _parse_stops(
        self,
        stops: list[etree._Element],
        opacity: float,
    ) -> list[GradientStop]:
        parsed: list[GradientStop] = []
        for stop in stops:
            offset_str = stop.get("offset", "0")
            offset = parse_offset(offset_str)
            color, stop_opacity = parse_stop_color(stop)
            total_opacity = max(0.0, min(1.0, stop_opacity * opacity))
            parsed.append(GradientStop(offset=offset, rgb=color, opacity=total_opacity))
        parsed.sort(key=lambda stop: stop.offset)
        return parsed

    def _descriptor_stop_colors(self, descriptor: GradientDescriptor) -> list[str]:
        return descriptor_stop_colors(descriptor)

    def _parse_style(self, style: str | None) -> dict[str, str]:
        return parse_style_attr(style)

    def _resolve_gradient_point(
        self,
        chain: list[etree._Element],
        attr_x: str,
        attr_y: str,
        *,
        default: tuple[str, str] | None,
        units: str,
        conversion,
        axis_defaults: tuple[str, str],
    ) -> tuple[float, float]:
        x_value = self._gradient_attr(chain, attr_x, default=default[0] if default else None)
        y_value = self._gradient_attr(chain, attr_y, default=default[1] if default else None)
        return (
            self._resolve_gradient_length(chain, attr_x, x_value, units, conversion, axis_defaults[0]),
            self._resolve_gradient_length(chain, attr_y, y_value, units, conversion, axis_defaults[1]),
        )

    def _resolve_gradient_length(
        self,
        chain: list[etree._Element],
        attribute: str,
        default: str | None,
        units: str,
        conversion,
        axis: str,
    ) -> float:
        value = self._gradient_attr(chain, attribute, default=default)
        if value is None:
            return 0.0
        if units == "userSpaceOnUse":
            px_value = self._to_px(value, conversion, axis)
            if conversion is not None:
                scale = None
                axis_lower = axis.lower()
                if axis_lower.startswith("x") or axis_lower == "width":
                    scale = getattr(conversion, "width", None) or getattr(conversion, "viewport_width", None)
                elif axis_lower.startswith("y") or axis_lower == "height":
                    scale = getattr(conversion, "height", None) or getattr(conversion, "viewport_height", None)
                if scale:
                    return px_value / scale
            return px_value
        return parse_percentage(value)

    def _apply_matrix_to_point(self, matrix: Matrix2D, point: tuple[float, float]) -> tuple[float, float]:
        return apply_matrix_to_point(matrix, point)

    def _matrix2d_to_numpy(self, matrix: Matrix2D | None):
        return matrix2d_to_numpy(matrix)

    def _to_px(self, value: str, conversion, axis: str) -> float:
        if self._unit_converter is None or conversion is None:
            try:
                return float(value)
            except ValueError:
                return 0.0
        try:
            return self._unit_converter.to_px(value, conversion, axis=axis)
        except Exception:
            try:
                return float(value)
            except ValueError:
                return 0.0


__all__ = ["StyleExtractor", "StyleResult"]
