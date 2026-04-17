"""Text conversion coordinator — delegates to sub-modules for layout and font metrics."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.common.geometry.algorithms import CurveTextPositioner, PathSamplingMethod
from svg2ooxml.core.ir.font_metrics import (
    estimate_run_width as _estimate_run_width,
)
from svg2ooxml.core.ir.smart_font_bridge import SmartFontBridge
from svg2ooxml.core.ir.text.font_metrics import (
    FONT_FALLBACKS,
    apply_text_decision,
    coerce_hex_color,
    create_run_from_style,
    merge_runs,
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
    record_text_path_reference,
    resolve_text_length,
    resvg_text_anchor,
    resvg_text_direction,
    resvg_text_origin,
    text_scale_for_coord_space,
)
from svg2ooxml.core.ir.text_pipeline import TextConversionPipeline
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.geometry import Point
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame
from svg2ooxml.policy.text_policy import TextPolicyDecision

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.ir.context import IRConverterContext


class TextConverter:
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
        for attr_name in ("dx", "dy", "rotate"):
            raw = element.get(attr_name, "").strip()
            if raw:
                try:
                    vals = [float(v) for v in raw.replace(",", " ").split() if v]
                    if vals:
                        _per_char_attrs[attr_name] = vals
                except ValueError:
                    pass
        # x/y arrays (multiple values = per-character absolute positioning)
        for attr_name in ("x", "y"):
            raw = element.get(attr_name, "").strip()
            if raw and " " in raw:
                try:
                    vals = [float(v) for v in raw.replace(",", " ").split() if v]
                    if len(vals) > 1:
                        _per_char_attrs[f"abs_{attr_name}"] = vals
                except ValueError:
                    pass
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
            try:
                target_width = float(text_length_attr) * text_scale
                char_count = len(text_content.strip())
                if char_count > 1 and target_width > 0:
                    metadata["_text_length_target"] = target_width
                    length_adjust = (
                        element.get("lengthAdjust", "spacing").strip().lower()
                    )
                    metadata["_length_adjust"] = length_adjust
            except ValueError:
                pass

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
    # Positioned text (multi-tspan)
    # ------------------------------------------------------------------

    def _needs_positioned_text(self, element: etree._Element) -> bool:
        for node in element.iter():
            tag = self._context.local_name(getattr(node, "tag", "")).lower()
            if tag == "tspan":
                if any(node.get(attr) for attr in ("x", "y", "dx", "dy")):
                    return True
                continue
            if tag != "text":
                continue
            if node.get("dx") or node.get("dy"):
                return True
            for attr in ("x", "y"):
                raw = node.get(attr)
                if raw and len(raw.replace(",", " ").split()) > 1:
                    return True
        return False

    def _convert_positioned_text(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        base_style: Mapping[str, Any],
        run_metadata: Mapping[str, Any],
    ) -> list[TextFrame]:
        segments = self._collect_positioned_segments(element, base_style)
        if not segments:
            return []

        frames: list[TextFrame] = []
        font_service = self._context.services.resolve("font")
        policy_meta_accum: dict[str, Any] = {}
        decision = self._resolve_policy_decision()
        text_scale = text_scale_for_coord_space(coord_space)

        # Extract text direction
        direction = base_style.get("direction") or element.get("direction") or None
        if isinstance(direction, str):
            direction = (
                direction.strip().lower()
                if direction.strip().lower() in ("rtl", "ltr")
                else None
            )

        for text, style, x, y in segments:
            run = self._create_run_from_style(text, style)
            if not run.text:
                continue
            run = scale_run_metrics(run, text_scale)
            updated, run_policy = self.apply_policy(run)
            if run_policy:
                policy_meta_accum.update(run_policy)

            origin_x, origin_y = coord_space.apply_point(x, y)
            bbox = estimate_text_bbox(
                [updated], origin_x, origin_y, font_service=font_service
            )

            metadata: dict[str, Any] = dict(run_metadata)
            self._context.attach_policy_metadata(metadata, "text")
            if policy_meta_accum:
                policy_meta = metadata.setdefault("policy", {}).setdefault("text", {})
                policy_meta.update(policy_meta_accum)

            frame = TextFrame(
                origin=Point(origin_x, origin_y),
                anchor=TextAnchor.START,
                bbox=bbox,
                runs=[updated],
                baseline_shift=0.0,
                direction=direction,
                metadata=metadata,
            )
            if self._pipeline is not None:
                frame = self._pipeline.plan_frame(frame, [updated], decision)
            if self._smart_font_bridge is not None:
                frame = self._smart_font_bridge.enhance_frame(
                    frame, [updated], decision
                )

            self._context.trace_geometry_decision(element, "native", frame.metadata)
            frames.append(frame)

        return frames

    def _collect_positioned_segments(
        self,
        element: etree._Element,
        base_style: Mapping[str, Any],
    ) -> list[tuple[str, Mapping[str, Any], float, float]]:
        segments: list[tuple[str, Mapping[str, Any], float, float]] = []
        font_service = self._context.services.resolve("font")
        current_x = 0.0
        current_y = 0.0

        def apply_segment(
            text: str,
            style: Mapping[str, Any],
            x_values: list[float],
            y_values: list[float],
            dx_values: list[float],
            dy_values: list[float],
            *,
            preserve_space: bool,
        ) -> None:
            nonlocal current_x, current_y
            normalized = normalize_positioned_text(text, preserve_space)
            if not normalized:
                return

            run = self._create_run_from_style(normalized, style)
            per_char = (
                max(len(x_values), len(y_values), len(dx_values), len(dy_values)) > 1
            )

            if per_char:
                for idx, ch in enumerate(normalized):
                    if idx < len(x_values):
                        current_x = x_values[idx]
                    if idx < len(y_values):
                        current_y = y_values[idx]
                    if idx < len(dx_values):
                        current_x += dx_values[idx]
                    if idx < len(dy_values):
                        current_y += dy_values[idx]

                    if ch.strip():
                        segments.append((ch, style, current_x, current_y))
                    current_x += _estimate_run_width(ch, run, font_service)
                return

            if x_values:
                current_x = x_values[0]
            if y_values:
                current_y = y_values[0]
            if dx_values:
                current_x += dx_values[0]
            if dy_values:
                current_y += dy_values[0]

            if normalized.strip():
                segments.append((normalized, style, current_x, current_y))
            current_x += _estimate_run_width(normalized, run, font_service)

        def visit(
            node: etree._Element,
            style: Mapping[str, Any],
            preserve_space: bool,
        ) -> None:
            nonlocal current_x, current_y
            local = self._context.local_name(getattr(node, "tag", "")).lower()
            node_style = style
            if local == "tspan":
                node_style = self._context.style_resolver.compute_text_style(
                    node,
                    context=self._context.css_context,
                    parent_style=dict(style),
                )

            font_size_pt = float(node_style.get("font_size_pt", 12.0))
            x_values = parse_text_length_list(
                node.get("x"), font_size_pt, axis="x", context=self._context
            )
            y_values = parse_text_length_list(
                node.get("y"), font_size_pt, axis="y", context=self._context
            )
            dx_values = parse_text_length_list(
                node.get("dx"), font_size_pt, axis="x", context=self._context
            )
            dy_values = parse_text_length_list(
                node.get("dy"), font_size_pt, axis="y", context=self._context
            )

            xml_space = node.get("{http://www.w3.org/XML/1998/namespace}space")
            node_preserve = preserve_space or (xml_space == "preserve")
            if node.text:
                apply_segment(
                    node.text,
                    node_style,
                    x_values,
                    y_values,
                    dx_values,
                    dy_values,
                    preserve_space=node_preserve,
                )

            for child in node:
                visit(child, node_style, node_preserve)
                if child.tail:
                    apply_segment(
                        child.tail,
                        node_style,
                        [],
                        [],
                        [],
                        [],
                        preserve_space=node_preserve,
                    )

        visit(element, base_style, False)
        return segments

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

    def _compute_text_style_with_inheritance(
        self, element: etree._Element
    ) -> dict[str, Any]:
        parent_style: dict[str, Any] | None = None
        parent = element.getparent()
        if isinstance(parent, etree._Element) and isinstance(parent.tag, str):
            parent_style = self._compute_text_style_with_inheritance(parent)
        return self._context.style_resolver.compute_text_style(
            element,
            context=self._context.css_context,
            parent_style=parent_style,
        )

    def _collect_text_runs(
        self,
        element: etree._Element,
        base_style: Mapping[str, Any],
    ) -> tuple[list[Run], dict[str, Any]]:
        segments: list[tuple[Mapping[str, Any], str]] = []
        metadata: dict[str, Any] = {}

        def visit(
            node: etree._Element, style: Mapping[str, Any], preserve_space: bool
        ) -> None:
            xml_space = node.get("{http://www.w3.org/XML/1998/namespace}space")
            node_preserve = preserve_space or (xml_space == "preserve")
            text_segment = normalize_text_segment(
                node.text, preserve_space=node_preserve
            )
            if text_segment:
                segments.append((dict(style), text_segment))

            for child in node:
                local = self._context.local_name(getattr(child, "tag", "")).lower()
                if local == "tspan":
                    child_style = self._context.style_resolver.compute_text_style(
                        child,
                        context=self._context.css_context,
                        parent_style=style,
                    )
                    visit(child, child_style, node_preserve)
                elif local == "textpath":
                    child_style = self._context.style_resolver.compute_text_style(
                        child,
                        context=self._context.css_context,
                        parent_style=style,
                    )
                    href = child.get("{http://www.w3.org/1999/xlink}href") or child.get(
                        "href"
                    )
                    record_text_path_reference(
                        href, metadata,
                        context=self._context,
                        text_path_positioner=self._text_path_positioner,
                    )
                    visit(child, child_style, node_preserve)
                else:
                    visit(child, style, node_preserve)
                tail_segment = normalize_text_segment(
                    child.tail, preserve_space=node_preserve
                )
                if tail_segment:
                    segments.append((dict(style), tail_segment))

        visit(element, base_style, False)

        runs: list[Run] = []
        for style, segment in segments:
            run = self._create_run_from_style(segment, style)
            if run.text:
                runs.append(run)
        runs = merge_runs(runs)
        return runs, metadata

    def _create_run_from_style(self, text: str, style: Mapping[str, Any]) -> Run:
        return create_run_from_style(
            text, style, resolve_text_length_fn=self._resolve_text_length
        )

    def _resolve_text_length(
        self,
        value: str | None,
        *,
        axis: str,
        font_size_pt: float,
    ) -> float:
        return resolve_text_length(
            value, axis=axis, font_size_pt=font_size_pt, context=self._context
        )

    def _attach_resvg_text_metadata(
        self,
        resvg_node: Any,
        metadata: dict[str, Any],
        *,
        text_scale: float = 1.0,
    ) -> None:
        if not hasattr(resvg_node, "text_content"):
            return
        try:
            from svg2ooxml.core.resvg.text.drawingml_generator import (
                DrawingMLTextGenerator,
            )
            from svg2ooxml.core.resvg.text.layout_analyzer import TextLayoutAnalyzer
        except Exception:
            return

        resvg_meta: dict[str, Any] = metadata.setdefault("resvg_text", {})
        analysis = TextLayoutAnalyzer().analyze(resvg_node)
        resvg_meta["complexity"] = analysis.complexity
        if analysis.details:
            resvg_meta["details"] = analysis.details
        resvg_meta["is_plain"] = analysis.is_plain

        if metadata.get("text_path_id"):
            resvg_meta["strategy"] = "text_path"
            return
        if not analysis.is_plain:
            resvg_meta["strategy"] = "emf"
            return

        paint_resolver = None
        tree = getattr(self._context, "resvg_tree", None)
        if tree is not None:
            from svg2ooxml.paint.resvg_bridge import _resolve_paint_reference

            def paint_resolver(ref):
                return _resolve_paint_reference(ref, tree)

        generator = DrawingMLTextGenerator(
            font_service=self._context.services.resolve("font"),
            embedding_engine=self._context.services.resolve("font_embedding"),
            paint_resolver=paint_resolver,
            text_scale=text_scale,
        )
        try:
            runs_xml = generator.generate_runs_xml(resvg_node)
        except Exception:
            resvg_meta["strategy"] = "error"
            return

        if runs_xml:
            resvg_meta["strategy"] = "runs"
            resvg_meta["runs_xml"] = runs_xml
        else:
            resvg_meta["strategy"] = "empty"


# ---------------------------------------------------------------
# Module-level backward-compat alias
# ---------------------------------------------------------------


def _parse_float(value: str | None, *, default: float | None = None) -> float | None:
    """Backward-compatible alias -- delegates to sub-module."""
    return _module_parse_float(value, default=default)


__all__ = ["TextConverter", "FONT_FALLBACKS"]
