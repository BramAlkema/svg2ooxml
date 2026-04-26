"""Lightweight gradient analysis and optimisation helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from lxml import etree

from svg2ooxml.color.models import Color
from svg2ooxml.color.parsers import parse_color
from svg2ooxml.common.style.css_values import parse_style_declarations
from svg2ooxml.common.svg_refs import local_name


class GradientComplexity(Enum):
    """Broad-strokes classification used by the gradient processor."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    UNSUPPORTED = "unsupported"


class GradientOptimisation(Enum):
    """Optimisations the processor may recommend."""

    LIMIT_STOP_COUNT = "limit_stop_count"
    FLATTEN_TRANSFORM = "flatten_transform"
    NORMALISE_SPREAD = "normalise_spread"
    SANITISE_COLORSPACE = "sanitise_colorspace"


@dataclass(frozen=True)
class GradientMetrics:
    """Quantitative metrics captured during analysis."""

    stop_count: int
    unique_colors: int
    transform_complexity: float
    has_spread: bool


@dataclass(frozen=True)
class GradientOptimisationPlan:
    """Actionable plan returned by the gradient processor."""

    simplify_to: int | None
    flatten_transform: bool
    normalise_spread: bool
    sanitise_color_space: bool
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class GradientAnalysis:
    """Full analysis payload returned by :class:`GradientProcessor`."""

    gradient_type: str
    complexity: GradientComplexity
    metrics: GradientMetrics
    plan: GradientOptimisationPlan


class GradientProcessor:
    """Inspect SVG gradient definitions and recommend transformations."""

    def __init__(self) -> None:
        self._cache: dict[str, GradientAnalysis] = {}
        self.stats: dict[str, int] = {
            "analysed": 0,
            "cache_hits": 0,
            "simplified": 0,
            "flattened": 0,
        }

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def analyse(self, element: etree._Element, *, context: Any | None = None) -> GradientAnalysis:
        """Analyse *element* and return the optimisation plan."""

        cache_key = self._cache_key(element)
        cached = self._cache.get(cache_key)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached

        self.stats["analysed"] += 1

        gradient_type = self._gradient_type(element)
        stops = list(self._iter_stops(element))
        stop_colors = [self._stop_color(stop) for stop in stops]
        unique_colors = len({color for color in stop_colors if color is not None})
        transform_complexity = self._transform_complexity(element)
        has_spread = (element.get("spreadMethod") or "").strip() not in {"", "pad"}

        metrics = GradientMetrics(
            stop_count=len(stops),
            unique_colors=unique_colors,
            transform_complexity=transform_complexity,
            has_spread=has_spread,
        )

        complexity = self._classify_complexity(metrics, gradient_type)
        plan = self._build_plan(element, metrics, complexity)

        if plan.simplify_to:
            self.stats["simplified"] += 1
        if plan.flatten_transform:
            self.stats["flattened"] += 1

        analysis = GradientAnalysis(
            gradient_type=gradient_type,
            complexity=complexity,
            metrics=metrics,
            plan=plan,
        )
        self._cache[cache_key] = analysis
        return analysis

    def reset_cache(self) -> None:
        self._cache.clear()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _cache_key(self, element: etree._Element) -> str:
        payload = etree.tostring(element, encoding="utf-8", with_tail=False)
        return hashlib.sha1(payload, usedforsecurity=False).hexdigest()

    def _gradient_type(self, element: etree._Element) -> str:
        return local_name(element.tag)

    def _iter_stops(self, element: etree._Element) -> Iterable[etree._Element]:
        for child in element:
            if not hasattr(child, "tag"):
                continue
            if local_name(child.tag) == "stop":
                yield child

    def _stop_color(self, stop: etree._Element) -> Color | None:
        candidate = parse_style_declarations(stop.get("style"))[0].get("stop-color")
        if candidate is None:
            candidate = stop.get("stop-color")
        if candidate is None:
            return None
        try:
            return parse_color(candidate)
        except Exception:
            return None

    def _transform_complexity(self, element: etree._Element) -> float:
        transform = element.get("gradientTransform", "")
        if not transform:
            return 0.0
        # Very coarse approximation: count operations and scale by magnitude.
        ops = transform.replace(",", " ").replace(")", " ) ").split()
        op_count = sum(1 for token in ops if "(" in token)
        magnitude = sum(abs(self._parse_float(token)) for token in ops if self._is_float(token))
        return op_count + min(magnitude / 100.0, 5.0)

    def _parse_float(self, value: str) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0

    def _is_float(self, token: str) -> bool:
        try:
            float(token)
            return True
        except Exception:
            return False

    def _classify_complexity(self, metrics: GradientMetrics, gradient_type: str) -> GradientComplexity:
        if gradient_type not in {"linearGradient", "radialGradient"}:
            return GradientComplexity.UNSUPPORTED

        if metrics.stop_count <= 4 and metrics.transform_complexity == 0.0:
            return GradientComplexity.SIMPLE
        if metrics.stop_count <= 10 and metrics.transform_complexity < 1.5:
            return GradientComplexity.MODERATE
        if metrics.stop_count <= 24 and metrics.transform_complexity < 4.0:
            return GradientComplexity.COMPLEX
        return GradientComplexity.UNSUPPORTED

    def _build_plan(
        self,
        element: etree._Element,
        metrics: GradientMetrics,
        complexity: GradientComplexity,
    ) -> GradientOptimisationPlan:
        simplify_to: int | None = None
        flatten_transform = metrics.transform_complexity > 0.0
        normalise_spread = metrics.has_spread
        sanitise_color_space = element.get("color-interpolation") not in (None, "", "sRGB", "auto")
        notes: list[str] = []

        if metrics.stop_count > 16:
            simplify_to = 12
            notes.append("stop-count>16")
        elif metrics.stop_count > 10 and complexity != GradientComplexity.SIMPLE:
            simplify_to = 10
            notes.append("stop-count>10")

        if flatten_transform:
            notes.append("flatten-transform")
        if normalise_spread:
            notes.append("normalise-spread")
        if sanitise_color_space:
            notes.append("convert-colorspace")

        return GradientOptimisationPlan(
            simplify_to=simplify_to,
            flatten_transform=flatten_transform,
            normalise_spread=normalise_spread,
            sanitise_color_space=sanitise_color_space,
            notes=tuple(notes),
        )


__all__ = [
    "GradientAnalysis",
    "GradientComplexity",
    "GradientMetrics",
    "GradientOptimisation",
    "GradientOptimisationPlan",
    "GradientProcessor",
]
