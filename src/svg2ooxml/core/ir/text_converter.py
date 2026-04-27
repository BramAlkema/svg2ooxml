"""Text conversion coordinator — delegates to sub-modules for layout and font metrics."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.common.geometry.algorithms import CurveTextPositioner, PathSamplingMethod
from svg2ooxml.core.ir.smart_font_bridge import SmartFontBridge
from svg2ooxml.core.ir.text.font_metrics import (
    FONT_FALLBACKS,
    apply_text_decision,
    coerce_hex_color,
    resvg_color_to_hex,
    run_from_resvg_node,
    runs_compatible,
    scale_run_metrics,
)
from svg2ooxml.core.ir.text.font_metrics import (
    parse_float as _module_parse_float,
)
from svg2ooxml.core.ir.text.layout import (
    apply_text_anchor,
    attach_text_path_metadata,
    estimate_text_bbox,
    normalize_positioned_text,
    normalize_text_segment,
    parse_number_list,
    parse_text_length_list,
    resolve_text_length,
    resvg_text_anchor,
    resvg_text_direction,
    resvg_text_origin,
    text_scale_for_coord_space,
)
from svg2ooxml.core.ir.text_pipeline import TextConversionPipeline
from svg2ooxml.core.ir.text_positioned import PositionedTextMixin
from svg2ooxml.core.ir.text_runs import TextRunsMixin
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.geometry import Point
from svg2ooxml.ir.text import Run, TextFrame
from svg2ooxml.policy.text_policy import TextPolicyDecision

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.ir.context import IRConverterContext


class TextConverter(PositionedTextMixin, TextRunsMixin):
    """Handle text element extraction, policy application, and metadata."""

    def __init__(
        self,
        context: IRConverterContext | Any,
        pipeline: TextConversionPipeline | None = None,
    ) -> None:
        self._context = self._resolve_context(context)
        self._pipeline = pipeline or TextConversionPipeline(
            font_service=self._context.services.resolve("font"),
            embedding_engine=self._context.services.resolve("font_embedding"),
            logger=self._context.logger,
        )
        self._smart_font_bridge = SmartFontBridge(
            self._context.services, self._context.logger
        )
        self._text_path_positioner = CurveTextPositioner(
            PathSamplingMethod.DETERMINISTIC
        )

    # ------------------------------------------------------------------
    # Public surface consumed by IRConverter
    # ------------------------------------------------------------------

    def convert(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        resvg_node: Any | None = None,
    ) -> TextFrame | list[TextFrame] | None:
        if resvg_node is None:
            return None
        return self._convert_resvg_text(
            element=element,
            coord_space=coord_space,
            resvg_node=resvg_node,
        )

    # ------------------------------------------------------------------
    # Resvg-only text conversion
    # ------------------------------------------------------------------

    def _convert_resvg_text(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        resvg_node: Any,
    ) -> TextFrame | None:
        text_content = getattr(resvg_node, "text_content", None) or ""
        if not text_content.strip():
            return None

        run = run_from_resvg_node(resvg_node, text_content)
        text_scale = text_scale_for_coord_space(coord_space)
        from dataclasses import replace as _replace

        # Parse style attribute once for all CSS property lookups below
        style_attr = element.get("style", "")

        lang = element.get("{http://www.w3.org/XML/1998/namespace}lang") or element.get(
            "lang"
        )
        if lang and not run.language:
            run = _replace(run, language=lang.strip())

        # font-variant: small-caps -> cap="small" on rPr
        font_variant = element.get("font-variant", "").strip().lower()
        if not font_variant:
            if "font-variant" in style_attr:
                m = re.search(r"font-variant\s*:\s*([^;]+)", style_attr)
                if m:
                    font_variant = m.group(1).strip().lower()
        if font_variant == "small-caps":
            run = _replace(run, font_variant="small-caps")

        run = scale_run_metrics(run, text_scale)
        updated, run_policy = self.apply_policy(run)
        runs = [updated]

        origin_x, origin_y = resvg_text_origin(resvg_node, coord_space)
        anchor = resvg_text_anchor(resvg_node)
        direction = resvg_text_direction(resvg_node)

        # dominant-baseline / alignment-baseline -> y-offset from real font metrics
        dom_baseline = (element.get("dominant-baseline") or "").strip().lower()
        align_baseline = (element.get("alignment-baseline") or "").strip().lower()
        baseline = dom_baseline or align_baseline
        if baseline and baseline not in ("auto", "alphabetic"):
            from svg2ooxml.drawingml.glyph_renderer import SKIA_AVAILABLE, _get_font

            if SKIA_AVAILABLE:
                _font = _get_font(updated.font_family, updated.font_size_pt)
                _m = _font.getMetrics()
                ascent = abs(_m.fAscent)
                descent = abs(_m.fDescent)
            else:
                ascent = updated.font_size_pt * 0.77
                descent = updated.font_size_pt * 0.23
            if baseline in ("central", "middle"):
                origin_y += (ascent - descent) / 2
            elif baseline == "hanging":
                origin_y += ascent
            elif baseline in ("text-bottom", "after-edge"):
                origin_y -= descent
            elif baseline in ("text-top", "before-edge"):
                origin_y += ascent

        font_service = self._context.services.resolve("font")
        bbox = estimate_text_bbox(
            runs, origin_x, origin_y, font_service=font_service
        )
        bbox = apply_text_anchor(bbox, anchor)

        metadata: dict[str, Any] = {}
        attach_text_path_metadata(
            element, metadata, resvg_node=resvg_node,
            context=self._context,
            text_path_positioner=self._text_path_positioner,
        )
        self._attach_resvg_text_metadata(
            resvg_node,
            metadata,
            text_scale=text_scale,
        )
        self._context.attach_policy_metadata(metadata, "text")
        if font_variant == "small-caps":
            metadata["font_variant"] = "small-caps"

        # writing-mode -> vert attribute on bodyPr
        writing_mode = element.get("writing-mode", "").strip().lower()
        if not writing_mode:
            if "writing-mode" in style_attr:
                wm = re.search(r"writing-mode\s*:\s*([^;]+)", style_attr)
                if wm:
                    writing_mode = wm.group(1).strip().lower()
        # Per-character positioning: dx/dy/x/y/rotate arrays
        _per_char_attrs: dict[str, list[float]] = {}
        for attr_name in ("dx", "dy"):
            raw = element.get(attr_name, "").strip()
            if raw:
                vals = parse_text_length_list(
                    raw,
                    updated.font_size_pt,
                    axis="x" if attr_name == "dx" else "y",
                    context=self._context,
                )
                if vals:
                    _per_char_attrs[attr_name] = vals
        raw_rotate = element.get("rotate", "").strip()
        if raw_rotate:
            vals = parse_number_list(raw_rotate)
            if vals:
                _per_char_attrs["rotate"] = vals
        # x/y arrays (multiple values = per-character absolute positioning)
        for attr_name in ("x", "y"):
            raw = element.get(attr_name, "").strip()
            if raw:
                vals = parse_text_length_list(
                    raw,
                    updated.font_size_pt,
                    axis=attr_name,
                    context=self._context,
                )
                if len(vals) > 1:
                    _per_char_attrs[f"abs_{attr_name}"] = vals
        if _per_char_attrs:
            # Uniform rotation -> xfrm rot on shape (keeps text native)
            rotate_vals = _per_char_attrs.get("rotate")
            if rotate_vals and len(set(rotate_vals)) == 1:
                metadata["text_rotation_deg"] = rotate_vals[0]
                del _per_char_attrs["rotate"]  # consumed

            # If only dx with uniform values, convert to letter_spacing
            # to keep text native + editable (font embedding via FontForge)
            dx_only = (
                "dx" in _per_char_attrs
                and "dy" not in _per_char_attrs
                and "rotate" not in _per_char_attrs
                and "abs_x" not in _per_char_attrs
                and "abs_y" not in _per_char_attrs
            )
            if dx_only:
                dx_vals = _per_char_attrs["dx"]
                if len(dx_vals) >= 1:
                    avg_dx = (sum(dx_vals) / len(dx_vals)) * text_scale
                    is_uniform = (
                        all(
                            abs((v * text_scale) - avg_dx)
                            / max(abs(avg_dx), 0.01)
                            < 0.1
                            for v in dx_vals
                        )
                        if avg_dx != 0
                        else all(abs(v * text_scale) < 0.5 for v in dx_vals)
                    )
                    if is_uniform and abs(avg_dx) > 0.01:
                        base_ls = updated.letter_spacing or 0.0
                        updated = _replace(updated, letter_spacing=base_ls + avg_dx)
                        runs = [updated]
                        _per_char_attrs = {}  # clear -- handled as native spc
            if _per_char_attrs:
                metadata["per_char"] = _per_char_attrs

        # font-stretch -> append width keyword to font family
        font_stretch = element.get("font-stretch", "").strip().lower()
        if not font_stretch:
            if "font-stretch" in style_attr:
                fs = re.search(r"font-stretch\s*:\s*([^;]+)", style_attr)
                if fs:
                    font_stretch = fs.group(1).strip().lower()
        _STRETCH_MAP = {
            "ultra-condensed": " UltraCondensed",
            "extra-condensed": " ExtraCondensed",
            "condensed": " Condensed",
            "semi-condensed": " SemiCondensed",
            "semi-expanded": " SemiExpanded",
            "expanded": " Expanded",
            "extra-expanded": " ExtraExpanded",
            "ultra-expanded": " UltraExpanded",
        }
        suffix = _STRETCH_MAP.get(font_stretch)
        if suffix and updated.font_family:
            updated = _replace(updated, font_family=updated.font_family + suffix)
            runs = [updated]

        # text-decoration: overline (DrawingML has no overline -- store for line shape)
        text_deco = element.get("text-decoration", "").lower()
        if not text_deco:
            if "text-decoration" in style_attr:
                td = re.search(r"text-decoration\s*:\s*([^;]+)", style_attr)
                if td:
                    text_deco = td.group(1).strip().lower()
        if "overline" in text_deco:
            metadata["overline"] = True

        if writing_mode in ("tb", "tb-rl", "vertical-rl"):
            metadata["writing_mode"] = "vert"
        elif writing_mode in ("tb-lr", "vertical-lr"):
            metadata["writing_mode"] = "vert270"

        # textLength -> compute effective letter-spacing
        text_length_attr = element.get("textLength")
        if text_length_attr and text_content.strip():
            target_width = (
                resolve_text_length(
                    text_length_attr,
                    axis="x",
                    font_size_pt=updated.font_size_pt,
                    context=self._context,
                )
                * text_scale
            )
            char_count = len(text_content.strip())
            if char_count > 1 and target_width > 0:
                metadata["_text_length_target"] = target_width
                length_adjust = element.get("lengthAdjust", "spacing").strip().lower()
                metadata["_length_adjust"] = length_adjust

        # Apply textLength letter-spacing using the estimated bbox
        target_width = metadata.pop("_text_length_target", None)
        if target_width is not None and bbox.width > 0:
            char_count = len(text_content.strip())
            if char_count > 1:
                natural_width = bbox.width
                extra_total = target_width - natural_width
                extra_per_gap = extra_total / (char_count - 1)
                base_ls = updated.letter_spacing or 0.0
                updated = _replace(updated, letter_spacing=base_ls + extra_per_gap)
                runs = [updated]

        if run_policy:
            policy_meta = metadata.setdefault("policy", {}).setdefault("text", {})
            policy_meta.update(run_policy)

        frame = TextFrame(
            origin=Point(origin_x, origin_y),
            anchor=anchor,
            bbox=bbox,
            runs=runs,
            baseline_shift=0.0,
            direction=direction,
            metadata=metadata,
        )
        decision = self._resolve_policy_decision()
        if self._pipeline is not None:
            frame = self._pipeline.plan_frame(frame, runs, decision)
        if self._smart_font_bridge is not None:
            frame = self._smart_font_bridge.enhance_frame(frame, runs, decision)

        trace_stage = getattr(self._context, "trace_stage", None)
        if callable(trace_stage):
            trace_stage(
                "text_frame",
                stage="text",
                subject=element.get("id"),
                metadata={
                    "run_count": len(runs),
                    "resvg_only": True,
                    "decision": getattr(decision, "value", decision),
                },
            )
        self._context.trace_geometry_decision(element, "resvg", frame.metadata)
        return frame

    # ------------------------------------------------------------------
    # Policy
    # ------------------------------------------------------------------

    def apply_policy(self, run: Run) -> tuple[Run, dict[str, Any]]:
        policy = self._context.policy_options("text")
        if not policy:
            return run, {}

        decision = self._resolve_policy_decision(policy)
        if decision is not None:
            return apply_text_decision(run, decision)

        return run, {}

    @property
    def pipeline(self) -> TextConversionPipeline:
        return self._pipeline

    @staticmethod
    def _resolve_context(context: IRConverterContext | Any) -> IRConverterContext:
        if hasattr(context, "style_resolver") and hasattr(context, "services"):
            return context
        parent_context = getattr(context, "_context", None)
        if parent_context is not None:
            return parent_context
        raise TypeError(
            "TextConverter expects an IRConverterContext or compatible object."
        )

    # ------------------------------------------------------------------
    # Static method aliases — preserve backward compatibility for tests
    # that call TextConverter._estimate_text_bbox etc. directly.
    # ------------------------------------------------------------------

    _estimate_text_bbox = staticmethod(estimate_text_bbox)
    _apply_text_anchor = staticmethod(apply_text_anchor)
    _text_scale_for_coord_space = staticmethod(text_scale_for_coord_space)
    _scale_run_metrics = staticmethod(scale_run_metrics)
    _runs_compatible = staticmethod(runs_compatible)
    _coerce_hex_color = staticmethod(coerce_hex_color)
    _normalize_text_segment = staticmethod(normalize_text_segment)
    _normalize_positioned_text = staticmethod(normalize_positioned_text)
    _parse_number_list = staticmethod(parse_number_list)
    _resvg_color_to_hex = staticmethod(resvg_color_to_hex)

    # ------------------------------------------------------------------
    # Internal helpers -- thin delegates to sub-modules
    # ------------------------------------------------------------------

    def _resolve_policy_decision(
        self,
        policy: Mapping[str, Any] | None = None,
    ) -> TextPolicyDecision | None:
        options = policy
        if options is None:
            options = self._context.policy_options("text")
        if not isinstance(options, Mapping):
            return None
        candidate = options.get("decision")
        if isinstance(candidate, TextPolicyDecision):
            return candidate
        return None

# ---------------------------------------------------------------
# Module-level backward-compat alias
# ---------------------------------------------------------------


def _parse_float(value: str | None, *, default: float | None = None) -> float | None:
    """Backward-compatible alias -- delegates to sub-module."""
    return _module_parse_float(value, default=default)


__all__ = ["TextConverter", "FONT_FALLBACKS"]
