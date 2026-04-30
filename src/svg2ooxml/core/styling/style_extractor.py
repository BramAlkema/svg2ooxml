"""Style extraction helpers for IR conversion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.color import parse_color
from svg2ooxml.color.utils import rgb_object_to_hex
from svg2ooxml.common.conversions.opacity import parse_opacity
from svg2ooxml.common.math_utils import finite_float
from svg2ooxml.common.style.resolver import StyleResolver
from svg2ooxml.core.styling.paint import maybe_set_geometry_fallback
from svg2ooxml.core.styling.paint.gradient import (
    build_gradient_paint,
    record_gradient_metadata,
    record_mesh_gradient_metadata,
)
from svg2ooxml.core.styling.paint.pattern import (
    build_pattern_paint,
    record_pattern_metadata,
)
from svg2ooxml.core.styling.style_helpers import (
    extract_url_id as _extract_url_id,
)
from svg2ooxml.core.styling.style_helpers import (
    normalize_hex as _normalize_hex,
)
from svg2ooxml.core.styling.style_helpers import (
    parse_dash_array as _parse_dash_array,
)
from svg2ooxml.core.styling.style_helpers import (
    parse_length as _parse_length,
)
from svg2ooxml.core.styling.style_helpers import (
    parse_optional_float as _parse_optional_float,
)
from svg2ooxml.core.styling.style_helpers import (
    parse_style_attr as _parse_style_attr,
)
from svg2ooxml.drawingml.bridges.resvg_paint_bridge import (
    MeshGradientDescriptor,
)
from svg2ooxml.ir.effects import Effect
from svg2ooxml.ir.paint import (
    GradientPaintRef,
    PatternPaint,
    SolidPaint,
    Stroke,
    StrokeCap,
    StrokeJoin,
)
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


def _style_token(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _resolve_fill_rule(
    element: etree._Element,
    paint_style: dict[str, Any],
) -> str | None:
    candidates = [paint_style.get("fill_rule")]
    current: etree._Element | None = element
    while current is not None:
        candidates.append(current.get("fill-rule"))
        candidates.append(_parse_style_attr(current.get("style")).get("fill-rule"))
        parent = current.getparent()
        current = parent if isinstance(parent, etree._Element) else None

    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        token = candidate.strip().lower()
        if token in {"evenodd", "even-odd"}:
            return "evenodd"
        if token == "nonzero":
            return "nonzero"
    return None


def _split_paint_server_fallback(token: str) -> tuple[str | None, str | None]:
    stripped = token.strip()
    if not stripped.startswith("url("):
        return None, None
    depth = 0
    for index, char in enumerate(stripped):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                paint_server = stripped[: index + 1].strip()
                fallback = stripped[index + 1 :].strip() or None
                return paint_server, fallback
    return stripped, None


def _solid_fallback_paint(token: str | None, opacity: float) -> SolidPaint | None:
    if token is None:
        return None
    stripped = token.strip()
    if not stripped or stripped.lower() == "none":
        return None
    color = parse_color(stripped)
    if color is None or color.a <= 0.0:
        return None
    rgb = rgb_object_to_hex(color, default=None)
    if rgb is None:
        return None
    alpha = max(0.0, min(1.0, float(color.a) * opacity))
    return SolidPaint(rgb=rgb, opacity=alpha)


def _is_empty_pattern_descriptor(descriptor: Any) -> bool:
    try:
        return float(descriptor.width) <= 0.0 or float(descriptor.height) <= 0.0
    except (TypeError, ValueError):
        return False


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

    def extract(
        self,
        element: etree._Element,
        services: ConversionServices,
        *,
        context: Any | None = None,
    ) -> StyleResult:
        paint_style = self._compute_paint_style_with_inheritance(
            element, context=context
        )
        metadata: dict[str, Any] = {}

        fill_opacity = parse_opacity(paint_style.get("fill_opacity"), default=1.0)

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

        opacity = parse_opacity(paint_style.get("opacity"), default=1.0)
        effects = self._resolve_effects(element, services, metadata, context)

        # Parse paint-order (SVG2): "stroke fill markers", "fill stroke", etc.
        paint_order = (
            paint_style.get("paint_order") or element.get("paint-order", "").strip()
        )
        if paint_order and paint_order != "normal":
            metadata["paint_order"] = paint_order

        # Parse mix-blend-mode and isolation
        blend_mode = (
            paint_style.get("mix_blend_mode")
            or element.get("mix-blend-mode", "").strip()
        )
        if blend_mode and blend_mode != "normal":
            metadata["mix_blend_mode"] = blend_mode
        isolation = paint_style.get("isolation") or element.get("isolation", "").strip()
        if isolation == "isolate":
            metadata["isolation"] = "isolate"

        vector_effect = str(paint_style.get("vector_effect") or "none").strip()
        if vector_effect and vector_effect != "none":
            metadata["vector_effect"] = vector_effect

        fill_rule = _resolve_fill_rule(element, paint_style)
        if fill_rule is not None:
            metadata["fill_rule"] = fill_rule

        return StyleResult(
            fill=fill,
            stroke=stroke,
            opacity=opacity,
            effects=effects,
            metadata=metadata,
        )

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

        style = self._resolver.compute_paint_style(
            element, context=context, parent_style=parent_style
        )
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
        paint_server_token, fallback_token = _split_paint_server_fallback(stripped)
        fallback_paint = _solid_fallback_paint(fallback_token, opacity)
        paint_id = _extract_url_id(paint_server_token or stripped)
        if paint_id:
            gradient_service = services.gradient_service
            descriptor = gradient_service.get(paint_id) if gradient_service else None
            if descriptor is not None:
                if isinstance(descriptor, MeshGradientDescriptor):
                    record_mesh_gradient_metadata(
                        gradient_id=paint_id,
                        descriptor=descriptor,
                        services=services,
                        metadata=metadata,
                        role=role,
                        context=context,
                        tracer=self._tracer,
                    )
                    return GradientPaintRef(gradient_id=paint_id, gradient_type="mesh")

                gradient_paint = build_gradient_paint(
                    gradient_id=paint_id,
                    services=services,
                    element=element,
                    opacity=opacity,
                    context=context,
                    unit_converter=self._unit_converter,
                )

                record_gradient_metadata(
                    gradient_id=paint_id,
                    descriptor=descriptor,
                    gradient_service=gradient_service,
                    services=services,
                    metadata=metadata,
                    role=role,
                    context=context,
                    tracer=self._tracer,
                )

                if gradient_paint is not None:
                    return gradient_paint
                return GradientPaintRef(gradient_id=paint_id, gradient_type="auto")
            pattern_service = services.pattern_service
            pattern_descriptor = (
                pattern_service.get(paint_id) if pattern_service else None
            )
            if pattern_descriptor is not None:
                if _is_empty_pattern_descriptor(pattern_descriptor):
                    return fallback_paint
                pattern_paint = build_pattern_paint(
                    pattern_id=paint_id,
                    services=services,
                    element=element,
                    context=context,
                )
                if pattern_paint is not None:
                    record_pattern_metadata(
                        pattern_id=paint_id,
                        descriptor=pattern_descriptor,
                        pattern_service=pattern_service,
                        services=services,
                        metadata=metadata,
                        role=role,
                        context=context,
                        tracer=self._tracer,
                    )
                    return pattern_paint
                return fallback_paint or PatternPaint(pattern_id=paint_id)
            # Unknown paint reference – fall through to solid paint with raw token.
            if fallback_paint is not None:
                return fallback_paint
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
            opacity=1.0,
            services=services,
            context=context,
            metadata=metadata,
            role="stroke",
        )
        if stroke_paint is None:
            return None

        stroke_width = finite_float(
            paint_style.get("stroke_width_px"),
            1.0,
        )
        stroke_width = max(0.0, stroke_width if stroke_width is not None else 1.0)
        join_attr = str(paint_style.get("stroke_linejoin") or "miter").lower()
        cap_attr = str(paint_style.get("stroke_linecap") or "butt").lower()

        stroke_join = {
            "round": StrokeJoin.ROUND,
            "bevel": StrokeJoin.BEVEL,
        }.get(join_attr, StrokeJoin.MITER)

        stroke_cap = {
            "round": StrokeCap.ROUND,
            "square": StrokeCap.SQUARE,
        }.get(cap_attr, StrokeCap.BUTT)

        dash_array = _parse_dash_array(_style_token(paint_style.get("stroke_dasharray")))
        dash_offset = _parse_length(_style_token(paint_style.get("stroke_dashoffset"))) or 0.0
        miter_limit = _parse_optional_float(_style_token(paint_style.get("stroke_miterlimit"))) or 4.0
        stroke_opacity_value = paint_style.get("stroke_opacity", 1.0)
        stroke_opacity = parse_opacity(
            stroke_opacity_value if stroke_opacity_value is not None else 0.0,
            default=1.0,
        )

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
        filter_id = _extract_url_id(filter_attr) or filter_attr

        filter_service = services.filter_service
        if filter_service and hasattr(filter_service, "resolve_effects"):
            try:
                if isinstance(context, dict):
                    filter_context = dict(context)
                else:
                    filter_context = {}
                if "policy" not in filter_context:
                    policy_context = getattr(services, "policy_context", None)
                    if policy_context is None and hasattr(services, "resolve"):
                        policy_context = services.resolve("policy_context")
                    if policy_context is not None and hasattr(policy_context, "get"):
                        filter_policy = policy_context.get("filter")
                        if isinstance(filter_policy, dict) and filter_policy:
                            filter_context["policy"] = dict(filter_policy)
                if self._tracer is not None and "tracer" not in filter_context:
                    filter_context["tracer"] = self._tracer
                filter_context.setdefault("element", element)
                effects = filter_service.resolve_effects(  # type: ignore[call-arg]
                    filter_id,
                    context=filter_context,
                )
                if effects:
                    metadata.setdefault("filter_ids", []).append(filter_id)
                    return list(effects)
            except Exception:  # pragma: no cover - defensive
                pass

        metadata.setdefault("filter_ids", []).append(filter_id)
        return []

    # ------------------------------------------------------------------
    # Thin wrappers — delegate to extracted paint modules while
    # preserving the instance-method interface for existing callers.
    # ------------------------------------------------------------------

    def _maybe_set_geometry_fallback(
        self, metadata: dict[str, Any], fallback: str
    ) -> None:
        maybe_set_geometry_fallback(metadata, fallback, self._tracer)

    def _record_gradient_metadata(
        self,
        *,
        gradient_id: str,
        descriptor,
        gradient_service: Any,
        services: ConversionServices,
        metadata: dict[str, Any],
        role: str,
        context: Any | None,
    ) -> None:
        record_gradient_metadata(
            gradient_id=gradient_id,
            descriptor=descriptor,
            gradient_service=gradient_service,
            services=services,
            metadata=metadata,
            role=role,
            context=context,
            tracer=self._tracer,
        )

    def _record_pattern_metadata(
        self,
        *,
        pattern_id: str,
        descriptor,
        pattern_service: Any,
        services: ConversionServices,
        metadata: dict[str, Any],
        role: str,
        context: Any | None,
    ) -> None:
        record_pattern_metadata(
            pattern_id=pattern_id,
            descriptor=descriptor,
            pattern_service=pattern_service,
            services=services,
            metadata=metadata,
            role=role,
            context=context,
            tracer=self._tracer,
        )


__all__ = ["StyleExtractor", "StyleResult"]
