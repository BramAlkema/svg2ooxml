"""Text rendering helpers extracted from DrawingMLWriter."""

from __future__ import annotations

import logging
from typing import Callable

from svg2ooxml.ir.text import TextFrame

from . import shapes_runtime
from .assets import AssetRegistry


class DrawingMLTextRenderer:
    """Render text frames and register font plans."""

    def __init__(
        self,
        *,
        text_template: str,
        wordart_template: str,
        policy_for: Callable[[dict[str, object] | None, str], dict[str, object]],
        register_run_navigation: Callable[[object, str], str],
        trace_writer: Callable[..., None],
        assets: AssetRegistry,
        logger: logging.Logger,
    ) -> None:
        self._text_template = text_template
        self._wordart_template = wordart_template
        self._policy_for = policy_for
        self._register_run_navigation = register_run_navigation
        self._trace_writer = trace_writer
        self._assets = assets
        self._logger = logger

    def render(
        self,
        element: TextFrame,
        shape_id: int,
        *,
        hyperlink_xml: str,
        clip_path_xml: str,
        mask_xml: str,
    ) -> tuple[str, int]:
        candidate = getattr(element, "wordart_candidate", None)
        metadata = element.metadata if isinstance(element.metadata, dict) else {}
        wordart_meta = metadata.get("wordart") if isinstance(metadata, dict) else {}
        
        # Determine confidence threshold from policy metadata
        policy_text = self._policy_for(metadata, "text")
        detection_meta = policy_text.get("wordart_detection")
        if isinstance(detection_meta, dict):
            threshold = float(detection_meta.get("confidence_threshold", 0.5))
        else:
            threshold = 0.5

        prefer_native = True
        if isinstance(wordart_meta, dict):
            prefer_native = bool(wordart_meta.get("prefer_native", True))

        is_confident = False
        if candidate is not None:
            is_confident = candidate.confidence >= threshold

        if (
            candidate is not None
            and is_confident
            and prefer_native
        ):
            xml = shapes_runtime.render_wordart(
                element,
                candidate,
                shape_id,
                template=self._wordart_template,
                policy_for=self._policy_for,
                logger=self._logger,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
                register_run_navigation=self._register_run_navigation,
            )
        else:
            xml = shapes_runtime.render_textframe(
                element,
                shape_id,
                template=self._text_template,
                policy_for=self._policy_for,
                logger=self._logger,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
                register_run_navigation=self._register_run_navigation,
            )

        if getattr(element, "embedding_plan", None) is not None:
            plan = element.embedding_plan
            if plan.requires_embedding:
                self._assets.add_font_plan(shape_id=shape_id, plan=plan)
                self._trace_writer(
                    "font_plan_registered",
                    stage="font",
                    metadata={
                        "shape_id": shape_id,
                        "font_family": getattr(plan, "font_family", None),
                        "requires_embedding": plan.requires_embedding,
                        "glyph_count": getattr(plan, "glyph_count", None),
                    },
                )

        return xml, shape_id + 1


__all__ = ["DrawingMLTextRenderer"]
