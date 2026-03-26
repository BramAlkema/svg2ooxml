"""Text conversion pipeline that plans WordArt and font embedding decisions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from svg2ooxml.common.geometry.algorithms import classify_text_path_warp
from svg2ooxml.ir.text import (
    EmbeddedFontPlan,
    Run,
    TextFrame,
    WordArtCandidate,
)
from svg2ooxml.ir.text_path import TextPathFrame
from svg2ooxml.policy.text_policy import TextPolicyDecision
from svg2ooxml.services.fonts import (
    FontEmbeddingRequest,
    FontMatch,
    FontQuery,
    FontSystem,
    FontSystemConfig,
    collect_font_directories,
)

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.ir.context import IRConverterContext
    from svg2ooxml.core.ir.text_converter import TextConverter
    from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace

try:  # pragma: no cover - optional dependency
    from svg2ooxml.services.fonts.providers.directory import DirectoryFontProvider
except Exception:  # pragma: no cover
    DirectoryFontProvider = None  # type: ignore[assignment]


class TextPipeline:
    """Expose text conversion through a focused pipeline interface."""

    def __init__(
        self,
        context: IRConverterContext,
        *,
        converter: TextConverter | None = None,
        pipeline: TextConversionPipeline | None = None,
    ) -> None:
        if converter is None:
            from svg2ooxml.core.ir.text_converter import TextConverter

            converter = TextConverter(context, pipeline=pipeline)
        self._converter = converter

    def convert(self, *, element, coord_space: CoordinateSpace, resvg_node=None):
        return self._converter.convert(element=element, coord_space=coord_space, resvg_node=resvg_node)

    @property
    def converter(self) -> TextConverter:
        return self._converter


class TextConversionPipeline:
    """Coordinate WordArt classification and font embedding planning."""

    def __init__(
        self,
        *,
        font_service,
        embedding_engine,
        logger,
        font_system=None,
    ) -> None:
        self._font_service = font_service
        self._embedding = embedding_engine
        self._logger = logger
        self._registered_dirs: set[Path] = set()
        self._font_system = font_system
        if self._font_system is None and font_service is not None:
            directories = collect_font_directories()
            config = FontSystemConfig(directories=directories)
            self._font_system = FontSystem(font_service, config=config)
        if self._font_system is not None and self._font_service is not None:
            self._font_system.register_directories(
                [Path(directory) for directory in collect_font_directories()]
            )

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def plan_frame(
        self,
        frame: TextFrame,
        runs: Sequence[Run],
        decision: TextPolicyDecision | None,
    ) -> TextFrame:
        """Return an updated frame with preliminary metadata attached."""

        if decision is not None:
            self._ensure_directory_providers(decision)

        wordart_candidate = self._plan_wordart(frame, runs, decision)
        embedding_plan = self._plan_embedding(frame, runs, decision)
        metadata = dict(frame.metadata)

        if wordart_candidate is not None and decision is not None:
            wordart_meta = metadata.setdefault("wordart", {})
            wordart_meta["preset"] = wordart_candidate.preset
            wordart_meta["confidence"] = wordart_candidate.confidence
            wordart_meta["fallback"] = wordart_candidate.fallback_strategy
            wordart_meta["prefer_native"] = decision.wordart.prefer_native_wordart
            if wordart_candidate.metadata:
                wordart_meta.update(wordart_candidate.metadata)

        if embedding_plan is not None:
            embedding_meta = metadata.setdefault("font_embedding", {})
            embedding_meta["requires_embedding"] = embedding_plan.requires_embedding
            embedding_meta["subset_strategy"] = embedding_plan.subset_strategy
            embedding_meta["glyph_count"] = embedding_plan.glyph_count
            if embedding_plan.metadata:
                embedding_meta.update(embedding_plan.metadata)

        return replace(
            frame,
            metadata=metadata,
            wordart_candidate=wordart_candidate,
            embedding_plan=embedding_plan,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _plan_wordart(
        self,
        frame: TextFrame,
        runs: Sequence[Run],
        decision: TextPolicyDecision | None,
    ) -> WordArtCandidate | None:
        if decision is None or not decision.wordart.enable_detection:
            return None

        text_content = "".join(run.text for run in runs).strip()
        if not text_content:
            return None

        metadata = frame.metadata if isinstance(frame.metadata, dict) else {}
        path_id = metadata.get("text_path_id") if isinstance(metadata, dict) else None
        path_points = metadata.get("text_path_points") if isinstance(metadata, dict) else None
        path_data = metadata.get("text_path_data") if isinstance(metadata, dict) else None

        classification = None
        if isinstance(path_points, list) and path_points:
            try:
                text_path_frame = TextPathFrame(
                    runs=list(runs),
                    path_reference=path_id or "detected-path",
                    path_points=path_points,
                )
                classification = classify_text_path_warp(
                    text_path_frame,
                    path_points,
                    path_data=path_data if isinstance(path_data, str) else None,
                )
            except Exception:  # pragma: no cover - defensive fallback
                classification = None

        if classification is not None:
            fallback = decision.fallback.glyph_fallback or "vector_outline"
            candidate_meta = {
                "length": len(text_content),
                "prefer_native": decision.wordart.prefer_native_wordart,
                "parameters": classification.parameters,
            }
            if classification.features:
                candidate_meta["features"] = classification.features
            if classification.reason:
                candidate_meta["reason"] = classification.reason
            if path_id:
                candidate_meta["text_path_id"] = path_id
            return WordArtCandidate(
                preset=classification.preset,
                confidence=classification.confidence,
                fallback_strategy=fallback,
                metadata=candidate_meta,
            )

        # Fallback heuristic classification
        if "\n" in text_content:
            return None

        preset, confidence = self._classify_wordart(
            text_content,
            frame,
            path_id,
            decision,
        )
        if confidence < max(0.05, decision.wordart.confidence_threshold * 0.6):
            return None

        fallback = decision.fallback.glyph_fallback or "vector_outline"
        fallback_metadata = {
            "length": len(text_content),
            "prefer_native": decision.wordart.prefer_native_wordart,
            "reason": "heuristic_wordart_classification",
        }
        if path_id:
            fallback_metadata["text_path_id"] = path_id
        return WordArtCandidate(
            preset=preset,
            confidence=min(confidence, 0.99),
            fallback_strategy=fallback,
            metadata=fallback_metadata,
        )

    def _plan_embedding(
        self,
        frame: TextFrame,
        runs: Sequence[Run],
        decision: TextPolicyDecision | None,
    ) -> EmbeddedFontPlan | None:
        if decision is None or not decision.embedding.embed_when_available:
            return None
        if not runs:
            return None

        primary_run = runs[0]
        glyphs = {ord(ch) for run in runs for ch in run.text or ""}
        glyph_count = len(glyphs)
        if glyph_count == 0:
            return None

        metadata: dict[str, object] = {
            "subset_strategy": decision.embedding.subset_strategy,
            "preserve_hinting": decision.embedding.preserve_hinting,
        }
        style_kind = self._style_kind_for_run(primary_run)
        metadata["font_style_kind"] = style_kind
        metadata["bold"] = primary_run.bold
        metadata["italic"] = primary_run.italic
        metadata["font_weight"] = primary_run.weight_class
        metadata["font_style"] = "italic" if primary_run.italic else "normal"

        match: FontMatch | None = None
        if self._font_service is not None:
            query = FontQuery(
                family=primary_run.font_family,
                weight=primary_run.weight_class,
                style="italic" if primary_run.italic else "normal",
                fallback_chain=decision.fallback.fallback_order,
            )
            match = self._font_service.find_font(query)
            if match is not None:
                metadata["resolved_family"] = match.family
                metadata["font_source"] = match.found_via
                if match.path:
                    metadata["font_path"] = match.path

        requires_embedding = match is not None
        subset_result = None
        if requires_embedding and self._embedding is not None and match.path:
            metadata["engine_available"] = True
            # Skip can_embed check for web fonts (data already loaded)
            is_web_font = "font_data" in match.metadata
            if not is_web_font and not self._embedding.can_embed(match.path):
                requires_embedding = False
                metadata["resolution"] = "embedding_disallowed"
            else:
                glyph_tuple = tuple(sorted(glyphs))
                request_metadata = {
                    "font_family": match.family,
                    "font_source": metadata.get("font_source"),
                    "font_style_kind": style_kind,
                    "bold": primary_run.bold,
                    "italic": primary_run.italic,
                    "font_weight": primary_run.weight_class,
                    "font_style": "italic" if primary_run.italic else "normal",
                }
                # Pass through web font data if available
                if "font_data" in match.metadata:
                    request_metadata["font_data"] = match.metadata["font_data"]

                request = FontEmbeddingRequest(
                    font_path=match.path,
                    glyph_ids=glyph_tuple,
                    preserve_hinting=decision.embedding.preserve_hinting,
                    subset_strategy=decision.embedding.subset_strategy,
                    metadata=request_metadata,
                )
                subset_result = self._embedding.subset_font(request)
                if subset_result is None:
                    requires_embedding = False
                    metadata["resolution"] = "embedding_failed"
                else:
                    metadata.update(subset_result.packaging_metadata)
                    metadata["subset_bytes"] = subset_result.bytes_written
                    if subset_result.relationship_id:
                        metadata["relationship_id"] = subset_result.relationship_id
        elif self._embedding is None:
            metadata["engine_available"] = False
            requires_embedding = False

        if match is None:
            metadata["resolution"] = "font_service_unavailable"
        elif requires_embedding and "resolution" not in metadata:
            metadata["resolution"] = "embed"
        elif "resolution" not in metadata:
            metadata["resolution"] = "embedding_disabled"

        return EmbeddedFontPlan(
            font_family=primary_run.font_family,
            requires_embedding=requires_embedding,
            subset_strategy=decision.embedding.subset_strategy,
            glyph_count=glyph_count,
            relationship_hint=subset_result.relationship_id if subset_result else None,
            metadata=metadata,
        )

    @staticmethod
    def _style_kind_for_run(run: Run) -> str:
        if run.bold and run.italic:
            return "boldItalic"
        if run.bold:
            return "bold"
        if run.italic:
            return "italic"
        return "regular"

    def _ensure_directory_providers(self, decision: TextPolicyDecision) -> None:
        if self._font_service is None or DirectoryFontProvider is None:
            return

        for directory in decision.font_directories:
            path = Path(directory).expanduser()
            if not path.exists() or not path.is_dir():
                continue
            resolved = path.resolve()
            if resolved in self._registered_dirs:
                continue
            provider = DirectoryFontProvider((resolved,))
            self._font_service.register_provider(provider)
            self._registered_dirs.add(resolved)
            if self._font_system is not None:
                self._font_system.register_directories((resolved,))

    def _classify_wordart(
        self,
        text_content: str,
        frame: TextFrame,
        text_path_id: str | None,
        decision: TextPolicyDecision,
    ) -> tuple[str, float]:
        base_confidence = max(0.05, decision.wordart.confidence_threshold)
        confidence = base_confidence * 0.75
        preset = "textPlain"
        is_path_based = False

        if text_path_id:
            # Only use non-plain presets for actual <textPath> elements
            preset = "textArchUp"
            confidence = max(confidence, base_confidence + 0.25)

        return preset, confidence


__all__ = ["TextConversionPipeline", "TextPipeline"]
