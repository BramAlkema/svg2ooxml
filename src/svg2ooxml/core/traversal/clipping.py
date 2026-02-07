"""Clip and mask helpers for the IR converter."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping

from lxml import etree

from svg2ooxml.clipmask.types import ClipDefinition, MaskInfo
from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.drawingml.generator import DrawingMLPathGenerator, px_to_emu
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
) -> ClipRef | None:
    clip_attr = element.get("clip-path")
    clip_id = extract_url_id(clip_attr) if clip_attr else None
    if not clip_id:
        return None

    definition = clip_definitions.get(clip_id)
    if definition is None:
        return ClipRef(clip_id=clip_id, strategy=ClipStrategy.NATIVE)

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
    )


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
    if not token:
        return None
    token = token.strip()
    if token.startswith("url(") and token.endswith(")"):
        inner = token[4:-1].strip().strip("\"'")
    else:
        inner = token
    if inner.startswith("#"):
        return inner[1:]
    return None


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
        rx = float(rx_value) if rx_value is not None else 0.0
        ry = float(ry_value) if ry_value is not None else 0.0
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
