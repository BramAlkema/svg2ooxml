"""Text conversion helpers extracted from the core converter."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha1
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, Iterable, Mapping

from lxml import etree

from svg2ooxml.common.geometry.algorithms import CurveTextPositioner, PathSamplingMethod
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame
from svg2ooxml.policy.constants import FALLBACK_EMF
from svg2ooxml.policy.text_policy import TextPolicyDecision

from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.core.ir.smart_font_bridge import SmartFontBridge
from svg2ooxml.core.ir.text_pipeline import TextConversionPipeline
from svg2ooxml.services.fonts.fontforge_utils import (
    FONTFORGE_AVAILABLE,
    open_font,
)

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

@dataclass(frozen=True)
class _FontMetrics:
    units_per_em: int
    cmap: dict[int, str]
    advances: dict[str, int]
    default_advance: float
    ascender: int
    descender: int
    line_gap: int


_FONT_METRICS_CACHE: dict[str, _FontMetrics] = {}
_FONT_METRICS_MISS: set[str] = set()


def _metrics_cache_key(path: str | None, font_data: bytes | None) -> str | None:
    if font_data is not None:
        return f"data:{sha1(font_data).hexdigest()}"
    if path:
        return path
    return None


def _load_font_metrics(path: str | None, font_data: bytes | None = None) -> _FontMetrics | None:
    cache_key = _metrics_cache_key(path, font_data)
    if cache_key and cache_key in _FONT_METRICS_CACHE:
        return _FONT_METRICS_CACHE[cache_key]
    if not FONTFORGE_AVAILABLE:
        return None
    if cache_key and cache_key in _FONT_METRICS_MISS:
        return None

    source = font_data if font_data is not None else path
    if source is None:
        return None

    suffix = ".ttf"
    if font_data is None and path:
        suffix = Path(path).suffix or ".ttf"

    try:
        with open_font(source, suffix=suffix) as font:
            units_per_em = int(getattr(font, "em", 1000) or getattr(font, "emsize", 1000) or 1000)
            cmap: dict[int, str] = {}
            advances: dict[str, int] = {}

            glyphs = getattr(font, "glyphs", None)
            if callable(glyphs):
                for glyph in font.glyphs():
                    glyph_name = getattr(glyph, "glyphname", None)
                    if glyph_name:
                        width = getattr(glyph, "width", None)
                        if isinstance(width, (int, float)):
                            advances[glyph_name] = int(width)
                    codepoint = getattr(glyph, "unicode", None)
                    if isinstance(codepoint, int) and codepoint >= 0 and glyph_name:
                        cmap[codepoint] = glyph_name

            if "space" in advances:
                default_advance = float(advances["space"])
            elif advances:
                default_advance = float(sum(advances.values()) / max(1, len(advances)))
            else:
                default_advance = float(units_per_em) * 0.5

            ascender = int(getattr(font, "ascent", units_per_em * 0.8))
            descender_raw = getattr(font, "descent", units_per_em * 0.2)
            descender = -abs(int(descender_raw))
            line_gap = int(getattr(font, "os2_typolinegap", 0) or 0)
    except Exception:
        if cache_key:
            _FONT_METRICS_MISS.add(cache_key)
        return None

    metrics = _FontMetrics(
        units_per_em=max(1, units_per_em),
        cmap=cmap,
        advances=advances,
        default_advance=default_advance,
        ascender=ascender,
        descender=descender,
        line_gap=line_gap,
    )
    if cache_key:
        _FONT_METRICS_CACHE[cache_key] = metrics
    return metrics


def _resolve_font_metrics(font_service: Any | None, run: Run) -> _FontMetrics | None:
    if font_service is None or not hasattr(font_service, "find_font"):
        return None
    try:
        from svg2ooxml.services.fonts import FontQuery
    except Exception:
        return None

    family = (run.font_family or "Arial").split(",")[0].strip().strip('"\'')
    weight = 700 if run.bold else 400
    style = "italic" if run.italic else "normal"

    try:
        query = FontQuery(family=family, weight=weight, style=style)
        match = font_service.find_font(query)
    except Exception:
        return None

    if match is None:
        return None

    font_data = None
    if isinstance(match.metadata, dict):
        data = match.metadata.get("font_data")
        if isinstance(data, (bytes, bytearray)):
            font_data = bytes(data)

    path = str(match.path) if getattr(match, "path", None) else None
    if path is None and font_data is None:
        return None
    return _load_font_metrics(path, font_data)


def _estimate_run_width(text: str, run: Run, font_service: Any | None) -> float:
    font_px = run.font_size_pt * (96.0 / 72.0)
    if font_px <= 0:
        return 0.0

    metrics = _resolve_font_metrics(font_service, run)
    if metrics is None:
        return len(text) * font_px * 0.6

    width_units = 0.0
    for ch in text:
        if ch == "\n":
            continue
        glyph_name = metrics.cmap.get(ord(ch))
        if glyph_name is None:
            width_units += metrics.default_advance
            continue
        width_units += metrics.advances.get(glyph_name, metrics.default_advance)

    return (width_units / metrics.units_per_em) * font_px


class TextConverter:
    """Handle text element extraction, policy application, and metadata."""

    def __init__(
        self,
        context: "IRConverterContext | Any",
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
        base_style = self._compute_text_style_with_inheritance(element)
        runs, run_metadata = self._collect_text_runs(element, base_style)
        if not runs:
            return None

        if self._needs_positioned_text(element):
            positioned = self._convert_positioned_text(
                element=element,
                coord_space=coord_space,
                base_style=base_style,
                run_metadata=run_metadata,
            )
            return positioned or None

        processed_runs: list[Run] = []
        policy_meta_accum: dict[str, Any] = {}
        for run in runs:
            updated, run_policy = self.apply_policy(run)
            if run_policy:
                policy_meta_accum.update(run_policy)
            processed_runs.append(updated)

        processed_runs = self._merge_runs(processed_runs)
        if not processed_runs:
            return None

        font_size_pt = float(base_style.get("font_size_pt", 12.0))
        x = self._resolve_text_length(element.get("x"), axis="x", font_size_pt=font_size_pt)
        y = self._resolve_text_length(element.get("y"), axis="y", font_size_pt=font_size_pt)
        anchor_token = base_style.get("text_anchor") or element.get("text-anchor") or "start"
        anchor = {
            "middle": TextAnchor.MIDDLE,
            "end": TextAnchor.END,
        }.get(str(anchor_token).strip().lower(), TextAnchor.START)

        origin_x, origin_y = coord_space.apply_point(x, y)
        font_service = self._context.services.resolve("font")
        bbox = self._estimate_text_bbox(processed_runs, origin_x, origin_y, font_service=font_service)
        bbox = self._apply_text_anchor(bbox, anchor)

        metadata: dict[str, Any] = dict(run_metadata)
        if resvg_node is not None:
            self._attach_resvg_text_metadata(resvg_node, metadata)
        self._context.attach_policy_metadata(metadata, "text")
        if policy_meta_accum:
            policy_meta = metadata.setdefault("policy", {}).setdefault("text", {})
            policy_meta.update(policy_meta_accum)

        frame = TextFrame(
            origin=Point(origin_x, origin_y),
            anchor=anchor,
            bbox=bbox,
            runs=processed_runs,
            baseline_shift=0.0,
            metadata=metadata,
        )
        decision = self._resolve_policy_decision()
        if self._pipeline is not None:
            frame = self._pipeline.plan_frame(frame, processed_runs, decision)
        if self._smart_font_bridge is not None:
            frame = self._smart_font_bridge.enhance_frame(frame, processed_runs, decision)
        trace_stage = getattr(self._context, "trace_stage", None)
        if callable(trace_stage):
            trace_stage(
                "text_frame",
                stage="text",
                subject=metadata.get("text_path_id") or element.get("id"),
                metadata={
                    "run_count": len(processed_runs),
                    "uses_text_path": "text_path_id" in metadata,
                    "policy_applied": bool(policy_meta_accum),
                    "decision": getattr(decision, "value", decision),
                },
            )
        self._context.trace_geometry_decision(element, "native", frame.metadata)
        return frame

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

        decision = self._resolve_policy_decision()
        if decision is not None:
            return self._apply_text_decision(run, decision)

        if isinstance(policy, Mapping):
            return self._apply_legacy_policy(run, policy)
        return run, {}

    @property
    def pipeline(self) -> TextConversionPipeline:
        return self._pipeline

    @staticmethod
    def _resolve_context(context: "IRConverterContext | Any") -> "IRConverterContext":
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
            and abs(first.fill_opacity - second.fill_opacity) <= 1e-6
            and first.stroke_rgb == second.stroke_rgb
            and abs((first.stroke_width_px or 0.0) - (second.stroke_width_px or 0.0)) <= 1e-6
            and abs((first.stroke_opacity or 1.0) - (second.stroke_opacity or 1.0)) <= 1e-6
        )

    def _attach_resvg_text_metadata(self, resvg_node: Any, metadata: dict[str, Any]) -> None:
        if not hasattr(resvg_node, "text_content"):
            return
        try:
            from svg2ooxml.core.resvg.text.layout_analyzer import TextLayoutAnalyzer
            from svg2ooxml.core.resvg.text.drawingml_generator import DrawingMLTextGenerator
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

        generator = DrawingMLTextGenerator(
            font_service=self._context.services.resolve("font"),
            embedding_engine=self._context.services.resolve("font_embedding"),
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

    def _apply_legacy_policy(self, run: Run, policy: Mapping[str, Any]) -> tuple[Run, dict[str, Any]]:
        metadata: dict[str, Any] = {}
        updated = run

        allow_effects = bool(policy.get("allow_effects", True))
        if not allow_effects and (run.bold or run.italic or run.underline):
            updated = replace(updated, bold=False, italic=False, underline=False)
            metadata["effects_stripped"] = True

        behavior = str(policy.get("font_missing_behavior") or "").lower()
        if behavior == "fallback_family":
            fallback = self._resolve_font_fallback(updated.font_family, ())
            if fallback and fallback != updated.font_family:
                updated = replace(updated, font_family=fallback)
                metadata["font_fallback"] = fallback
        elif behavior in {"outline", FALLBACK_EMF}:
            metadata["rendering_behavior"] = behavior

        glyph_fallback = policy.get("glyph_fallback")
        if glyph_fallback:
            metadata["glyph_fallback"] = glyph_fallback

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
