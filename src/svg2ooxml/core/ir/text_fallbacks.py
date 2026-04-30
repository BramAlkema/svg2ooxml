"""SVG text fallback helpers for :mod:`svg2ooxml.core.ir.text_converter`."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.core.ir.text.dense_rotation_fallback import (
    bidi_override_fallback_mode,
    context_viewport_size,
    dense_rotation_fallback_mode,
    has_mixed_ltr_rtl_text,
    source_text_svg_payload,
)
from svg2ooxml.core.ir.text.layout import estimate_text_bbox
from svg2ooxml.core.ir.text.positioning_metadata import PerCharacterTextLayout
from svg2ooxml.core.ir.text.positioning_metadata import (
    has_rotate_tree as _has_rotate_tree_impl,
)
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.scene import Image
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame
from svg2ooxml.policy.text_policy import TextPolicyDecision


class TextFallbackMixin:
    """Fallback conversion paths shared by the text conversion coordinator."""

    def _convert_bidi_override_text_fallback(
        self,
        *,
        element: etree._Element,
        text_content: str,
        metadata: dict[str, Any],
        style_attr: str,
        decision: TextPolicyDecision | None,
    ) -> Image | None:
        if not uses_bidi_override(element, style_attr):
            return None
        if not has_mixed_ltr_rtl_text(text_content):
            return None
        mode = bidi_override_fallback_mode(decision)
        if mode not in {"svg", "svg_image"}:
            return None

        # TODO(0.9): Replace this fallback with a typed bidi visual-order
        # evaluator so bidi-override mixed-script text can stay native/editable.
        return self._convert_svg_text_fallback(
            element=element,
            metadata=metadata,
            mode=mode,
            policy_key="bidi_override_fallback",
            image_source="bidi_override_text",
            reason="bidi_override_mixed_script",
            split="bidi_override_fallback",
        )

    def _convert_dense_rotated_text_fallback(
        self,
        *,
        element: etree._Element,
        metadata: dict[str, Any],
        decision: TextPolicyDecision | None,
    ) -> Image | None:
        mode = dense_rotation_fallback_mode(decision)
        if mode in {"auto", "auto_vector_outline"}:
            if self._vector_outline_available():
                return None
            reason = (
                "dense_tspan_rotation_skia_unavailable"
                if has_tspan_descendant(element)
                else "dense_per_character_rotation_skia_unavailable"
            )
            return self._convert_svg_text_fallback(
                element=element,
                metadata=metadata,
                mode="svg",
                policy_key="dense_rotation_fallback",
                image_source="dense_rotated_text",
                reason=reason,
                split="dense_rotation_fallback",
                requested_mode=mode,
            )
        if mode not in {"svg", "svg_image"}:
            if mode in {"vector_outline", "outline", "glyph_outline"}:
                if self._vector_outline_available():
                    return None
                return self._convert_svg_text_fallback(
                    element=element,
                    metadata=metadata,
                    mode="svg",
                    policy_key="dense_rotation_fallback",
                    image_source="dense_rotated_text",
                    reason="dense_per_character_rotation_skia_unavailable",
                    split="dense_rotation_fallback",
                    requested_mode=mode,
                )
            return None

        return self._convert_svg_text_fallback(
            element=element,
            metadata=metadata,
            mode=mode,
            policy_key="dense_rotation_fallback",
            image_source="dense_rotated_text",
            reason="dense_per_character_rotation",
            split="dense_rotation_fallback",
        )

    def _convert_svg_text_fallback(
        self,
        *,
        element: etree._Element,
        metadata: dict[str, Any],
        mode: str,
        policy_key: str,
        image_source: str,
        reason: str,
        split: str,
        requested_mode: str | None = None,
    ) -> Image | None:
        svg_payload = source_text_svg_payload(
            element,
            viewport_size=context_viewport_size(self._context),
        )
        if svg_payload is None:
            return None

        width_px, height_px = svg_payload[1]
        image_metadata = split_text_metadata(metadata)
        image_metadata.setdefault("policy", {}).setdefault("text", {})[policy_key] = (
            mode
        )
        image_metadata["image_source"] = image_source
        image_metadata["text_fallback"] = {
            "mode": mode,
            "reason": reason,
        }
        if requested_mode and requested_mode != mode:
            image_metadata["text_fallback"]["requested_mode"] = requested_mode
        image = Image(
            origin=Point(0.0, 0.0),
            size=Rect(0.0, 0.0, width_px, height_px),
            data=svg_payload[0],
            format="svg",
            opacity=1.0,
            metadata=image_metadata,
        )
        trace_stage = getattr(self._context, "trace_stage", None)
        if callable(trace_stage):
            trace_stage(
                "text_frame",
                stage="text",
                subject=element.get("id"),
                metadata={
                    "run_count": 1,
                    "resvg_only": False,
                    "split": split,
                    "fallback": mode,
                },
            )
        self._context.trace_geometry_decision(element, "svg", image.metadata)
        return image

    def _convert_sparse_rotated_text(
        self,
        *,
        element: etree._Element,
        layout: PerCharacterTextLayout,
        run: Run,
        metadata: dict[str, Any],
        direction: str | None,
        decision: TextPolicyDecision | None,
        font_service: Any,
    ) -> list[TextFrame]:
        frames: list[TextFrame] = []
        for start, end, outline in split_rotation_ranges(layout):
            text = layout.text[start:end]
            if not text.strip():
                continue
            segment_run = replace(run, text=text)
            origin_x = layout.abs_x[start]
            origin_y = layout.abs_y[start]
            segment_metadata = split_text_metadata(metadata)
            if outline:
                segment_metadata["per_char"] = {
                    "abs_x": layout.abs_x[start:end],
                    "abs_y": layout.abs_y[start:end],
                    "rotate": layout.rotate[start:end],
                }
                bbox = layout_range_bbox(layout, start, end, segment_run.font_size_pt)
            else:
                bbox = estimate_text_bbox(
                    [segment_run],
                    origin_x,
                    origin_y,
                    font_service=font_service,
                )

            frame = TextFrame(
                origin=Point(origin_x, origin_y),
                anchor=TextAnchor.START,
                bbox=bbox,
                runs=[segment_run],
                baseline_shift=0.0,
                direction=direction,
                metadata=segment_metadata,
            )
            if self._pipeline is not None:
                frame = self._pipeline.plan_frame(frame, [segment_run], decision)
            if self._smart_font_bridge is not None:
                frame = self._smart_font_bridge.enhance_frame(
                    frame, [segment_run], decision
                )

            trace_stage = getattr(self._context, "trace_stage", None)
            if callable(trace_stage):
                trace_stage(
                    "text_frame",
                    stage="text",
                    subject=element.get("id"),
                    metadata={
                        "run_count": 1,
                        "resvg_only": outline,
                        "decision": getattr(decision, "value", decision),
                        "split": "rotated_outline" if outline else "native",
                    },
                )
            self._context.trace_geometry_decision(
                element,
                "resvg" if outline else "native",
                frame.metadata,
            )
            frames.append(frame)
        return frames


def split_rotation_ranges(
    layout: PerCharacterTextLayout,
) -> list[tuple[int, int, bool]]:
    ranges: list[tuple[int, int, bool]] = []
    start = 0
    current_outline = outline_char_at(layout, 0) if layout.text else False
    for index in range(1, len(layout.text)):
        outline = outline_char_at(layout, index)
        if outline == current_outline:
            continue
        ranges.append((start, index, current_outline))
        start = index
        current_outline = outline
    if layout.text:
        ranges.append((start, len(layout.text), current_outline))
    return ranges


def outline_char_at(layout: PerCharacterTextLayout, index: int) -> bool:
    return bool(
        layout.text[index].strip()
        and index < len(layout.rotate)
        and abs(layout.rotate[index]) > 1e-9
    )


def split_text_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    split_metadata = deepcopy(dict(metadata))
    split_metadata.pop("resvg_text", None)
    return split_metadata


def layout_range_bbox(
    layout: PerCharacterTextLayout,
    start: int,
    end: int,
    font_size_pt: float,
) -> Rect:
    xs = layout.abs_x[start:end]
    ys = layout.abs_y[start:end]
    advances = layout.advances[start:end]
    left = min(xs)
    right = max(x + advance for x, advance in zip(xs, advances, strict=False))
    baseline_top = min(ys)
    baseline_bottom = max(ys)
    ascent = font_size_pt
    descent = font_size_pt * 0.25
    top = baseline_top - ascent
    bottom = baseline_bottom + descent
    return Rect(
        left,
        top,
        max(right - left, 0.01),
        max(bottom - top, 0.01),
    )


def has_rotate_tree(element: etree._Element) -> bool:
    return _has_rotate_tree_impl(element)


def has_tspan_descendant(element: etree._Element) -> bool:
    return any(
        local_name(getattr(node, "tag", "")).lower() == "tspan"
        for node in element.iterdescendants()
    )


def uses_bidi_override(element: etree._Element, style_attr: str) -> bool:
    unicode_bidi = element.get("unicode-bidi", "").strip().lower()
    if not unicode_bidi and "unicode-bidi" in style_attr:
        match = re.search(r"unicode-bidi\s*:\s*([^;]+)", style_attr)
        if match:
            unicode_bidi = match.group(1).strip().lower()
    return unicode_bidi == "bidi-override"


def vector_outline_available() -> bool:
    try:
        from svg2ooxml.drawingml.glyph_renderer import SKIA_AVAILABLE
    except Exception:
        return False
    return bool(SKIA_AVAILABLE)


__all__ = [
    "TextFallbackMixin",
    "has_rotate_tree",
    "has_tspan_descendant",
    "layout_range_bbox",
    "split_rotation_ranges",
    "split_text_metadata",
    "uses_bidi_override",
    "vector_outline_available",
]
