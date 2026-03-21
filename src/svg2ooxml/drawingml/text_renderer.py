"""Text rendering helpers extracted from DrawingMLWriter."""

from __future__ import annotations

import logging
from collections.abc import Callable

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

        # Overline: emit a thin line shape above the text baseline
        meta = getattr(element, "metadata", None)
        if isinstance(meta, dict) and meta.get("overline"):
            overline_xml = _build_overline_shape(element, shape_id + 1)
            if overline_xml:
                xml = xml + overline_xml
                return xml, shape_id + 2

        return xml, shape_id + 1


def _build_overline_shape(element, shape_id: int) -> str:
    """Build a thin line shape positioned above the text baseline."""
    from svg2ooxml.drawingml.generator import px_to_emu

    bbox = element.bbox
    run = (element.runs or [None])[0]
    stroke_rgb = "000000"
    stroke_width = 1.0
    if run is not None:
        stroke_rgb = run.rgb or "000000"
        stroke_width = max(0.5, run.font_size_pt * 0.05)

    x = px_to_emu(bbox.x)
    y = px_to_emu(bbox.y)
    w = px_to_emu(bbox.width)
    h = px_to_emu(stroke_width)
    sw = px_to_emu(stroke_width)

    return (
        f'<p:cxnSp>'
        f'<p:nvCxnSpPr>'
        f'<p:cNvPr id="{shape_id}" name="Overline {shape_id}"/>'
        f'<p:cNvCxnSpPr><a:cxnSpLocks noGrp="1"/></p:cNvCxnSpPr>'
        f'<p:nvPr/>'
        f'</p:nvCxnSpPr>'
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="0"/></a:xfrm>'
        f'<a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
        f'<a:ln w="{sw}"><a:solidFill><a:srgbClr val="{stroke_rgb.upper()}"/></a:solidFill></a:ln>'
        f'</p:spPr>'
        f'</p:cxnSp>'
    )


__all__ = ["DrawingMLTextRenderer"]
