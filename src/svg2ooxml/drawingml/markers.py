"""Marker XML utilities for DrawingML generation."""

from __future__ import annotations

import re
from collections.abc import Mapping

from lxml import etree

from svg2ooxml.drawingml.xml_builder import a_elem

__all__ = ["marker_end_elements"]


_DEFAULT_END_STYLE: tuple[str, str, str] = ("triangle", "med", "med")
_ALLOWED_MARKER_TYPES = {"none", "triangle", "stealth", "diamond", "oval", "arrow"}
_ALLOWED_MARKER_SIZES = {"sm", "med", "lg"}
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_marker_hint(marker_id: str) -> str:
    return _NON_ALNUM_RE.sub(" ", marker_id.strip().lower())


def _has_token(words: list[str], tokens: tuple[str, ...]) -> bool:
    return any(token in words for token in tokens)


def _infer_marker_style(marker_hint: str | None) -> tuple[str, str, str]:
    if not marker_hint:
        return _DEFAULT_END_STYLE

    words = _normalize_marker_hint(marker_hint).split()

    marker_type = "triangle"
    if _has_token(words, ("stealth", "vee", "chevron")):
        marker_type = "stealth"
    elif _has_token(words, ("diamond", "rhomb")):
        marker_type = "diamond"
    elif _has_token(words, ("circle", "dot", "oval", "round", "disc")):
        marker_type = "oval"
    elif _has_token(words, ("arrow", "arrowhead")):
        marker_type = "arrow"

    marker_size = "med"
    if _has_token(words, ("small", "sm", "tiny", "mini", "xs")):
        marker_size = "sm"
    elif _has_token(words, ("large", "lg", "big", "xl", "xlarge")):
        marker_size = "lg"

    return marker_type, marker_size, marker_size


def _style_from_profile(profile: Mapping[str, object] | None) -> tuple[str, str, str] | None:
    if not isinstance(profile, Mapping):
        return None
    marker_type = str(profile.get("type", "")).strip().lower()
    if marker_type not in _ALLOWED_MARKER_TYPES:
        return None
    size = str(profile.get("size", "med")).strip().lower()
    if size not in _ALLOWED_MARKER_SIZES:
        size = "med"
    return marker_type, size, size


def _resolve_marker_style(
    marker_hint: str | None,
    marker_profile: Mapping[str, object] | None,
) -> tuple[str, str, str]:
    from_profile = _style_from_profile(marker_profile)
    if from_profile is not None:
        return from_profile
    return _infer_marker_style(marker_hint)


def marker_end_elements(
    markers: Mapping[str, str],
    *,
    marker_profiles: Mapping[str, Mapping[str, object]] | None = None,
) -> tuple[etree._Element | None, etree._Element | None]:
    """Return DrawingML marker elements for stroke ends.

    Args:
        markers: Mapping of marker positions ("start", "end") to marker types
        marker_profiles: Optional mapping of positions to deterministic
            marker style profiles derived from marker geometry.

    Returns:
        Tuple of (head_elem, tail_elem) — each is an lxml Element or None
    """
    if not markers:
        return None, None

    head_marker = markers.get("end")
    tail_marker = markers.get("start")
    profiles = marker_profiles or {}

    head_elem = None
    if head_marker:
        head_type, head_w, head_len = _resolve_marker_style(head_marker, profiles.get("end"))
        head_elem = a_elem("headEnd", type=head_type, w=head_w, len=head_len)

    tail_elem = None
    if tail_marker:
        tail_type, tail_w, tail_len = _resolve_marker_style(tail_marker, profiles.get("start"))
        tail_elem = a_elem("tailEnd", type=tail_type, w=tail_w, len=tail_len)

    return head_elem, tail_elem
