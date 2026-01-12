"""Text conversion helpers extracted from the core converter."""

from __future__ import annotations

from dataclasses import dataclass, replace
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

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.ir.context import IRConverterContext


FONT_FALLBACKS: dict[str, str] = {
    "sans-serif": "Arial",
    "serif": "Times New Roman",
    "monospace": "Courier New",
    "cursive": "Comic Sans MS",
    "fantasy": "Impact",
}

try:  # pragma: no cover - optional dependency
    from fontTools.ttLib import TTFont  # type: ignore[import-untyped]

    FONTTOOLS_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    TTFont = None  # type: ignore[assignment]
    FONTTOOLS_AVAILABLE = False


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


def _load_font_metrics(path: str) -> _FontMetrics | None:
    if path in _FONT_METRICS_CACHE:
        return _FONT_METRICS_CACHE[path]
    if path in _FONT_METRICS_MISS or not FONTTOOLS_AVAILABLE:
        return None
    try:
        font = TTFont(path)
    except Exception:
        _FONT_METRICS_MISS.add(path)
        return None

    try:
        units_per_em = 1000
        if "head" in font:
            units_per_em = int(getattr(font["head"], "unitsPerEm", units_per_em))
        cmap = {}
        if "cmap" in font:
            cmap = font["cmap"].getBestCmap() or {}
        advances: dict[str, int] = {}
        if "hmtx" in font:
            advances = {name: int(metrics[0]) for name, metrics in font["hmtx"].metrics.items()}
        if "space" in advances:
            default_advance = float(advances["space"])
        elif advances:
            default_advance = float(sum(advances.values()) / len(advances))
        else:
            default_advance = float(units_per_em) * 0.5

        ascender = None
        descender = None
        line_gap = None
        if "OS/2" in font:
            os2 = font["OS/2"]
            ascender = getattr(os2, "sTypoAscender", None)
            descender = getattr(os2, "sTypoDescender", None)
            line_gap = getattr(os2, "sTypoLineGap", None)
            win_ascent = getattr(os2, "usWinAscent", None)
            win_descent = getattr(os2, "usWinDescent", None)
            if ascender is None and win_ascent is not None:
                ascender = int(win_ascent)
            if descender is None and win_descent is not None:
                descender = -int(win_descent)
        if "hhea" in font:
            hhea = font["hhea"]
            if ascender is None:
                ascender = int(getattr(hhea, "ascent", 0))
            if descender is None:
                descender = int(getattr(hhea, "descent", 0))
            if line_gap is None:
                line_gap = int(getattr(hhea, "lineGap", 0))

        if ascender is None:
            ascender = int(units_per_em * 0.8)
        if descender is None:
            descender = -int(units_per_em * 0.2)
        if line_gap is None:
            line_gap = 0
    finally:
        try:
            font.close()
        except Exception:
            pass

    metrics = _FontMetrics(
        units_per_em=max(1, units_per_em),
        cmap=cmap,
        advances=advances,
        default_advance=default_advance,
        ascender=ascender,
        descender=descender,
        line_gap=line_gap,
    )
    _FONT_METRICS_CACHE[path] = metrics
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

    if match is None or not getattr(match, "path", None):
        return None
    return _load_font_metrics(str(match.path))


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
    ) -> TextFrame | None:
        base_style = self._context.style_resolver.compute_text_style(
            element,
            context=self._context.css_context,
        )
        runs, run_metadata = self._collect_text_runs(element, base_style)
        if not runs:
            return None

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

        x = _parse_float(element.get("x"), default=0.0) or 0.0
        y = _parse_float(element.get("y"), default=0.0) or 0.0
        anchor = {
            "middle": TextAnchor.MIDDLE,
            "end": TextAnchor.END,
        }.get(element.get("text-anchor"), TextAnchor.START)

        origin_x, origin_y = coord_space.apply_point(x, y)
        font_service = self._context.services.resolve("font")
        bbox = self._estimate_text_bbox(processed_runs, origin_x, origin_y, font_service=font_service)

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

    def _collect_text_runs(
        self,
        element: etree._Element,
        base_style: Mapping[str, Any],
    ) -> tuple[list[Run], dict[str, Any]]:
        segments: list[tuple[Mapping[str, Any], str]] = []
        metadata: dict[str, Any] = {}

        def visit(node: etree._Element, style: Mapping[str, Any]) -> None:
            text_segment = self._normalize_text_segment(node.text)
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
                    visit(child, child_style)
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
                    visit(child, child_style)
                else:
                    visit(child, style)
                tail_segment = self._normalize_text_segment(child.tail)
                if tail_segment:
                    segments.append((dict(style), tail_segment))

        visit(element, base_style)

        runs: list[Run] = []
        for style, segment in segments:
            run = self._create_run_from_style(segment, style)
            if run.text:
                runs.append(run)
        runs = self._merge_runs(runs)
        return runs, metadata

    @staticmethod
    def _normalize_text_segment(text: str | None) -> str:
        if not text:
            return ""
        token = text.replace("\r\n", "\n").replace("\r", "\n")
        if token.strip() == "":
            return "\n" if "\n" in token else " "
        return token

    def _create_run_from_style(self, text: str, style: Mapping[str, Any]) -> Run:
        fill = style.get("fill") or "#000000"
        hex_color = self._coerce_hex_color(fill)
        font_size = float(style.get("font_size_pt", 12.0))
        font_family = style.get("font_family", "Arial")
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
        )

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
            line_height = max_ascent_px + max_descent_px + max_gap_px
            min_line_height = max_font_px * 1.2
            if line_height < min_line_height:
                line_height = min_line_height
            y_offset = max_ascent_px if max_ascent_px > 0.0 else max_font_px * 0.8
        else:
            # Line height = font size + leading (extra space between lines)
            # Use 1.5x to avoid clipping when metrics are unavailable.
            line_height = max_font_px * 1.5
            y_offset = max_font_px * 0.8

        height = line_height * max(1, line_count)

        return Rect(origin_x, origin_y - y_offset, max_width, height)

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
    if value in (None, "", "0"):
        return default
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


__all__ = ["TextConverter", "FONT_FALLBACKS"]
