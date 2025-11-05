"""Text conversion helpers extracted from the core converter."""

from __future__ import annotations

from dataclasses import replace
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
    from svg2ooxml.core.ir.converter import IRConverter


FONT_FALLBACKS: dict[str, str] = {
    "sans-serif": "Arial",
    "serif": "Times New Roman",
    "monospace": "Courier New",
    "cursive": "Comic Sans MS",
    "fantasy": "Impact",
}


class TextConverter:
    """Handle text element extraction, policy application, and metadata."""

    def __init__(self, parent: IRConverter, pipeline: TextConversionPipeline | None = None) -> None:
        self._parent = parent
        self._pipeline = pipeline or TextConversionPipeline(
            font_service=parent._services.resolve("font"),  # pylint: disable=protected-access
            embedding_engine=parent._services.resolve("font_embedding"),  # pylint: disable=protected-access
            logger=parent._logger,  # pylint: disable=protected-access
        )
        self._smart_font_bridge = SmartFontBridge(parent._services, parent._logger)
        self._text_path_positioner = CurveTextPositioner(PathSamplingMethod.DETERMINISTIC)

    # ------------------------------------------------------------------
    # Public surface consumed by IRConverter
    # ------------------------------------------------------------------

    def convert(self, *, element: etree._Element, coord_space: CoordinateSpace) -> TextFrame | None:
        base_style = self._parent._style_resolver.compute_text_style(  # pylint: disable=protected-access
            element,
            context=self._parent._css_context,  # pylint: disable=protected-access
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
        bbox = self._estimate_text_bbox(processed_runs, origin_x, origin_y)

        metadata: dict[str, Any] = dict(run_metadata)
        self._parent._attach_policy_metadata(metadata, "text")  # pylint: disable=protected-access
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
        trace_stage = getattr(self._parent, "_trace_stage", None)
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
        self._parent._trace_geometry_decision(element, "native", frame.metadata)  # pylint: disable=protected-access
        return frame

    def apply_policy(self, run: Run) -> tuple[Run, dict[str, Any]]:
        policy = self._parent._policy_options("text")  # pylint: disable=protected-access
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_policy_decision(
        self,
        policy: Mapping[str, Any] | None = None,
    ) -> TextPolicyDecision | None:
        options = policy
        if options is None:
            options = self._parent._policy_options("text")  # pylint: disable=protected-access
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
                local = self._parent._local_name(getattr(child, "tag", "")).lower()  # pylint: disable=protected-access
                if local == "tspan":
                    child_style = self._parent._style_resolver.compute_text_style(  # pylint: disable=protected-access
                        child,
                        context=self._parent._css_context,  # pylint: disable=protected-access
                        parent_style=style,
                    )
                    visit(child, child_style)
                elif local == "textpath":
                    child_style = self._parent._style_resolver.compute_text_style(  # pylint: disable=protected-access
                        child,
                        context=self._parent._css_context,  # pylint: disable=protected-access
                        parent_style=style,
                    )
                    href = child.get("{http://www.w3.org/1999/xlink}href") or child.get("href")
                    path_id = self._parent._normalize_href_reference(href)  # pylint: disable=protected-access
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

    @staticmethod
    def _estimate_text_bbox(
        runs: list[Run],
        origin_x: float,
        origin_y: float,
    ) -> Rect:
        """Estimate text bounding box from runs.

        Note: font_size_pt is in points. Need to convert to pixels (96 DPI standard).
        Proper text box height requires:
        - Font size in pixels
        - Line height (typically 1.2-1.5x font size)
        - Font ascent/descent

        Current approach uses conservative estimates to ensure text fits.
        """
        if not runs:
            return Rect(origin_x, origin_y, 0.0, 0.0)

        max_font_pt = max(run.font_size_pt for run in runs)

        # Convert points to pixels (96 DPI standard: 1pt = 96/72 pixels = 1.333px)
        max_font_px = max_font_pt * (96.0 / 72.0)

        text_content = "".join(run.text for run in runs)
        lines = text_content.split("\n") if text_content else [""]
        max_line_length = max(len(line) for line in lines) if lines else 0

        # Width: Estimate average character width as 0.6x font size (monospace assumption)
        # TODO: Use actual font metrics for more accurate width
        width = max_line_length * max_font_px * 0.6

        # Height: Use proper line height calculation
        # Line height = font size + leading (extra space between lines)
        # Standard line height is 1.2-1.5x font size
        # We use 1.5x to ensure text doesn't clip
        line_height = max_font_px * 1.5
        height = line_height * max(1, len(lines))

        # Origin offset: Position top of bbox above the baseline
        # Typical font ascent is ~0.75-0.8 of font size
        y_offset = max_font_px * 0.8

        return Rect(origin_x, origin_y - y_offset, width, height)

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
        element = self._parent._element_index.get(path_id)  # pylint: disable=protected-access
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
