"""Viewport-aware length helpers for the lightweight resvg tree."""

from __future__ import annotations

from typing import TYPE_CHECKING

from svg2ooxml.common.conversions.transforms import parse_numeric_list
from svg2ooxml.common.units import UnitConverter
from svg2ooxml.common.units.conversion import ConversionContext

from .parser.options import Options

if TYPE_CHECKING:
    from .parser.tree import SvgNode

_UNIT_CONVERTER = UnitConverter()
_DEFAULT_VIEWPORT_WIDTH = 100.0
_DEFAULT_VIEWPORT_HEIGHT = 100.0


def parse_length_px(
    value: str | None,
    context: ConversionContext,
    *,
    axis: str,
    default: float = 0.0,
) -> float:
    if value is None:
        return default
    token = value.strip()
    if not token:
        return default
    try:
        return _UNIT_CONVERTER.to_px(token, context, axis=axis)
    except ValueError:
        return _parse_number(token, default)


def initial_viewport_context(
    node: SvgNode,
    options: Options | None,
) -> ConversionContext:
    default_size = options.default_size if options is not None else None
    default_width = default_size.width if default_size is not None else _DEFAULT_VIEWPORT_WIDTH
    default_height = default_size.height if default_size is not None else _DEFAULT_VIEWPORT_HEIGHT
    font_size = _options_font_size(options)
    base_context = _UNIT_CONVERTER.create_context(
        width=default_width,
        height=default_height,
        parent_width=default_width,
        parent_height=default_height,
        viewport_width=default_width,
        viewport_height=default_height,
        font_size=font_size,
        root_font_size=font_size,
    )

    width = parse_length_px(node.attributes.get("width"), base_context, axis="x", default=default_width)
    height = parse_length_px(node.attributes.get("height"), base_context, axis="y", default=default_height)

    view_box = _parse_view_box(node.attributes.get("viewBox"))
    if view_box is not None:
        _, _, view_box_width, view_box_height = view_box
        width = view_box_width if width <= 0 else width
        height = view_box_height if height <= 0 else height

    width = width if width > 0 else default_width
    height = height if height > 0 else default_height
    return _UNIT_CONVERTER.create_context(
        width=width,
        height=height,
        parent_width=width,
        parent_height=height,
        viewport_width=width,
        viewport_height=height,
        font_size=font_size,
        root_font_size=font_size,
    )


def derive_svg_viewport_context(
    attributes: dict[str, str],
    context: ConversionContext,
    options: Options | None,
) -> ConversionContext:
    width = parse_length_px(attributes.get("width"), context, axis="x", default=context.width)
    height = parse_length_px(attributes.get("height"), context, axis="y", default=context.height)
    view_box = _parse_view_box(attributes.get("viewBox"))
    if view_box is not None:
        _, _, view_box_width, view_box_height = view_box
        width = view_box_width if width <= 0 else width
        height = view_box_height if height <= 0 else height

    width = width if width > 0 else context.width
    height = height if height > 0 else context.height
    return context.derive(width=width, height=height, font_size=_options_font_size(options))


def _options_font_size(options: Options | None) -> float:
    return options.font_size if options is not None else 12.0


def _parse_number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    token = value.strip()
    if not token:
        return default
    try:
        if token.endswith("%"):
            return float(token[:-1]) / 100.0
        return float(token)
    except ValueError:
        return default


def _parse_view_box(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    numbers = tuple(parse_numeric_list(raw))
    if len(numbers) != 4:
        return None
    return numbers[0], numbers[1], numbers[2], numbers[3]
