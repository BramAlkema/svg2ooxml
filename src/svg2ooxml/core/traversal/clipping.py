"""Clip and mask helpers for the IR converter."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping
from dataclasses import replace

from lxml import etree

from svg2ooxml.clipmask.types import ClipDefinition, MaskInfo
from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.common.geometry.segments import transform_segments
from svg2ooxml.common.svg_refs import local_url_id
from svg2ooxml.core.traversal.bridges.resvg_clip_mask_bounds import parse_number
from svg2ooxml.drawingml.generator import DrawingMLPathGenerator, px_to_emu
from svg2ooxml.drawingml.skia_path import skia
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.scene import (
    ClipRef,
    ClipStrategy,
    MaskDefinition,
    MaskInstance,
    MaskMode,
    MaskRef,
)
from svg2ooxml.services import ConversionServices

GeometryPayload = tuple[str, Rect, tuple[int, int]]


def resolve_clip_ref(
    element: etree._Element,
    *,
    clip_definitions: Mapping[str, ClipDefinition],
    services: ConversionServices,
    logger: logging.Logger,
    tolerance: float,
    is_axis_aligned: Callable[[Matrix2D, float], bool],
    use_transform: Matrix2D | None = None,
) -> ClipRef | None:
    clip_attr = element.get("clip-path")
    clip_id = extract_url_id(clip_attr) if clip_attr else None
    if not clip_id:
        return None

    definition = clip_definitions.get(clip_id)
    if definition is None:
        return ClipRef(clip_id=clip_id, strategy=ClipStrategy.NATIVE)
    definition = _definition_in_use_space(definition, use_transform)

    geometry_xml: str | None = None
    geometry_bounds: Rect | None = None
    geometry_size: tuple[int, int] | None = None

    geometry_payload = generate_clip_geometry(
        definition,
        services=services,
        logger=logger,
        tolerance=tolerance,
        is_axis_aligned=is_axis_aligned,
    )
    if geometry_payload is not None:
        geometry_xml, geometry_bounds, geometry_size = geometry_payload

    return ClipRef(
        clip_id=clip_id,
        path_segments=definition.segments,
        bounding_box=definition.bounding_box,
        clip_rule=definition.clip_rule,
        strategy=ClipStrategy.NATIVE,
        transform=definition.transform,
        primitives=definition.primitives,
        custom_geometry_xml=geometry_xml,
        custom_geometry_bounds=geometry_bounds,
        custom_geometry_size=geometry_size,
        skia_path=definition.skia_path,
        is_empty=definition.is_empty,
    )


def _definition_in_use_space(
    definition: ClipDefinition,
    use_transform: Matrix2D | None,
) -> ClipDefinition:
    matrix = _coerce_matrix(use_transform)
    if matrix is None or matrix.is_identity(tolerance=1e-9):
        return definition

    existing_transform = definition.transform or Matrix2D.identity()
    return replace(
        definition,
        segments=tuple(transform_segments(definition.segments, matrix.transform_point)),
        bounding_box=_transform_rect(definition.bounding_box, matrix),
        transform=matrix.multiply(existing_transform),
        primitives=_transform_primitives(definition.primitives, matrix),
        skia_path=_transform_skia_path(definition.skia_path, matrix),
    )


def _coerce_matrix(value: object) -> Matrix2D | None:
    if value is None:
        return None
    if isinstance(value, Matrix2D):
        return value
    values = [getattr(value, name, None) for name in ("a", "b", "c", "d", "e", "f")]
    if all(isinstance(item, (int, float)) for item in values):
        return Matrix2D(*(float(item) for item in values))
    return None


def _transform_rect(rect: Rect, matrix: Matrix2D) -> Rect:
    corners = (
        matrix.transform_xy(rect.x, rect.y),
        matrix.transform_xy(rect.x + rect.width, rect.y),
        matrix.transform_xy(rect.x + rect.width, rect.y + rect.height),
        matrix.transform_xy(rect.x, rect.y + rect.height),
    )
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    min_x = min(xs)
    min_y = min(ys)
    return Rect(min_x, min_y, max(xs) - min_x, max(ys) - min_y)


def _transform_primitives(
    primitives: tuple[dict[str, object], ...],
    matrix: Matrix2D,
) -> tuple[dict[str, object], ...]:
    transformed: list[dict[str, object]] = []
    for primitive in primitives:
        item = dict(primitive)
        existing = _matrix_from_tuple(item.get("transform")) or Matrix2D.identity()
        item["transform"] = _matrix_tuple(matrix.multiply(existing))
        transformed.append(item)
    return tuple(transformed)


def _matrix_from_tuple(value: object) -> Matrix2D | None:
    if not isinstance(value, (list, tuple)) or len(value) != 6:
        return None
    try:
        return Matrix2D(*(float(item) for item in value))
    except (TypeError, ValueError):
        return None


def _matrix_tuple(matrix: Matrix2D) -> tuple[float, float, float, float, float, float]:
    return (
        float(matrix.a),
        float(matrix.b),
        float(matrix.c),
        float(matrix.d),
        float(matrix.e),
        float(matrix.f),
    )


def _transform_skia_path(path: object, matrix: Matrix2D):
    if path is None or skia is None:
        return path
    try:
        transformed = skia.Path(path)
        skia_matrix = skia.Matrix()
        skia_matrix.setAffine(
            [
                float(matrix.a),
                float(matrix.b),
                float(matrix.c),
                float(matrix.d),
                float(matrix.e),
                float(matrix.f),
            ]
        )
        transformed.transform(skia_matrix)
        return transformed
    except Exception:
        return path


def generate_clip_geometry(
    definition: ClipDefinition,
    *,
    services: ConversionServices,
    logger: logging.Logger,
    tolerance: float,
    is_axis_aligned: Callable[[Matrix2D, float], bool],
) -> GeometryPayload | None:
    native_geometry = _generate_native_clip_geometry(
        definition,
        tolerance=tolerance,
        is_axis_aligned=is_axis_aligned,
    )
    if native_geometry is not None:
        return native_geometry

    if not definition.segments:
        return None

    generator = services.ensure_default("drawingml_path_generator")
    if generator is None:
        generator = DrawingMLPathGenerator()
        services.register("drawingml_path_generator", generator)

    try:
        custom_geometry = generator.generate_custom_geometry(
            definition.segments,
            fill_mode="none",
            stroke_mode="false",
            closed=True,
        )
    except Exception:  # pragma: no cover - defensive logging
        logger.debug(
            "Failed to generate custom geometry for clip %s",
            definition.clip_id,
            exc_info=True,
        )
        return None

    return (
        custom_geometry.xml,
        custom_geometry.bounds,
        (custom_geometry.width_emu, custom_geometry.height_emu),
    )


def resolve_mask_ref(
    element: etree._Element,
    *,
    mask_info: Mapping[str, MaskInfo],
) -> tuple[MaskRef | None, MaskInstance | None]:
    mask_attr = element.get("mask")
    mask_id = extract_url_id(mask_attr) if mask_attr else None
    if not mask_id:
        return None, None

    info = mask_info.get(mask_id)
    if info is None:
        mask_ref = MaskRef(mask_id=mask_id)
        return mask_ref, MaskInstance(mask=mask_ref)

    mode = _coerce_mask_mode(info.mode)

    definition = MaskDefinition(
        mask_id=mask_id,
        mask_type=info.mask_type,
        mode=mode,
        mask_units=info.mask_units,
        mask_content_units=info.mask_content_units,
        region=info.region,
        opacity=info.opacity,
        bounding_box=info.bounding_box,
        segments=info.segments,
        content_xml=info.content_xml,
        transform=info.transform,
        primitives=info.primitives,
        raw_region=dict(info.raw_region),
        policy_hints=dict(info.policy_hints),
    )
    mask_ref = MaskRef(
        mask_id=mask_id,
        definition=definition,
        target_bounds=info.bounding_box or info.region,
        target_opacity=info.opacity,
        policy_hints=dict(info.policy_hints),
    )
    mask_instance = MaskInstance(
        mask=mask_ref,
        bounds=info.region or info.bounding_box,
        opacity=info.opacity,
        policy_hints=dict(info.policy_hints),
    )
    return mask_ref, mask_instance


def extract_url_id(token: str | None) -> str | None:
    return local_url_id(token)


def _coerce_mask_mode(value: str | None) -> MaskMode:
    if not value:
        return MaskMode.AUTO
    token = str(value).strip().lower()
    if token == "alpha":
        return MaskMode.ALPHA
    if token == "luminance":
        return MaskMode.LUMINANCE
    return MaskMode.AUTO


def _generate_native_clip_geometry(
    definition: ClipDefinition,
    *,
    tolerance: float,
    is_axis_aligned: Callable[[Matrix2D, float], bool],
) -> GeometryPayload | None:
    if not definition.primitives:
        return None

    bounds = definition.bounding_box
    if bounds.width <= 0 or bounds.height <= 0:
        return None

    primitive_candidates = [
        primitive
        for primitive in definition.primitives
        if primitive.get("type") in {"rect", "circle", "ellipse"}
    ]
    if len(primitive_candidates) != 1:
        return None

    primitive = primitive_candidates[0]
    transform_tuple = primitive.get("transform")
    matrix = Matrix2D(*transform_tuple) if transform_tuple else Matrix2D.identity()

    if not is_axis_aligned(matrix, tolerance):
        return None

    scale_x = abs(matrix.a)
    scale_y = abs(matrix.d)
    if scale_x <= tolerance or scale_y <= tolerance:
        return None

    primitive_type = primitive.get("type")
    snip_emu: int | None = None
    if primitive_type == "rect":
        rx_value = primitive.get("rx")
        ry_value = primitive.get("ry")
        rx = parse_number(rx_value, 0.0)
        ry = parse_number(ry_value, 0.0)
        radius_x = min(rx * scale_x, bounds.width / 2.0)
        radius_y = min(ry * scale_y, bounds.height / 2.0)
        has_round_x = radius_x > tolerance
        has_round_y = radius_y > tolerance

        if not has_round_x and not has_round_y:
            prst = "rect"
            radius_emu = None
        elif has_round_x and has_round_y and math.isclose(
            radius_x, radius_y, rel_tol=0.05, abs_tol=0.5
        ):
            radius_px = min(radius_x, radius_y)
            if radius_px <= tolerance:
                return None
            prst = "roundRect"
            radius_emu = max(px_to_emu(radius_px), 1)
        else:
            prst = "snipRoundRect"
            round_radius = min(
                radius_x if has_round_x else 0.0,
                radius_y if has_round_y else float("inf"),
            )
            snip_radius = max(
                radius_x if has_round_x else 0.0,
                radius_y if has_round_y else 0.0,
            )
            if not has_round_x or not has_round_y:
                round_radius = radius_y if has_round_y else radius_x
                snip_radius = round_radius if snip_radius <= tolerance else snip_radius
            round_radius = max(round_radius, 0.0)
            snip_radius = max(snip_radius, 0.0)
            radius_emu = max(px_to_emu(round_radius), 0) if round_radius > tolerance else 0
            snip_emu = max(px_to_emu(snip_radius), 0)
    else:
        prst = "ellipse"
        radius_emu = None

    width_emu = max(px_to_emu(bounds.width), 1)
    height_emu = max(px_to_emu(bounds.height), 1)
    if prst == "snipRoundRect":
        geometry_xml = (
            f'<a:prstGeom prst="{prst}"><a:avLst>'
            f'<a:gd name="snip" fmla="val {snip_emu}"/>'
            f'<a:gd name="rad" fmla="val {radius_emu}"/>'
            "</a:avLst></a:prstGeom>"
        )
    elif radius_emu is not None:
        geometry_xml = (
            f'<a:prstGeom prst="{prst}"><a:avLst>'
            f'<a:gd name="rad" fmla="val {radius_emu}"/>'
            "</a:avLst></a:prstGeom>"
        )
    else:
        geometry_xml = f'<a:prstGeom prst="{prst}"><a:avLst/></a:prstGeom>'

    return geometry_xml, bounds, (width_emu, height_emu)


__all__ = [
    "GeometryPayload",
    "extract_url_id",
    "generate_clip_geometry",
    "resolve_clip_ref",
    "resolve_mask_ref",
]
