"""<use> expansion helpers for the IR converter."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.common.style.resolver import StyleResolver
from svg2ooxml.core.traversal.viewbox import (
    parse_preserve_aspect_ratio,
    parse_viewbox_attribute,
)


def instantiate_use_target(converter, target: etree._Element, use_element: etree._Element) -> list[etree._Element]:
    clone = deepcopy(target)
    _apply_computed_presentation(converter, target, clone)
    local = converter._local_name(clone.tag)
    if local == "symbol":
        return wrap_symbol_clone(converter, clone, use_element)
    apply_use_attributes(converter, use_element, clone)
    return [clone]


def wrap_symbol_clone(converter, symbol_clone: etree._Element, use_element: etree._Element) -> list[etree._Element]:
    group_tag = converter._make_namespaced_tag(symbol_clone, "g")
    if symbol_clone.nsmap:
        group = etree.Element(group_tag, nsmap=symbol_clone.nsmap)
    else:
        group = etree.Element(group_tag)
    for child in list(symbol_clone):
        group.append(child)
    for attr in ("class", "style"):
        if attr in symbol_clone.attrib:
            group.set(attr, symbol_clone.attrib[attr])
    _apply_computed_presentation(converter, symbol_clone, group)
    apply_use_attributes(converter, use_element, group)
    propagate_symbol_use_attributes(converter, group, use_element)
    return [group]


def apply_use_attributes(converter, use_element: etree._Element, target: etree._Element) -> None:
    skip_attrs = {
        "x",
        "y",
        "width",
        "height",
        "transform",
        "{http://www.w3.org/1999/xlink}href",
        "href",
    }
    for attr, value in use_element.attrib.items():
        if attr in skip_attrs:
            continue
        if attr == "class" and target.get("class"):
            existing = target.get("class")
            target.set("class", f"{existing} {value}".strip())
        elif attr == "style":
            existing = target.get("style") or ""
            merged = value or ""
            if merged and not merged.endswith(";"):
                merged += ";"
            merged = f"{merged}{existing}"
            target.set("style", merged)
        else:
            target.set(attr, value)


def _apply_computed_presentation(converter, source: etree._Element, clone: etree._Element) -> None:
    # Skip if already processed (prevents double-application if called multiple times)
    if clone.get("data-svg2ooxml-use-clone") == "true":
        return

    clone.set("data-svg2ooxml-use-clone", "true")
    style_resolver: StyleResolver | None = getattr(converter, "_style_resolver", None)
    if style_resolver is None:
        return
    css_context = getattr(converter, "_css_context", None)
    try:
        paint_style = style_resolver.compute_paint_style(source, context=css_context)
    except Exception:  # pragma: no cover - defensive
        return

    # Build inline style from computed paint style
    # This ensures the computed styles take precedence over any inherited styles
    style_parts = []

    fill_value = paint_style.get("fill")
    if isinstance(fill_value, str) and fill_value:
        style_parts.append(f"fill:{fill_value}")

    stroke_value = paint_style.get("stroke")
    if isinstance(stroke_value, str) and stroke_value:
        style_parts.append(f"stroke:{stroke_value}")

    fill_opacity = paint_style.get("fill_opacity")
    if fill_opacity is not None and fill_opacity != 1.0:
        style_parts.append(f"fill-opacity:{fill_opacity}")

    stroke_opacity = paint_style.get("stroke_opacity")
    if stroke_opacity is not None and stroke_opacity != 1.0:
        style_parts.append(f"stroke-opacity:{stroke_opacity}")

    stroke_width = paint_style.get("stroke_width_px")
    if stroke_width is not None:
        style_parts.append(f"stroke-width:{stroke_width}px")

    opacity = paint_style.get("opacity")
    if opacity is not None and opacity != 1.0:
        style_parts.append(f"opacity:{opacity}")

    # Append to existing inline style if present, otherwise set new one
    if style_parts:
        existing_style = clone.get("style", "")
        if existing_style and not existing_style.endswith(";"):
            existing_style += ";"
        new_style = existing_style + ";".join(style_parts)
        clone.set("style", new_style)


def propagate_symbol_use_attributes(converter, group: etree._Element, use_element: etree._Element) -> None:
    href_attr = use_element.get("{http://www.w3.org/1999/xlink}href") or use_element.get("href")
    reference_id = converter._normalize_href_reference(href_attr)
    if not reference_id:
        return

    symbol = converter._symbol_definitions.get(reference_id)
    if symbol is None:
        return

    for attr in ("viewBox", "preserveAspectRatio"):
        value = symbol.get(attr)
        if value is not None:
            group.set(attr, value)

    presentation_attrs = (
        "fill",
        "stroke",
        "opacity",
        "fill-opacity",
        "stroke-opacity",
        "stroke-width",
    )
    for attr in presentation_attrs:
        value = use_element.get(attr)
        if value is None:
            continue
        for child in group:
            if child.get(attr) is None:
                child.set(attr, value)


def apply_use_transform(
    converter,
    clones: Iterable[etree._Element],
    matrix: Matrix2D,
    dx: float | None = None,
    dy: float | None = None,
    *,
    tolerance: float,
) -> None:
    combined = matrix
    if dx is not None or dy is not None:
        translate = Matrix2D(1.0, 0.0, 0.0, 1.0, dx or 0.0, dy or 0.0)
        combined = matrix.multiply(translate)
    if combined.is_identity(tolerance=tolerance):
        return
    for clone in clones:
        prepend_transform(clone, combined)


def _compute_use_transform_parts(
    converter,
    element: etree._Element,
    target: etree._Element,
    *,
    tolerance: float,
) -> tuple[Matrix2D, Matrix2D]:
    element_matrix = Matrix2D.identity()
    href_transform = element.get("transform")
    if href_transform:
        element_matrix = element_matrix.multiply(converter._matrix_from_transform(href_transform))

    content_matrix = Matrix2D.identity()

    context = converter._conversion_context
    if context is None:
        return element_matrix, content_matrix

    viewbox_attr = element.get("viewBox") or target.get("viewBox")
    viewbox = parse_viewbox_attribute(viewbox_attr)

    width_px = converter._resolve_dimension_preference(
        element.get("width"),
        target.get("width"),
        context,
        axis="x",
    )
    height_px = converter._resolve_dimension_preference(
        element.get("height"),
        target.get("height"),
        context,
        axis="y",
    )

    if viewbox is not None:
        if width_px is None:
            width_px = viewbox.width
        if height_px is None:
            height_px = viewbox.height
        if width_px is None or height_px is None:
            return element_matrix, content_matrix
        preserve_attr = element.get("preserveAspectRatio") or target.get("preserveAspectRatio")
        preserve = parse_preserve_aspect_ratio(preserve_attr)
        try:
            result = converter._viewport_engine.compute(
                viewbox,
                (width_px, height_px),
                preserve,
            )
        except Exception:
            return element_matrix, content_matrix
        content_matrix = Matrix2D(
            result.scale_x,
            0.0,
            0.0,
            result.scale_y,
            result.translate_x,
            result.translate_y,
        )
        return element_matrix, content_matrix

    target_width = converter._resolve_length(target.get("width"), context, axis="x")
    target_height = converter._resolve_length(target.get("height"), context, axis="y")
    if (
        width_px not in (None, 0.0)
        and height_px not in (None, 0.0)
        and target_width not in (None, 0.0)
        and target_height not in (None, 0.0)
    ):
        scale_x = width_px / target_width
        scale_y = height_px / target_height
        if abs(scale_x - 1.0) > tolerance or abs(scale_y - 1.0) > tolerance:
            content_matrix = Matrix2D(scale_x, 0.0, 0.0, scale_y, 0.0, 0.0)
    return element_matrix, content_matrix


def compute_use_transform(
    converter,
    element: etree._Element,
    target: etree._Element,
    *,
    tolerance: float,
) -> Matrix2D | None:
    element_matrix, content_matrix = _compute_use_transform_parts(
        converter,
        element,
        target,
        tolerance=tolerance,
    )
    return element_matrix.multiply(content_matrix)


def compose_use_transform(
    converter,
    element: etree._Element,
    target: etree._Element,
    *,
    tolerance: float,
) -> Matrix2D:
    element_matrix, content_matrix = _compute_use_transform_parts(
        converter,
        element,
        target,
        tolerance=tolerance,
    )
    dx, dy = resolve_use_offsets(converter, element)
    translation = Matrix2D(1.0, 0.0, 0.0, 1.0, dx, dy)
    return element_matrix.multiply(translation).multiply(content_matrix)


def resolve_use_offsets(converter, element: etree._Element) -> tuple[float, float]:
    context = converter._conversion_context
    dx = converter._resolve_length(element.get("x"), context, axis="x")
    dy = converter._resolve_length(element.get("y"), context, axis="y")
    return dx or 0.0, dy or 0.0


def prepend_transform(element: etree._Element, matrix: Matrix2D) -> None:
    token = matrix_to_string(matrix)
    existing = element.get("transform")
    if existing:
        element.set("transform", f"{token} {existing}")
    else:
        element.set("transform", token)


def matrix_to_string(matrix: Matrix2D) -> str:
    return f"matrix({matrix.a:.6g} {matrix.b:.6g} {matrix.c:.6g} {matrix.d:.6g} {matrix.e:.6g} {matrix.f:.6g})"


__all__ = [
    "apply_use_attributes",
    "apply_use_transform",
    "compose_use_transform",
    "compute_use_transform",
    "instantiate_use_target",
    "propagate_symbol_use_attributes",
    "resolve_use_offsets",
    "_apply_computed_presentation",
    "wrap_symbol_clone",
]
