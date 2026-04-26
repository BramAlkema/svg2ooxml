"""Text frame and WordArt DrawingML rendering helpers."""

from __future__ import annotations

import logging

from svg2ooxml.common.conversions.bidi import is_rtl_text
from svg2ooxml.drawingml.generator import px_to_emu
from svg2ooxml.drawingml.shape_attrs import descr_attr, rot_attr, vert_attr
from svg2ooxml.drawingml.text_runs_runtime import resolve_runs_xml
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.text import TextAnchor, TextFrame, WordArtCandidate


def render_textframe(
    frame: TextFrame,
    shape_id: int,
    *,
    template: str,
    policy_for,
    logger: logging.Logger,
    hyperlink_xml: str = "",
    register_run_navigation=None,
) -> str:
    bbox = frame.bbox
    rtl = _is_frame_rtl(frame)
    align = _resolve_alignment(frame.anchor, rtl=rtl)

    policy_text = policy_for(getattr(frame, "metadata", None), "text")
    note_parts: list[str] = []
    behavior = policy_text.get("rendering_behavior")
    if isinstance(behavior, str) and behavior:
        note_parts.append(f"rendering_behavior={behavior}")
        if behavior != "outline":
            logger.warning(
                "Text frame %s requests %s rendering; emitting live text until fallback support lands.",
                shape_id,
                behavior,
            )
    fallback_font = policy_text.get("font_fallback")
    if isinstance(fallback_font, str) and fallback_font:
        note_parts.append(f"font_fallback={fallback_font}")

    shape_name = f"Text {shape_id}"
    if note_parts:
        logger.debug("Text frame %s policy notes: %s", shape_id, "; ".join(note_parts))

    runs_xml = resolve_runs_xml(frame, register_run_navigation)

    return template.format(
        SHAPE_ID=shape_id,
        SHAPE_NAME=shape_name,
        X_EMU=px_to_emu(bbox.x),
        Y_EMU=px_to_emu(bbox.y),
        WIDTH_EMU=px_to_emu(bbox.width),
        HEIGHT_EMU=px_to_emu(bbox.height),
        TEXT_ALIGN=align,
        RTL_ATTR=' rtl="1"' if rtl else "",
        RUNS_XML=runs_xml,
        HYPERLINK_XML=hyperlink_xml,
        DESCR_ATTR=descr_attr(getattr(frame, "metadata", None)),
        VERT_ATTR=vert_attr(getattr(frame, "metadata", None)),
        ROT_ATTR=rot_attr(getattr(frame, "metadata", None)),
    )


def render_wordart(
    frame: TextFrame,
    candidate: WordArtCandidate,
    shape_id: int,
    *,
    template: str,
    policy_for,
    logger: logging.Logger,
    hyperlink_xml: str = "",
    register_run_navigation=None,
) -> str:
    bbox = _normalize_wordart_bbox(frame, candidate)
    rtl = _is_frame_rtl(frame)
    align = _resolve_alignment(frame.anchor, rtl=rtl)

    policy_text = policy_for(getattr(frame, "metadata", None), "text")
    note_parts: list[str] = []
    if policy_text:
        for key, value in sorted(policy_text.items()):
            note_parts.append(f"{key}={value}")

    if candidate.fallback_strategy:
        note_parts.append(f"fallback={candidate.fallback_strategy}")
    note_parts.append(f"confidence={candidate.confidence:.2f}")

    shape_name = f"WordArt {shape_id}"
    if note_parts:
        logger.debug("WordArt %s policy notes: %s", shape_id, "; ".join(note_parts))

    runs_xml = resolve_runs_xml(frame, register_run_navigation)
    body_extra = ""

    if candidate.fallback_strategy and candidate.fallback_strategy != "vector_outline":
        logger.info(
            "WordArt %s prefers native preset '%s' with fallback %s",
            shape_id,
            candidate.preset,
            candidate.fallback_strategy,
        )

    return template.format(
        SHAPE_ID=shape_id,
        SHAPE_NAME=shape_name,
        X_EMU=px_to_emu(bbox.x),
        Y_EMU=px_to_emu(bbox.y),
        WIDTH_EMU=px_to_emu(bbox.width),
        HEIGHT_EMU=px_to_emu(bbox.height),
        TEXT_ALIGN=align,
        RTL_ATTR=' rtl="1"' if rtl else "",
        WARP_PRESET=candidate.preset,
        BODY_EXTRA=body_extra,
        RUNS_XML=runs_xml,
        HYPERLINK_XML=hyperlink_xml,
        DESCR_ATTR=descr_attr(getattr(frame, "metadata", None)),
        VERT_ATTR=vert_attr(getattr(frame, "metadata", None)),
        ROT_ATTR=rot_attr(getattr(frame, "metadata", None)),
    )


def _is_frame_rtl(frame: TextFrame) -> bool:
    """Determine if a text frame should use RTL paragraph direction."""
    direction = getattr(frame, "direction", None)
    if direction == "rtl":
        return True
    if direction == "ltr":
        return False
    text = frame.text_content
    return bool(text) and is_rtl_text(text)


def _resolve_alignment(anchor: TextAnchor, *, rtl: bool) -> str:
    """Map text-anchor to DrawingML alignment, flipping for RTL."""
    if rtl:
        return {
            TextAnchor.START: "r",
            TextAnchor.MIDDLE: "ctr",
            TextAnchor.END: "l",
        }.get(anchor, "r")
    return {
        TextAnchor.START: "l",
        TextAnchor.MIDDLE: "ctr",
        TextAnchor.END: "r",
    }.get(anchor, "l")


_LOW_PROFILE_WORDART_PRESETS = frozenset(
    {
        "textPlain",
        "textArchUp",
        "textArchDown",
        "textWave1",
        "textSlantUp",
        "textSlantDown",
    }
)
_MEDIUM_PROFILE_WORDART_PRESETS = frozenset(
    {
        "textCanUp",
        "textCanDown",
        "textInflate",
        "textDeflate",
        "textInflateTop",
        "textInflateBottom",
    }
)


def _normalize_wordart_bbox(frame: TextFrame, candidate: WordArtCandidate) -> Rect:
    """Tighten WordArt height so it tracks textbox sizing more closely."""
    bbox = frame.bbox
    runs = frame.runs or []
    if bbox.height <= 0.0 or not runs or frame.is_multiline:
        return bbox

    max_font_pt = max((run.font_size_pt for run in runs), default=0.0)
    if max_font_pt <= 0.0:
        return bbox

    if candidate.preset in _LOW_PROFILE_WORDART_PRESETS:
        profile_scale = 1.1
    elif candidate.preset in _MEDIUM_PROFILE_WORDART_PRESETS:
        profile_scale = 1.2
    else:
        return bbox

    max_font_px = max_font_pt * (96.0 / 72.0)
    stroke_padding_px = max((run.stroke_width_px or 0.0 for run in runs), default=0.0)
    target_height = min(
        bbox.height,
        max_font_px * profile_scale + stroke_padding_px,
    )
    if target_height >= bbox.height * 0.98:
        return bbox

    center_y = bbox.y + (bbox.height / 2.0)
    return Rect(
        x=bbox.x,
        y=center_y - (target_height / 2.0),
        width=bbox.width,
        height=target_height,
    )


__all__ = ["render_textframe", "render_wordart"]
