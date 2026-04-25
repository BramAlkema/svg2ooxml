"""ViewBox resolution utilities for traversal and styling."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from lxml import etree

from svg2ooxml.common.geometry.transforms.matrix import Matrix2D
from svg2ooxml.common.units import ConversionContext, UnitConverter

ALIGN_MAP: Final[dict[str, tuple[float, float]]] = {
    "xminymin": (0.0, 0.0),
    "xmidymin": (0.5, 0.0),
    "xmaxymin": (1.0, 0.0),
    "xminymid": (0.0, 0.5),
    "xmidymid": (0.5, 0.5),
    "xmaxymid": (1.0, 0.5),
    "xminymax": (0.0, 1.0),
    "xmidymax": (0.5, 1.0),
    "xmaxymax": (1.0, 1.0),
}
_NUMBER_RE = re.compile(r"[-+]?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[eE][-+]?\d+)?")
_NUMERIC_SEPARATOR_RE = re.compile(r"^[\s,]*$")


@dataclass(slots=True, frozen=True)
class PreserveAspectRatio:
    align: str = "xMidYMid"
    meet_or_slice: str = "meet"  # meet | slice
    defer: bool = False

    @property
    def is_none(self) -> bool:
        return self.align.lower() == "none"


@dataclass(slots=True, frozen=True)
class ViewBox:
    min_x: float
    min_y: float
    width: float
    height: float

    @classmethod
    def from_tuple(cls, value: tuple[float, float, float, float]) -> ViewBox:
        return cls(*value)


@dataclass(slots=True, frozen=True)
class Viewport:
    width: float
    height: float


@dataclass(slots=True, frozen=True)
class ViewBoxResult:
    scale_x: float
    scale_y: float
    translate_x: float
    translate_y: float
    clip_width: float
    clip_height: float
    preserve_aspect_ratio: PreserveAspectRatio

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.scale_x, self.scale_y, self.translate_x, self.translate_y


class ViewportEngine:
    """Resolve SVG viewBox + preserveAspectRatio semantics."""

    def compute(
        self,
        view_box: tuple[float, float, float, float] | ViewBox,
        viewport: tuple[float, float] | Viewport,
        preserve_aspect_ratio: str | PreserveAspectRatio | None = None,
    ) -> ViewBoxResult:
        vb = view_box if isinstance(view_box, ViewBox) else ViewBox.from_tuple(view_box)
        vp = viewport if isinstance(viewport, Viewport) else Viewport(*viewport)
        par = (
            preserve_aspect_ratio
            if isinstance(preserve_aspect_ratio, PreserveAspectRatio)
            else parse_preserve_aspect_ratio(preserve_aspect_ratio)
        )

        if vb.width <= 0 or vb.height <= 0:
            raise ValueError("viewBox width/height must be positive")
        if vp.width <= 0 or vp.height <= 0:
            raise ValueError("viewport width/height must be positive")

        if par.is_none:
            scale_x = vp.width / vb.width
            scale_y = vp.height / vb.height
            translate_x = -vb.min_x * scale_x
            translate_y = -vb.min_y * scale_y
            return ViewBoxResult(
                scale_x=scale_x,
                scale_y=scale_y,
                translate_x=translate_x,
                translate_y=translate_y,
                clip_width=vp.width,
                clip_height=vp.height,
                preserve_aspect_ratio=par,
            )

        uniform_scale = self._resolve_uniform_scale(vb, vp, par.meet_or_slice)
        align = ALIGN_MAP.get(par.align.lower())
        if align is None:
            raise ValueError(f"unknown preserveAspectRatio alignment {par.align!r}")

        offset_x = (vp.width - vb.width * uniform_scale) * align[0]
        offset_y = (vp.height - vb.height * uniform_scale) * align[1]
        translate_x = -vb.min_x * uniform_scale + offset_x
        translate_y = -vb.min_y * uniform_scale + offset_y

        return ViewBoxResult(
            scale_x=uniform_scale,
            scale_y=uniform_scale,
            translate_x=translate_x,
            translate_y=translate_y,
            clip_width=vp.width,
            clip_height=vp.height,
            preserve_aspect_ratio=par,
        )

    @staticmethod
    def _resolve_uniform_scale(vb: ViewBox, vp: Viewport, mode: str) -> float:
        scale_x = vp.width / vb.width
        scale_y = vp.height / vb.height
        if mode.lower() == "slice":
            return max(scale_x, scale_y)
        return min(scale_x, scale_y)

    @staticmethod
    def to_matrix(result: ViewBoxResult) -> Matrix2D:
        """Convert a ``ViewBoxResult`` into a transform matrix."""

        return Matrix2D.from_values(
            result.scale_x,
            0.0,
            0.0,
            result.scale_y,
            result.translate_x,
            result.translate_y,
        )


def parse_preserve_aspect_ratio(value: str | None) -> PreserveAspectRatio:
    """Parse preserveAspectRatio strings, mirroring SVG semantics."""

    if value is None or not value.strip():
        return PreserveAspectRatio()

    tokens = value.replace(",", " ").split()
    defer = False
    if tokens and tokens[0].lower() == "defer":
        defer = True
        tokens = tokens[1:]

    if not tokens:
        return PreserveAspectRatio(defer=defer)

    align_token = tokens[0].lower()
    if align_token == "none":
        return PreserveAspectRatio(align="none", meet_or_slice="meet", defer=defer)

    align = align_token if align_token in ALIGN_MAP else "xMidYMid"
    mos = tokens[1].lower() if len(tokens) > 1 else "meet"
    if mos not in {"meet", "slice"}:
        mos = "meet"
    return PreserveAspectRatio(align=align, meet_or_slice=mos, defer=defer)


def compute_viewbox(
    view_box: tuple[float, float, float, float],
    viewport: tuple[float, float],
    preserve_aspect_ratio: str | None = None,
) -> ViewBoxResult:
    """Functional façade mirroring the legacy helper."""

    engine = ViewportEngine()
    return engine.compute(view_box, viewport, preserve_aspect_ratio)


def parse_viewbox_attribute(value: str | None) -> ViewBox | None:
    """Parse the value of the SVG ``viewBox`` attribute."""

    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    parts = _parse_viewbox_numbers(cleaned)
    if len(parts) != 4:
        raise ValueError(f"viewBox must provide four numbers (got {value!r})")
    min_x, min_y, width, height = parts
    if width <= 0 or height <= 0:
        raise ValueError("viewBox width/height must be positive")
    return ViewBox(min_x, min_y, width, height)


def _parse_viewbox_numbers(value: str) -> list[float]:
    values: list[float] = []
    position = 0
    for match in _NUMBER_RE.finditer(value):
        separator = value[position : match.start()]
        if not _NUMERIC_SEPARATOR_RE.match(separator):
            raise ValueError(f"viewBox contains non-numeric values: {value!r}")
        values.append(float(match.group(0)))
        position = match.end()
    if not _NUMERIC_SEPARATOR_RE.match(value[position:]):
        raise ValueError(f"viewBox contains non-numeric values: {value!r}")
    return values


def resolve_viewbox_dimensions(
    svg_root: etree._Element,
    unit_converter: UnitConverter,
    *,
    default_width: float = 800.0,
    default_height: float = 600.0,
    context: ConversionContext | None = None,
) -> tuple[float, float, ViewBox | None, PreserveAspectRatio]:
    """Resolve viewport dimensions and related metadata for an SVG element."""

    width_attr = svg_root.get("width")
    height_attr = svg_root.get("height")
    viewbox = parse_viewbox_attribute(svg_root.get("viewBox"))
    preserve = parse_preserve_aspect_ratio(svg_root.get("preserveAspectRatio"))

    width_px = _to_px_safely(unit_converter, width_attr, context=context, axis="width")
    height_px = _to_px_safely(unit_converter, height_attr, context=context, axis="height")

    if width_px is None and viewbox is not None:
        width_px = viewbox.width
    if height_px is None and viewbox is not None:
        height_px = viewbox.height

    if width_px is None:
        width_px = default_width
    if height_px is None:
        height_px = default_height

    return width_px, height_px, viewbox, preserve


def viewbox_matrix_from_element(
    svg_root: etree._Element,
    unit_converter: UnitConverter,
    *,
    default_width: float = 800.0,
    default_height: float = 600.0,
    context: ConversionContext | None = None,
) -> tuple[Matrix2D, ViewBoxResult]:
    """Convenience helper returning the viewport matrix for ``svg_root``."""

    width_px, height_px, viewbox, preserve = resolve_viewbox_dimensions(
        svg_root,
        unit_converter,
        default_width=default_width,
        default_height=default_height,
        context=context,
    )

    if viewbox is None:
        viewbox = ViewBox(0.0, 0.0, width_px, height_px)

    engine = ViewportEngine()
    result = engine.compute(viewbox, (width_px, height_px), preserve)
    return engine.to_matrix(result), result


def _to_px_safely(
    converter: UnitConverter,
    value: str | None,
    *,
    context: ConversionContext | None = None,
    axis: str | None = None,
) -> float | None:
    if value is None:
        return None
    try:
        return converter.to_px(value, context, axis=axis)
    except Exception:  # pragma: no cover - defensive
        return None


def resolve_viewbox(
    svg_root: etree._Element,
    unit_converter: UnitConverter,
    *,
    default_width: float = 800.0,
    default_height: float = 600.0,
) -> tuple[tuple[float, float], ViewBox | None, PreserveAspectRatio]:
    """Return viewport dimensions and metadata for ``svg_root``."""

    width_px, height_px, viewbox, preserve = resolve_viewbox_dimensions(
        svg_root,
        unit_converter,
        default_width=default_width,
        default_height=default_height,
    )
    return (width_px, height_px), viewbox, preserve


__all__ = [
    "PreserveAspectRatio",
    "ViewBox",
    "ViewBoxResult",
    "Viewport",
    "ViewportEngine",
    "compute_viewbox",
    "parse_preserve_aspect_ratio",
    "parse_viewbox_attribute",
    "resolve_viewbox",
    "resolve_viewbox_dimensions",
    "viewbox_matrix_from_element",
]
