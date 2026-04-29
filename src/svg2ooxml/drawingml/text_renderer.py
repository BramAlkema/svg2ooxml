"""Text rendering helpers extracted from DrawingMLWriter."""

from __future__ import annotations

import logging
from collections.abc import Callable

from svg2ooxml.common.math_utils import coerce_float
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
            threshold = coerce_float(
                detection_meta.get("confidence_threshold"),
                0.5,
            )
        else:
            threshold = 0.5

        prefer_native = True
        if isinstance(wordart_meta, dict):
            prefer_native = bool(wordart_meta.get("prefer_native", True))

        is_confident = False
        if candidate is not None:
            is_confident = candidate.confidence >= threshold or prefer_native

        # Per-character positioning: use glyph outline renderer
        # Per-character positioning: prefer native text with spc when dx is
        # uniform, otherwise fall back to glyph outlines.
        meta = getattr(element, "metadata", None) or {}
        per_char = meta.get("per_char") if isinstance(meta, dict) else None
        if per_char and element.runs:
            # Try native text with letter-spacing if dx is uniform and no
            # dy/rotate/absolute positioning — keeps text editable.
            if self._can_use_native_text(per_char, element):
                pass  # fall through to normal text rendering below
            else:
                glyph_xml = self._render_per_char_glyphs(element, shape_id, per_char)
                if glyph_xml:
                    return glyph_xml

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

    @staticmethod
    def _can_use_native_text(per_char: dict, element) -> bool:
        """Return True when per-char attributes can use native DrawingML.

        Native text is preferred because it keeps text editable and uses
        font embedding (FontForge → EOT) instead of glyph outlines.

        Handles:
        - Uniform dx → letter-spacing (spc)
        - Uniform rotate → xfrm rot on shape (stored in metadata)
        - No dy/abs positioning needed
        """
        if per_char.get("dy"):
            return False
        if per_char.get("abs_x") or per_char.get("abs_y"):
            return False

        # Uniform rotation → can use <a:xfrm rot="..."> on the text shape
        rotate = per_char.get("rotate")
        if rotate:
            if len(set(rotate)) == 1:
                # All same angle — store for xfrm emission
                meta = getattr(element, "metadata", None)
                if isinstance(meta, dict):
                    meta["text_rotation_deg"] = rotate[0]
            else:
                return False  # varying rotation needs glyph outlines
        dx = per_char.get("dx")
        if not dx:
            return True  # no offsets at all
        # Check if dx values are uniform (all same ± 10%)
        if len(dx) <= 1:
            return True
        avg = sum(dx) / len(dx)
        if avg == 0:
            return all(abs(v) < 0.5 for v in dx)
        return all(abs(v - avg) / max(abs(avg), 0.01) < 0.1 for v in dx)

    def _render_per_char_glyphs(
        self, element, shape_id: int, per_char: dict,
    ) -> tuple[str, int] | None:
        """Render per-character positioned text as glyph outlines."""
        from svg2ooxml.drawingml.glyph_renderer import (
            SKIA_AVAILABLE,
            compute_glyph_placements,
            render_positioned_glyphs,
        )

        if not SKIA_AVAILABLE:
            return None

        run = element.runs[0]
        text = run.text
        if not text.strip():
            return None

        bbox = element.bbox
        placements = compute_glyph_placements(
            text,
            run.font_family,
            run.font_size_pt,
            bbox.x,
            bbox.y + bbox.height,  # baseline ≈ bottom of bbox
            dx=per_char.get("dx"),
            dy=per_char.get("dy"),
            abs_x=per_char.get("abs_x"),
            abs_y=per_char.get("abs_y"),
            rotate=per_char.get("rotate"),
        )

        xml, next_id = render_positioned_glyphs(
            text,
            run.font_family,
            run.font_size_pt,
            placements,
            shape_id_start=shape_id,
            fill_rgb=run.rgb,
            fill_opacity=run.fill_opacity,
        )
        if xml:
            return xml, next_id
        return None


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
