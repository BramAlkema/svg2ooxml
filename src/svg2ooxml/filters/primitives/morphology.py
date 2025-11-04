"""feMorphology filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import build_exporter_hook, parse_number
from svg2ooxml.units.conversion import px_to_emu

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string


@dataclass
class MorphologyParams:
    operator: str
    radius_x: float
    radius_y: float


class MorphologyFilter(Filter):
    primitive_tags = ("feMorphology",)
    filter_type = "morphology"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive)
        radius_max = max(params.radius_x, params.radius_y)
        metadata = {
            "filter_type": self.filter_type,
            "operator": params.operator,
            "radius_x": params.radius_x,
            "radius_y": params.radius_y,
            "radius_max": radius_max,
        }

        if params.operator == "erode":
            metadata["effect"] = "soft_edge"
            if radius_max <= 0:
                metadata["native_support"] = False
                metadata["reason"] = "zero_radius"
                return FilterResult(success=True, drawingml="", metadata=metadata)

            radius_emu = int(px_to_emu(radius_max))
            metadata["radius_emu"] = radius_emu
            metadata["native_support"] = True

            effectLst = a_elem("effectLst")
            a_sub(effectLst, "softEdge", rad=radius_emu)
            drawingml = to_string(effectLst)

            return FilterResult(success=True, drawingml=drawingml, metadata=metadata)

        if params.operator == "dilate":
            metadata["effect"] = "glow"
            if radius_max <= 0:
                metadata["native_support"] = False
                metadata["reason"] = "zero_radius"
                return FilterResult(success=True, drawingml="", metadata=metadata)

            policy_hint = self._policy_hint(context)
            color_hex, alpha, strategy = self._resolve_glow_colour(primitive, context, policy_hint)

            effective_radius = radius_max
            max_policy_radius = policy_hint.get("max_glow_radius") if isinstance(policy_hint, dict) else None
            if isinstance(max_policy_radius, (int, float)) and max_policy_radius >= 0:
                if radius_max > float(max_policy_radius):
                    effective_radius = float(max_policy_radius)
                    metadata["clamped_radius"] = effective_radius

            max_policy_alpha = policy_hint.get("max_glow_alpha") if isinstance(policy_hint, dict) else None
            if isinstance(max_policy_alpha, (int, float)):
                max_alpha = max(0.0, min(float(max_policy_alpha), 1.0))
                if alpha > max_alpha:
                    alpha = max_alpha
                    metadata["alpha_clamped"] = True

            alpha = max(0.0, min(alpha, 1.0))

            radius_emu = int(px_to_emu(effective_radius))
            alpha_val = int(alpha * 100000)

            if policy_hint:
                metadata["policy"] = dict(policy_hint)

            metadata.update(
                {
                    "color": color_hex,
                    "alpha": alpha,
                    "color_strategy": strategy,
                    "radius_emu": radius_emu,
                    "radius_effective": effective_radius,
                    "native_support": True,
                }
            )

            effectLst = a_elem("effectLst")
            glow = a_sub(effectLst, "glow", rad=radius_emu)
            srgbClr = a_sub(glow, "srgbClr", val=color_hex)
            a_sub(srgbClr, "alpha", val=alpha_val)
            drawingml = to_string(effectLst)

            return FilterResult(success=True, drawingml=drawingml, metadata=metadata)

        metadata["effect"] = "unknown"
        drawingml = build_exporter_hook(
            "morphology",
            {
                "operator": params.operator,
                "radius_x": params.radius_x,
                "radius_y": params.radius_y,
            },
        )
        return FilterResult(success=True, drawingml=drawingml, metadata=metadata)

    def _parse_params(self, primitive: etree._Element) -> MorphologyParams:
        operator = (primitive.get("operator") or "erode").strip().lower()
        radius = (primitive.get("radius") or "0").strip()
        if " " in radius:
            rx_str, ry_str = radius.split(" ", 1)
        else:
            rx_str = ry_str = radius
        radius_x = max(0.0, parse_number(rx_str))
        radius_y = max(0.0, parse_number(ry_str))
        if operator not in {"erode", "dilate"}:
            operator = "erode"
        return MorphologyParams(operator=operator, radius_x=radius_x, radius_y=radius_y)

    # ------------------------------------------------------------------
    # Colour helpers
    # ------------------------------------------------------------------

    def _resolve_glow_colour(
        self,
        primitive: etree._Element,
        context: FilterContext,
        policy_hint: dict[str, float | str | bool] | None,
    ) -> tuple[str, float, str]:
        style_map = self._parse_style(primitive.get("style"))
        pipeline = context.pipeline_state or {}
        options = context.options if isinstance(context.options, dict) else {}

        preferred = ""
        if isinstance(policy_hint, dict):
            raw_pref = policy_hint.get("preferred_glow_strategy")
            if isinstance(raw_pref, str):
                preferred = raw_pref.strip().lower()
        if preferred not in {"source", "flood", "style"}:
            preferred = "inherit"

        pipeline_entry = self._pipeline_colour(primitive.get("in"), pipeline)
        flood_candidates = [
            ("attribute:flood-color", primitive.get("flood-color")),
            ("style:flood-color", style_map.get("flood-color")),
        ]
        source_candidates = [
            pipeline_entry,
            ("attribute:color", primitive.get("color")),
        ]
        style_candidates = [
            ("style:color", style_map.get("color")),
        ]
        option_candidates = [
            ("options:fill_color", self._as_colour_token(options.get("fill_color"))),
            ("options:stroke_color", self._as_colour_token(options.get("stroke_color"))),
        ]

        order_map = {
            "flood": [flood_candidates, source_candidates, style_candidates, option_candidates],
            "style": [style_candidates, flood_candidates, source_candidates, option_candidates],
            "source": [source_candidates, flood_candidates, style_candidates, option_candidates],
            "inherit": [source_candidates, flood_candidates, style_candidates, option_candidates],
        }

        ordered_candidates = []
        seen: set[tuple[str, str]] = set()
        for group in order_map.get(preferred, order_map["inherit"]):
            for entry in group:
                if not isinstance(entry, tuple) or len(entry) != 2:
                    continue
                name, value = entry
                if not value:
                    continue
                norm = value.strip()
                if not norm:
                    continue
                key = (name, norm)
                if key in seen:
                    continue
                seen.add(key)
                ordered_candidates.append((name, norm))

        color_hex = None
        strategy = "default:white"
        for strat, candidate in ordered_candidates:
            normalized = self._normalize_colour(candidate)
            if normalized:
                color_hex = normalized
                strategy = strat
                break

        if color_hex is None:
            color_hex = "FFFFFF"

        alpha_candidates = [
            primitive.get("flood-opacity"),
            primitive.get("opacity"),
            style_map.get("flood-opacity"),
            style_map.get("opacity"),
            options.get("fill_opacity"),
            policy_hint.get("max_glow_alpha") if isinstance(policy_hint, dict) else None,
        ]
        alpha = self._resolve_alpha(alpha_candidates)

        pipeline_alpha = self._pipeline_alpha(primitive.get("in"), pipeline)
        if pipeline_alpha is not None and alpha is None:
            alpha = pipeline_alpha

        if alpha is None:
            alpha = 1.0

        return color_hex, alpha, strategy

    def _parse_style(self, value: str | None) -> dict[str, str]:
        if not value:
            return {}
        properties: dict[str, str] = {}
        for part in value.split(";"):
            if ":" not in part:
                continue
            key, val = part.split(":", 1)
            properties[key.strip()] = val.strip()
        return properties

    def _normalize_colour(self, token: str | None) -> str | None:
        if not token:
            return None
        value = token.strip().lstrip("#")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        if len(value) != 6:
            return None
        try:
            int(value, 16)
        except ValueError:
            return None
        return value.upper()

    def _as_colour_token(self, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return None

    def _resolve_alpha(self, candidates: list[object]) -> float | None:
        for candidate in candidates:
            if candidate is None:
                continue
            try:
                alpha_value = float(str(candidate))
            except (ValueError, TypeError):
                continue
            if alpha_value < 0.0:
                alpha_value = 0.0
            if alpha_value > 1.0:
                alpha_value = 1.0
            return alpha_value
        return None

    def _pipeline_colour(
        self,
        input_name: str | None,
        pipeline: dict[str, FilterResult],
    ) -> tuple[str, str | None]:
        if not input_name:
            return ("pipeline:default_input", None)
        result = pipeline.get(input_name)
        if not result:
            return ("pipeline:missing", None)
        metadata = result.metadata or {}
        for key in ("flood_color", "color", "fill_color"):
            candidate = metadata.get(key)
            if candidate:
                return (f"pipeline:{key}", candidate)
        return ("pipeline:metadata", None)

    def _pipeline_alpha(
        self,
        input_name: str | None,
        pipeline: dict[str, FilterResult],
    ) -> float | None:
        if not input_name:
            return None
        result = pipeline.get(input_name)
        if not result:
            return None
        metadata = result.metadata or {}
        for key in ("opacity", "alpha"):
            candidate = metadata.get(key)
            if candidate is not None:
                try:
                    return float(candidate)
                except (ValueError, TypeError):
                    continue
        return None

    def _policy_hint(self, context: FilterContext) -> dict[str, float | str | bool]:
        options = context.options if isinstance(context.options, dict) else {}
        policy = options.get("policy")
        hint: dict[str, float | str | bool] = {}

        if isinstance(policy, dict):
            hint = {}
            if "max_glow_radius" in policy:
                try:
                    hint["max_glow_radius"] = float(policy["max_glow_radius"])
                except (TypeError, ValueError):
                    pass
            if "max_glow_alpha" in policy:
                try:
                    hint["max_glow_alpha"] = float(policy["max_glow_alpha"])
                except (TypeError, ValueError):
                    pass
            if "preferred_glow_strategy" in policy:
                strategy = policy.get("preferred_glow_strategy")
                if isinstance(strategy, str):
                    hint["preferred_glow_strategy"] = strategy
        preferred = hint.get("preferred_glow_strategy")
        if not preferred:
            strategy = options.get("preferred_glow_strategy")
            if isinstance(strategy, str):
                hint["preferred_glow_strategy"] = strategy
        return hint


__all__ = ["MorphologyFilter"]
