"""Text conversion helpers extracted from the core converter."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.common.geometry.algorithms import CurveTextPositioner, PathSamplingMethod
from svg2ooxml.core.ir.font_metrics import (
    estimate_run_width as _estimate_run_width,
)
from svg2ooxml.core.ir.font_metrics import (
    resolve_font_metrics as _resolve_font_metrics,
)
from svg2ooxml.core.ir.smart_font_bridge import SmartFontBridge
from svg2ooxml.core.ir.text_pipeline import TextConversionPipeline
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame
from svg2ooxml.policy.constants import FALLBACK_EMF
from svg2ooxml.policy.text_policy import TextPolicyDecision

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.ir.context import IRConverterContext


FONT_FALLBACKS: dict[str, str] = {
    "sans-serif": "Arial",
    "serif": "Times New Roman",
    "monospace": "Courier New",
    "cursive": "Comic Sans MS",
    "fantasy": "Impact",
    "svgfreesansascii": "Arial",
}


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
        self._smart_font_bridge = SmartFontBridge(self._context.services, self._context.logger)
        self._text_path_positioner = CurveTextPositioner(PathSamplingMethod.DETERMINISTIC)

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

        run = self._run_from_resvg_node(resvg_node, text_content)
        # Attach xml:lang and font-variant from the SVG element
        from dataclasses import replace as _replace
        lang = element.get("{http://www.w3.org/XML/1998/namespace}lang") or element.get("lang")
        if lang and not run.language:
            run = _replace(run, language=lang.strip())

        # font-variant: small-caps → cap="small" on rPr
        font_variant = element.get("font-variant", "").strip().lower()
        if not font_variant:
            style_attr = element.get("style", "")
            if "font-variant" in style_attr:
                import re
                m = re.search(r"font-variant\s*:\s*([^;]+)", style_attr)
                if m:
                    font_variant = m.group(1).strip().lower()
        if font_variant == "small-caps":
            run = _replace(run, font_variant="small-caps")

        updated, run_policy = self.apply_policy(run)
        runs = [updated]

        origin_x, origin_y = self._resvg_text_origin(resvg_node, coord_space)
        anchor = self._resvg_text_anchor(resvg_node)
        direction = self._resvg_text_direction(resvg_node)

        # dominant-baseline / alignment-baseline → y-offset
        font_size = updated.font_size_pt
        dom_baseline = (element.get("dominant-baseline") or "").strip().lower()
        align_baseline = (element.get("alignment-baseline") or "").strip().lower()
        baseline = dom_baseline or align_baseline
        if baseline in ("central", "middle"):
            origin_y += font_size * 0.4  # shift down by ~half ascent
        elif baseline == "hanging":
            origin_y += font_size * 0.8  # shift down by full ascent
        elif baseline in ("text-bottom", "after-edge"):
            origin_y -= font_size * 0.2  # shift up by descent
        elif baseline in ("text-top", "before-edge"):
            origin_y += font_size * 0.8

        font_service = self._context.services.resolve("font")
        bbox = self._estimate_text_bbox(runs, origin_x, origin_y, font_service=font_service)
        bbox = self._apply_text_anchor(bbox, anchor)

        metadata: dict[str, Any] = {}
        self._attach_resvg_text_metadata(resvg_node, metadata)
        self._context.attach_policy_metadata(metadata, "text")
        if font_variant == "small-caps":
            metadata["font_variant"] = "small-caps"

        # writing-mode → vert attribute on bodyPr
        writing_mode = element.get("writing-mode", "").strip().lower()
        if not writing_mode:
            style_attr = element.get("style", "")
            if "writing-mode" in style_attr:
                import re as _re
                wm = _re.search(r"writing-mode\s*:\s*([^;]+)", style_attr)
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
            # Uniform rotation → xfrm rot on shape (keeps text native)
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
                    avg_dx = sum(dx_vals) / len(dx_vals)
                    is_uniform = all(
                        abs(v - avg_dx) / max(abs(avg_dx), 0.01) < 0.1
                        for v in dx_vals
                    ) if avg_dx != 0 else all(abs(v) < 0.5 for v in dx_vals)
                    if is_uniform and abs(avg_dx) > 0.01:
                        base_ls = updated.letter_spacing or 0.0
                        updated = _replace(updated, letter_spacing=base_ls + avg_dx)
                        runs = [updated]
                        _per_char_attrs = {}  # clear — handled as native spc
            if _per_char_attrs:
                metadata["per_char"] = _per_char_attrs

        # font-stretch → append width keyword to font family
        font_stretch = element.get("font-stretch", "").strip().lower()
        if not font_stretch:
            style_attr = element.get("style", "")
            if "font-stretch" in style_attr:
                import re as _re3
                fs = _re3.search(r"font-stretch\s*:\s*([^;]+)", style_attr)
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

        # text-decoration: overline (DrawingML has no overline — store for line shape)
        text_deco = element.get("text-decoration", "").lower()
        if not text_deco:
            style_attr = element.get("style", "")
            if "text-decoration" in style_attr:
                import re as _re2
                td = _re2.search(r"text-decoration\s*:\s*([^;]+)", style_attr)
                if td:
                    text_deco = td.group(1).strip().lower()
        if "overline" in text_deco:
            metadata["overline"] = True

        if writing_mode in ("tb", "tb-rl", "vertical-rl"):
            metadata["writing_mode"] = "vert"
        elif writing_mode in ("tb-lr", "vertical-lr"):
            metadata["writing_mode"] = "vert270"

        # textLength → compute effective letter-spacing
        text_length_attr = element.get("textLength")
        if text_length_attr and text_content.strip():
            try:
                target_width = float(text_length_attr)
                char_count = len(text_content.strip())
                if char_count > 1 and target_width > 0:
                    # Estimate natural width from bbox (will be computed below)
                    metadata["_text_length_target"] = target_width
                    length_adjust = element.get("lengthAdjust", "spacing").strip().lower()
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

    def _resvg_text_origin(self, resvg_node: Any, coord_space: CoordinateSpace) -> tuple[float, float]:
        spans = getattr(resvg_node, "spans", None)
        if spans:
            first = spans[0]
            x = getattr(first, "x", 0.0)
            y = getattr(first, "y", 0.0)
            return coord_space.apply_point(float(x), float(y))

        attrs = getattr(resvg_node, "attributes", {}) or {}
        x = self._parse_number_list(attrs.get("x"))
        y = self._parse_number_list(attrs.get("y"))
        dx = self._parse_number_list(attrs.get("dx"))
        dy = self._parse_number_list(attrs.get("dy"))
        base_x = x[0] if x else 0.0
        base_y = y[0] if y else 0.0
        base_x += dx[0] if dx else 0.0
        base_y += dy[0] if dy else 0.0
        return coord_space.apply_point(base_x, base_y)

    @staticmethod
    def _parse_number_list(value: str | None) -> list[float]:
        if not value:
            return []
        values: list[float] = []
        for part in value.replace(",", " ").split():
            try:
                values.append(float(part))
            except ValueError:
                continue
        return values

    def _resvg_text_anchor(self, resvg_node: Any) -> TextAnchor:
        attrs = getattr(resvg_node, "attributes", {}) or {}
        anchor_token = attrs.get("text-anchor") or attrs.get("textAnchor") or "start"
        return {
            "middle": TextAnchor.MIDDLE,
            "end": TextAnchor.END,
        }.get(str(anchor_token).strip().lower(), TextAnchor.START)

    def _resvg_text_direction(self, resvg_node: Any) -> str | None:
        attrs = getattr(resvg_node, "attributes", {}) or {}
        direction = attrs.get("direction")
        if isinstance(direction, str):
            token = direction.strip().lower()
            if token in ("rtl", "ltr"):
                return token
        return None

    def _run_from_resvg_node(self, resvg_node: Any, text: str) -> Run:
        text_style = getattr(resvg_node, "text_style", None)
        fill_style = getattr(resvg_node, "fill", None)
        stroke_style = getattr(resvg_node, "stroke", None)

        font_family = "Arial"
        font_size_pt = 12.0
        bold = False
        italic = False
        underline = False
        strike = False
        letter_spacing = None

        if text_style is not None:
            families = getattr(text_style, "font_families", None)
            if families:
                font_family = families[0] or font_family
            size = getattr(text_style, "font_size", None)
            if isinstance(size, (int, float)) and size > 0:
                font_size_pt = float(size)
            weight = str(getattr(text_style, "font_weight", "") or "").strip().lower()
            if weight:
                if weight in {"bold", "bolder"}:
                    bold = True
                else:
                    try:
                        bold = int(weight) >= 700
                    except ValueError:
                        bold = False
            style = str(getattr(text_style, "font_style", "") or "").strip().lower()
            italic = style in {"italic", "oblique"}
            decoration = str(getattr(text_style, "text_decoration", "") or "").lower()
            underline = "underline" in decoration
            strike = "line-through" in decoration
            letter_spacing = getattr(text_style, "letter_spacing", None)

        rgb = "000000"
        fill_opacity = 1.0
        if fill_style is not None:
            color = getattr(fill_style, "color", None)
            if color is not None:
                rgb = self._resvg_color_to_hex(color)
            opacity = getattr(fill_style, "opacity", None)
            if isinstance(opacity, (int, float)):
                fill_opacity = float(opacity)

        stroke_rgb = None
        stroke_width_px = None
        stroke_opacity = None
        if stroke_style is not None:
            color = getattr(stroke_style, "color", None)
            if color is not None:
                stroke_rgb = self._resvg_color_to_hex(color)
            width = getattr(stroke_style, "width", None)
            if isinstance(width, (int, float)):
                stroke_width_px = float(width)
            opacity = getattr(stroke_style, "opacity", None)
            if isinstance(opacity, (int, float)):
                stroke_opacity = float(opacity)

        return Run(
            text=text,
            font_family=font_family,
            font_size_pt=font_size_pt,
            bold=bold,
            italic=italic,
            underline=underline,
            strike=strike,
            rgb=rgb,
            fill_opacity=fill_opacity,
            stroke_rgb=stroke_rgb,
            stroke_width_px=stroke_width_px,
            stroke_opacity=stroke_opacity,
            letter_spacing=letter_spacing,
        )

    @staticmethod
    def _resvg_color_to_hex(color: Any) -> str:
        try:
            from svg2ooxml.color.models import Color as CentralizedColor
        except Exception:
            return "000000"

        r = float(getattr(color, "r", 0.0))
        g = float(getattr(color, "g", 0.0))
        b = float(getattr(color, "b", 0.0))
        a = float(getattr(color, "a", 1.0))
        centralized = CentralizedColor(r=r, g=g, b=b, a=a)
        hex_with_hash = centralized.to_hex(include_alpha=False)
        return hex_with_hash[1:].upper()

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

        # Extract text direction
        direction = base_style.get("direction") or element.get("direction") or None
        if isinstance(direction, str):
            direction = direction.strip().lower() if direction.strip().lower() in ("rtl", "ltr") else None

        for text, style, x, y in segments:
            run = self._create_run_from_style(text, style)
            if not run.text:
                continue
            updated, run_policy = self.apply_policy(run)
            if run_policy:
                policy_meta_accum.update(run_policy)

            origin_x, origin_y = coord_space.apply_point(x, y)
            bbox = self._estimate_text_bbox([updated], origin_x, origin_y, font_service=font_service)

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
                frame = self._smart_font_bridge.enhance_frame(frame, [updated], decision)

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
            normalized = self._normalize_positioned_text(text, preserve_space)
            if not normalized:
                return

            run = self._create_run_from_style(normalized, style)
            per_char = max(len(x_values), len(y_values), len(dx_values), len(dy_values)) > 1

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
            x_values = self._parse_text_length_list(node.get("x"), font_size_pt, axis="x")
            y_values = self._parse_text_length_list(node.get("y"), font_size_pt, axis="y")
            dx_values = self._parse_text_length_list(node.get("dx"), font_size_pt, axis="x")
            dy_values = self._parse_text_length_list(node.get("dy"), font_size_pt, axis="y")

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

    def _parse_text_length_list(
        self,
        value: str | None,
        font_size_pt: float,
        *,
        axis: str,
    ) -> list[float]:
        if not value:
            return []
        tokens = [token for token in re.split(r"[ ,]+", value.strip()) if token]
        return [
            self._resolve_text_length(token, axis=axis, font_size_pt=font_size_pt)
            for token in tokens
        ]

    @staticmethod
    def _normalize_positioned_text(text: str | None, preserve_space: bool) -> str:
        return TextConverter._normalize_text_segment(text, preserve_space=preserve_space)

    def apply_policy(self, run: Run) -> tuple[Run, dict[str, Any]]:
        policy = self._context.policy_options("text")
        if not policy:
            return run, {}

        decision = self._resolve_policy_decision(policy)
        if decision is not None:
            return self._apply_text_decision(run, decision)

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
        raise TypeError("TextConverter expects an IRConverterContext or compatible object.")

    # ------------------------------------------------------------------
    # Internal helpers
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

    def _compute_text_style_with_inheritance(self, element: etree._Element) -> dict[str, Any]:
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

        def visit(node: etree._Element, style: Mapping[str, Any], preserve_space: bool) -> None:
            xml_space = node.get("{http://www.w3.org/XML/1998/namespace}space")
            node_preserve = preserve_space or (xml_space == "preserve")
            text_segment = self._normalize_text_segment(node.text, preserve_space=node_preserve)
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
                    href = child.get("{http://www.w3.org/1999/xlink}href") or child.get("href")
                    path_id = self._context.normalize_href_reference(href)
                    if path_id:
                        metadata.setdefault("text_path_id", path_id)
                        sampled = self._sample_text_path(path_id)
                        if sampled is not None:
                            metadata["text_path_data"] = sampled["path_data"]
                            metadata["text_path_points"] = sampled["points"]
                    visit(child, child_style, node_preserve)
                else:
                    visit(child, style, node_preserve)
                tail_segment = self._normalize_text_segment(child.tail, preserve_space=node_preserve)
                if tail_segment:
                    segments.append((dict(style), tail_segment))

        visit(element, base_style, False)

        runs: list[Run] = []
        for style, segment in segments:
            run = self._create_run_from_style(segment, style)
            if run.text:
                runs.append(run)
        runs = self._merge_runs(runs)
        return runs, metadata

    @staticmethod
    def _normalize_text_segment(text: str | None, *, preserve_space: bool = False) -> str:
        if not text:
            return ""
        token = text.replace("\r\n", "\n").replace("\r", "\n")
        if preserve_space:
            if token.strip() == "":
                return "\n" if "\n" in token else " "
            return token
        if "\n" in token:
            collapsed = re.sub(r"\s+", " ", token)
            return collapsed.strip()
        if token.strip() == "":
            return " "
        leading_space = token[:1].isspace()
        trailing_space = token[-1:].isspace()
        core = re.sub(r"\s+", " ", token.strip())
        if leading_space:
            core = f" {core}"
        if trailing_space:
            core = f"{core} "
        return core

    def _create_run_from_style(self, text: str, style: Mapping[str, Any]) -> Run:
        fill = style.get("fill") or "#000000"
        hex_color = self._coerce_hex_color(fill)
        fill_opacity = float(style.get("fill_opacity", 1.0))
        
        stroke = style.get("stroke")
        stroke_rgb = None
        stroke_width = None
        stroke_opacity = None
        
        if stroke and stroke.lower() != "none":
            stroke_rgb = self._coerce_hex_color(stroke)
            stroke_width_raw = style.get("stroke_width", "1")
            stroke_width = self._resolve_text_length(stroke_width_raw, axis="x", font_size_pt=float(style.get("font_size_pt", 12.0)))
            stroke_opacity = float(style.get("stroke_opacity", 1.0))

        font_size = float(style.get("font_size_pt", 12.0))
        font_family = self._normalize_font_family_list(style.get("font_family"))
        weight_token = (style.get("font_weight") or "normal").lower()
        bold = weight_token in {"bold", "bolder", "600", "700", "800", "900"}
        font_style = (style.get("font_style") or "normal").lower()
        text_decoration = (style.get("text_decoration") or "").lower()
        underline = "underline" in text_decoration
        strike = any(token in text_decoration for token in ("line-through", "strike"))
        return Run(
            text=text,
            font_family=font_family,
            font_size_pt=font_size,
            bold=bold,
            italic=font_style == "italic",
            underline=underline,
            strike=strike,
            rgb=hex_color,
            fill_opacity=fill_opacity,
            stroke_rgb=stroke_rgb,
            stroke_width_px=stroke_width,
            stroke_opacity=stroke_opacity,
        )

    def _resolve_text_length(
        self,
        value: str | None,
        *,
        axis: str,
        font_size_pt: float,
    ) -> float:
        if value in (None, "", "0"):
            return 0.0
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            unit_converter = getattr(self._context, "unit_converter", None)
            context = getattr(self._context, "conversion_context", None)
            if unit_converter is None or context is None:
                return 0.0
            font_px = font_size_pt * (96.0 / 72.0)
            derived = context.derive(font_size=font_px)
            try:
                return unit_converter.to_px(value, derived, axis=axis)
            except Exception:
                return 0.0

    def _merge_runs(self, runs: list[Run]) -> list[Run]:
        if not runs:
            return []
        merged: list[Run] = [runs[0]]
        for run in runs[1:]:
            last = merged[-1]
            if self._runs_compatible(last, run):
                merged[-1] = replace(last, text=last.text + run.text)
            else:
                merged.append(run)
        return merged

    @staticmethod
    def _runs_compatible(first: Run, second: Run) -> bool:
        return (
            first.font_family == second.font_family
            and abs(first.font_size_pt - second.font_size_pt) <= 1e-6
            and first.bold == second.bold
            and first.italic == second.italic
            and first.underline == second.underline
            and first.strike == second.strike
            and first.rgb == second.rgb
            and first.theme_color == second.theme_color
            and abs(first.fill_opacity - second.fill_opacity) <= 1e-6
            and first.stroke_rgb == second.stroke_rgb
            and first.stroke_theme_color == second.stroke_theme_color
            and abs((first.stroke_width_px or 0.0) - (second.stroke_width_px or 0.0)) <= 1e-6
            and abs((first.stroke_opacity or 1.0) - (second.stroke_opacity or 1.0)) <= 1e-6
        )

    def _attach_resvg_text_metadata(self, resvg_node: Any, metadata: dict[str, Any]) -> None:
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

            paint_resolver = lambda ref: _resolve_paint_reference(ref, tree)  # noqa: E731

        generator = DrawingMLTextGenerator(
            font_service=self._context.services.resolve("font"),
            embedding_engine=self._context.services.resolve("font_embedding"),
            paint_resolver=paint_resolver,
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

    @staticmethod
    def _estimate_text_bbox(
        runs: list[Run],
        origin_x: float,
        origin_y: float,
        *,
        font_service: Any | None = None,
    ) -> Rect:
        """Estimate text bounding box from runs.

        Note: font_size_pt is in points. Need to convert to pixels (96 DPI standard).
        Proper text box height requires:
        - Font size in pixels
        - Line height (typically 1.2-1.5x font size)
        - Font ascent/descent

        Current approach uses conservative estimates to ensure text fits.
        When a FontService is available, per-glyph advances are used to
        improve width estimation.
        """
        if not runs:
            return Rect(origin_x, origin_y, 0.0, 0.0)

        max_font_pt = max(run.font_size_pt for run in runs)

        # Convert points to pixels (96 DPI standard: 1pt = 96/72 pixels = 1.333px)
        max_font_px = max_font_pt * (96.0 / 72.0)

        max_width = 0.0
        current_width = 0.0
        line_count = 1
        max_ascent_px = 0.0
        max_descent_px = 0.0
        max_gap_px = 0.0
        for run in runs:
            text = (run.text or "").replace("\r\n", "\n").replace("\r", "\n")
            if not text:
                continue
            parts = text.split("\n")
            for index, part in enumerate(parts):
                if index > 0:
                    max_width = max(max_width, current_width)
                    current_width = 0.0
                    line_count += 1
                if part:
                    current_width += _estimate_run_width(part, run, font_service)
            metrics = _resolve_font_metrics(font_service, run)
            if metrics is not None:
                font_px = run.font_size_pt * (96.0 / 72.0)
                scale = font_px / metrics.units_per_em
                ascender_px = max(0.0, metrics.ascender * scale)
                descender_px = max(0.0, -metrics.descender * scale)
                gap_px = max(0.0, metrics.line_gap * scale)
                max_ascent_px = max(max_ascent_px, ascender_px)
                max_descent_px = max(max_descent_px, descender_px)
                max_gap_px = max(max_gap_px, gap_px)
        max_width = max(max_width, current_width)

        metrics_found = max_ascent_px > 0.0 or max_descent_px > 0.0
        if metrics_found:
            raw_line_height = max_ascent_px + max_descent_px + max_gap_px
            min_line_height = max_font_px * 1.2
            line_height = max(raw_line_height, min_line_height)
            baseline_span = max_ascent_px + max_descent_px
            if baseline_span > 0.0:
                baseline_ratio = max_ascent_px / baseline_span
                y_offset = line_height * baseline_ratio
            else:
                y_offset = max_font_px * 0.8
        else:
            # Line height = font size + leading (extra space between lines)
            # Use 1.5x to avoid clipping when metrics are unavailable.
            line_height = max_font_px * 1.5
            y_offset = max_font_px * 0.8

        height = line_height * max(1, line_count)

        return Rect(origin_x, origin_y - y_offset, max_width, height)

    @staticmethod
    def _apply_text_anchor(bbox: Rect, anchor: TextAnchor) -> Rect:
        if anchor == TextAnchor.MIDDLE:
            return Rect(bbox.x - bbox.width / 2.0, bbox.y, bbox.width, bbox.height)
        if anchor == TextAnchor.END:
            return Rect(bbox.x - bbox.width, bbox.y, bbox.width, bbox.height)
        return bbox

    @staticmethod
    def _coerce_hex_color(token: str) -> str:
        value = (token or "").strip().lstrip("#")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        if len(value) != 6:
            return "000000"
        try:
            int(value, 16)
        except ValueError:
            return "000000"
        return value.upper()

    def _apply_text_decision(self, run: Run, decision: TextPolicyDecision) -> tuple[Run, dict[str, Any]]:
        updated = run
        metadata: dict[str, Any] = {}

        if not decision.allow_effects and (run.bold or run.italic or run.underline):
            updated = replace(updated, bold=False, italic=False, underline=False)
            metadata["effects_stripped"] = True

        behavior = decision.fallback.missing_font_behavior.lower()
        if behavior == "fallback_family":
            fallback = self._resolve_font_fallback(updated.font_family, decision.fallback.fallback_order)
            if fallback and fallback.lower() != updated.font_family.lower():
                updated = replace(updated, font_family=fallback)
                metadata["font_fallback"] = fallback
        elif behavior in {"outline", FALLBACK_EMF, "embedded"}:
            metadata["rendering_behavior"] = behavior

        glyph_fallback = decision.fallback.glyph_fallback
        if glyph_fallback:
            metadata["glyph_fallback"] = glyph_fallback

        if decision.fallback.max_vectorized_glyphs:
            metadata["max_vectorized_glyphs"] = decision.fallback.max_vectorized_glyphs
        metadata["prefer_vector_fallback"] = decision.fallback.prefer_vector_fallback
        metadata["wordart_detection"] = {
            "enabled": decision.wordart.enable_detection,
            "confidence_threshold": decision.wordart.confidence_threshold,
        }

        return updated, metadata

    def _resolve_font_fallback(
        self,
        family: str | None,
        fallback_order: Iterable[str],
    ) -> str | None:
        current = (family or "").strip()
        current_lower = current.lower()
        for candidate in fallback_order:
            resolved = self._normalize_font_family(candidate)
            if not resolved:
                continue
            if resolved.lower() == current_lower:
                continue
            return resolved

        normalized = self._normalize_font_family(self._font_fallback(current))
        if normalized and normalized.lower() != current_lower:
            return normalized
        return None

    @staticmethod
    def _font_fallback(family: str | None) -> str | None:
        if not family:
            return None
        key = family.strip().lower()
        return FONT_FALLBACKS.get(key)

    @staticmethod
    def _normalize_font_family(family: str | None) -> str | None:
        if family is None:
            return None
        token = family.strip()
        if not token:
            return None
        mapped = FONT_FALLBACKS.get(token.lower())
        return mapped or token

    def _normalize_font_family_list(self, family: str | None) -> str:
        if not family:
            return "Arial"
        tokens = [
            part.strip().strip('"\'')
            for part in family.split(",")
            if part.strip().strip('"\'')
        ]
        if not tokens:
            return "Arial"
        primary = tokens[0]
        normalized = self._normalize_font_family(primary)
        return normalized or primary

    def _sample_text_path(self, path_id: str) -> dict[str, object] | None:
        element = self._context.element_index.get(path_id)
        if element is None:
            return None
        path_data = element.get("d")
        if not path_data:
            return None
        try:
            points = self._text_path_positioner.sample_path_for_text(path_data, num_samples=96)
            return {"points": points, "path_data": path_data}
        except Exception:  # pragma: no cover - defensive fallback
            return None


def _parse_float(value: str | None, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    value = str(value).strip()
    if not value:
        return default
    try:
        if value.endswith("%"):
            return float(value[:-1]) / 100.0
        return float(value)  # type: ignore[arg-type]
    except ValueError:
        return default


__all__ = ["TextConverter", "FONT_FALLBACKS"]
