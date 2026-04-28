"""Resvg filter pipeline — plan promotion, surface seeding, and EMF turbulence."""

from __future__ import annotations

import copy
import struct
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from lxml import etree

from svg2ooxml.common.numpy_compat import require_numpy
from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.common.units import px_to_emu
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.planner import FilterPlanner
from svg2ooxml.filters.primitives.blend import BlendFilter
from svg2ooxml.filters.primitives.color_matrix import ColorMatrixFilter
from svg2ooxml.filters.primitives.component_transfer import ComponentTransferFilter
from svg2ooxml.filters.primitives.composite import CompositeFilter
from svg2ooxml.filters.primitives.convolve_matrix import ConvolveMatrixFilter
from svg2ooxml.filters.primitives.flood import FloodFilter
from svg2ooxml.filters.primitives.gaussian_blur import GaussianBlurFilter
from svg2ooxml.filters.primitives.lighting import (
    DiffuseLightingFilter,
    SpecularLightingFilter,
)
from svg2ooxml.filters.primitives.merge import MergeFilter
from svg2ooxml.filters.primitives.morphology import MorphologyFilter
from svg2ooxml.filters.primitives.offset import OffsetFilter
from svg2ooxml.filters.primitives.tile import TileFilter
from svg2ooxml.filters.resvg_bridge import ResolvedFilter
from svg2ooxml.filters.utils import parse_number
from svg2ooxml.io.emf.blob import EMFBlob
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.render.filters import FilterPlan
from svg2ooxml.render.rasterizer import Viewport
from svg2ooxml.render.surface import Surface
from svg2ooxml.services.filter_types import FilterEffectResult

np = require_numpy("Filter raster bridging requires NumPy; install the 'render' extra.")

_PROMOTION_FILTER_FACTORIES = {
    "feflood": FloodFilter,
    "feblend": BlendFilter,
    "fecomposite": CompositeFilter,
    "fecolormatrix": ColorMatrixFilter,
    "femorphology": MorphologyFilter,
    "fetile": TileFilter,
    "femerge": MergeFilter,
    "feoffset": OffsetFilter,
    "fecomponenttransfer": ComponentTransferFilter,
    "feconvolvematrix": ConvolveMatrixFilter,
    "fediffuselighting": DiffuseLightingFilter,
    "fespecularlighting": SpecularLightingFilter,
    "fegaussianblur": GaussianBlurFilter,
}


def promotion_filter(tag: str):  # noqa: ANN201
    """Instantiate a filter primitive promoter for *tag*, or ``None``."""
    factory = _PROMOTION_FILTER_FACTORIES.get(tag)
    if factory is None:
        return None
    return factory()


def seed_source_surface(width: int, height: int) -> Surface:
    """Create a synthetic RGBA source surface for resvg evaluation."""
    width = max(1, width)
    height = max(1, height)
    surface = Surface.make(width, height)
    xs = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    ys = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]

    red = 0.15 + 0.75 * xs
    green = 0.2 + 0.6 * (1.0 - ys)
    radial = np.sqrt((xs - 0.5) ** 2 + (ys - 0.5) ** 2)
    blue = np.clip(0.9 - 0.8 * radial, 0.1, 0.9)

    base_alpha = np.clip(0.6 + 0.4 * (1.0 - radial * 1.2), 0.25, 1.0)
    stripe = ((xs + ys) % 0.25) < 0.02
    base_alpha = np.where(stripe, np.minimum(base_alpha, 0.4), base_alpha)

    surface.data[..., 0] = red
    surface.data[..., 1] = green
    surface.data[..., 2] = blue
    surface.data[..., 3] = base_alpha
    surface.data[..., :3] *= surface.data[..., 3:4]
    return surface


def surface_to_bmp(surface: Surface) -> bytes:
    """Convert a float32 RGBA surface to a 24-bit BMP byte string."""
    data = np.clip(surface.data, 0.0, 1.0)
    rgb = data[..., :3]
    alpha = data[..., 3:4]
    safe_alpha = np.where(alpha > 1e-6, alpha, 1.0)
    unpremult = np.where(alpha > 1e-6, rgb / safe_alpha, 0.0)
    unpremult = np.clip(unpremult, 0.0, 1.0)
    bgr = (unpremult[..., ::-1] * 255.0 + 0.5).astype(np.uint8)
    height, width = bgr.shape[:2]
    row_stride = (width * 3 + 3) & ~3
    padding = row_stride - width * 3
    pad_bytes = b"\x00" * padding
    rows = []
    for y in range(height - 1, -1, -1):
        rows.append(bgr[y].tobytes() + pad_bytes)
    pixel_data = b"".join(rows)
    header_size = 40
    dib_header = struct.pack(
        "<IIIHHIIIIII",
        header_size,
        width,
        height,
        1,
        24,
        0,
        len(pixel_data),
        int(96 / 0.0254),
        int(96 / 0.0254),
        0,
        0,
    )
    file_header = b"BM" + struct.pack(
        "<IHHI",
        14 + len(dib_header) + len(pixel_data),
        0,
        0,
        14 + len(dib_header),
    )
    return file_header + dib_header + pixel_data


def turbulence_emf_effect(
    surface: Surface,
    viewport: Viewport,
    plan: FilterPlan,
    filter_id: str,
) -> FilterEffectResult:
    """Wrap a turbulence result surface into an EMF-backed effect."""
    width_px = max(1, int(round(viewport.width)))
    height_px = max(1, int(round(viewport.height)))
    bmp_bytes = surface_to_bmp(surface)
    width_emu = max(1, int(round(px_to_emu(width_px))))
    height_emu = max(1, int(round(px_to_emu(height_px))))
    blob = EMFBlob(width_emu=width_emu, height_emu=height_emu)
    blob.draw_bitmap(
        0,
        0,
        width_emu,
        height_emu,
        0,
        0,
        width_px,
        height_px,
        bmp_bytes,
    )
    emf_bytes = blob.finalize()
    metadata: dict[str, Any] = {
        "renderer": "resvg",
        "resvg_promotion": "emf",
        "promotion_source": "resvg",
        "promotion_primitives": [primitive.tag for primitive in plan.primitives],
        "fallback_assets": [
            {
                "type": "emf",
                "format": "emf",
                "data": emf_bytes,
                "width_px": width_px,
                "height_px": height_px,
            }
        ],
        "turbulence_emf": True,
        "filter_id": filter_id,
    }
    effect = CustomEffect(drawingml="")
    return FilterEffectResult(effect=effect, strategy="vector", metadata=metadata, fallback="emf")


def match_plan_elements(
    filter_element: etree._Element,
    plan: FilterPlan,
) -> list[etree._Element] | None:
    """Match plan primitives to actual lxml elements by tag / result-name."""
    buckets: dict[str, list[etree._Element]] = defaultdict(list)
    results: dict[str, etree._Element] = {}
    for child in filter_element:
        local = local_name(child.tag).lower()
        buckets[local].append(child)
        result_name = child.get("result")
        if result_name:
            token = result_name.strip()
            if token and token not in results:
                results[token] = child

    ordered: list[etree._Element] = []
    used: set[etree._Element] = set()
    for primitive in plan.primitives:
        local = primitive.tag.lower()
        candidate: etree._Element | None = None
        if primitive.result_name:
            candidate = results.get(primitive.result_name)
            if candidate in used:
                candidate = None
        if candidate is None:
            bucket = buckets.get(local)
            while bucket:
                contender = bucket.pop(0)
                if contender not in used:
                    candidate = contender
                    break
        if candidate is None:
            return None
        ordered.append(candidate)
        used.add(candidate)
    return ordered


def inject_promotion_metadata(
    metadata: dict[str, Any],
    plan: FilterPlan,
    viewport: Viewport,
    planner: FilterPlanner,
) -> None:
    """Populate *metadata* with plan/viewport info for a promoted result."""
    metadata.setdefault("width_px", viewport.width)
    metadata.setdefault("height_px", viewport.height)
    metadata.setdefault("promotion_plan_length", len(plan.primitives))
    plan_summary = []
    for primitive_plan in plan.primitives:
        entry = {
            "tag": primitive_plan.tag,
            "inputs": list(primitive_plan.inputs),
            "result": primitive_plan.result_name,
        }
        if primitive_plan.extra:
            entry["metadata"] = planner.serialise_plan_extra(primitive_plan.extra)
        plan_summary.append(entry)
    metadata.setdefault("plan_primitives", plan_summary)


def is_neutral_promotion(tag: str, element: etree._Element, result: FilterResult) -> bool:
    """Return ``True`` when the promoted result is a no-op identity."""
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    if metadata.get("no_op"):
        return True

    if tag == "fegaussianblur":
        std_x = metadata.get("std_deviation_x")
        std_y = metadata.get("std_deviation_y")
        try:
            std_x_val = float(std_x) if std_x is not None else 0.0
            std_y_val = float(std_y) if std_y is not None else 0.0
        except (TypeError, ValueError):
            std_x_val = 0.0
            std_y_val = 0.0
        return abs(std_x_val) <= 1e-6 and abs(std_y_val) <= 1e-6

    if tag == "feoffset":
        dx = metadata.get("dx")
        dy = metadata.get("dy")
        try:
            dx_val = float(dx) if dx is not None else 0.0
            dy_val = float(dy) if dy is not None else 0.0
        except (TypeError, ValueError):
            dx_val = 0.0
            dy_val = 0.0
        return abs(dx_val) <= 1e-6 and abs(dy_val) <= 1e-6

    if tag == "fecolormatrix":
        if metadata.get("reason") == "identity_matrix":
            return True
        matrix_type = str(metadata.get("matrix_type") or "matrix").strip().lower()
        if matrix_type != "matrix":
            return False
        values = metadata.get("values")
        if not values:
            return True
        try:
            return is_identity_matrix([float(v) for v in values])
        except (TypeError, ValueError):
            return False

    if tag == "fegaussianblur" and element is not None:
        std_attr = element.get("stdDeviation")
        if std_attr:
            parts = [parse_number(token) for token in std_attr.replace(",", " ").split()]
            if parts and all(abs(value) <= 1e-6 for value in parts[:2]):
                return True

    return False


def is_identity_matrix(values: list[float]) -> bool:
    """Check whether *values* is a 4x5 identity colour matrix."""
    if len(values) != 20:
        return False
    identity = [
        1.0, 0.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 1.0, 0.0,
    ]
    tol = 1e-6
    return all(abs(a - b) <= tol for a, b in zip(values, identity, strict=True))


def promote_resvg_plan(
    plan: FilterPlan,
    filter_element: etree._Element,
    context: FilterContext,
    viewport: Viewport,
    overrides: dict[str, dict[str, Any]] | None,
    descriptor: ResolvedFilter,
    planner: FilterPlanner,
    drawingml_renderer: Any,
    *,
    trace: Callable[..., None] | None = None,
) -> FilterEffectResult | None:
    """Attempt native promotion of a resvg plan; returns ``None`` on failure."""
    if not plan.primitives:
        return None

    policy = context.policy
    if policy.get("allow_promotion") is False:
        if trace is not None:
            trace("resvg_promotion_policy_blocked", reason="global_allow_promotion=false")
        return None

    matched_elements = match_plan_elements(filter_element, plan)
    if matched_elements is None:
        return None

    pipeline_state: dict[str, FilterResult] = {}
    if isinstance(context.pipeline_state, dict):
        pipeline_state.update(context.pipeline_state)
    original_pipeline = context.pipeline_state
    context.pipeline_state = pipeline_state

    lighting_candidates: list[str] = []
    lighting_primitives: list[str] = []
    try:
        stage_results: list[FilterResult] = []
        no_op_primitives: list[str] = []
        for primitive_plan, element in zip(plan.primitives, matched_elements, strict=True):
            tag = primitive_plan.tag.lower()
            entry_override = (overrides or {}).get(tag)
            promoter = promotion_filter(tag)
            if promoter is None:
                if trace is not None:
                    if tag in {"fediffuselighting", "fespecularlighting"}:
                        trace(
                            "resvg_lighting_candidate",
                            primitive=tag,
                            plan_extra=planner.serialise_plan_extra(primitive_plan.extra)
                            if primitive_plan.extra
                            else {},
                        )
                    else:
                        trace(
                            "resvg_promotion_missing_handler",
                            primitive=tag,
                        )
                if tag in {"fediffuselighting", "fespecularlighting"}:
                    lighting_candidates.append(tag)
                return None

            promoted_result = promoter.apply(copy.deepcopy(element), context)
            if trace is not None and tag in {"fediffuselighting", "fespecularlighting"}:
                trace(
                    "resvg_lighting_promoted",
                    primitive=tag,
                    plan_extra=planner.serialise_plan_extra(primitive_plan.extra)
                    if primitive_plan.extra
                    else {},
                )
                lighting_primitives.append(tag)
            elif tag in {"fediffuselighting", "fespecularlighting"}:
                lighting_primitives.append(tag)
            is_no_op = is_neutral_promotion(tag, element, promoted_result)
            if is_no_op:
                no_op_primitives.append(tag)
                if trace is not None:
                    trace("resvg_promotion_noop", primitive=tag)
                if primitive_plan.result_name:
                    input_name = next((name for name in primitive_plan.inputs if name), None)
                    source = pipeline_state.get(input_name) if input_name else None
                    if source is None and input_name in {"SourceGraphic", "SourceAlpha"}:
                        source = pipeline_state.get(input_name)
                    pipeline_state[primitive_plan.result_name] = source or promoted_result
                continue

            if entry_override and entry_override.get("allow_promotion") is False:
                if trace is not None:
                    trace(
                        "resvg_promotion_policy_blocked",
                        primitive=tag,
                        reason="allow_promotion=false",
                    )
                return None

            violation = None
            if entry_override:
                violation = planner.promotion_policy_violation(tag, promoted_result, entry_override)
                if violation is not None and trace is not None:
                    trace(
                        "resvg_promotion_policy_blocked",
                        primitive=tag,
                        **violation,
                    )
            if violation is not None:
                return None

            if primitive_plan.result_name:
                pipeline_state[primitive_plan.result_name] = promoted_result
            stage_results.append(promoted_result)

        if not stage_results:
            if no_op_primitives:
                metadata: dict[str, Any] = {
                    "renderer": "resvg",
                    "resvg_promotion": "native",
                    "promotion_source": "resvg",
                    "promotion_primitives": [primitive.tag for primitive in plan.primitives],
                    "no_op": True,
                    "no_op_primitives": list(no_op_primitives),
                    "descriptor": planner.serialize_descriptor(descriptor),
                    "primitives": [primitive.tag for primitive in descriptor.primitives],
                    "filter_units": descriptor.filter_units,
                    "primitive_units": descriptor.primitive_units,
                }
                if descriptor.filter_id:
                    metadata["filter_id"] = descriptor.filter_id
                inject_promotion_metadata(metadata, plan, viewport, planner)
                effect = CustomEffect(drawingml="")
                return FilterEffectResult(
                    effect=effect,
                    strategy="native",
                    metadata=metadata,
                    fallback=None,
                )
            return None

        final_result = stage_results[-1]
        if final_result.fallback not in {"emf", "vector", None}:
            return None
        if final_result.fallback is None:
            drawingml_payload = final_result.drawingml or ""
            if not drawingml_payload.strip():
                return None

        rendered = drawingml_renderer.render([final_result], context=context)
        if not rendered:
            return None

        effect = rendered[0]
        metadata = dict(effect.metadata or {})
        assets = metadata.get("fallback_assets")
        if isinstance(assets, list):
            metadata["fallback_assets"] = list(assets)
        inject_promotion_metadata(metadata, plan, viewport, planner)
        metadata.setdefault("renderer", "resvg")
        metadata.setdefault("resvg_promotion", final_result.fallback or "vector")
        metadata.setdefault("promotion_source", "resvg")
        metadata.setdefault("promotion_primitives", [primitive.tag for primitive in plan.primitives])
        metadata.setdefault("descriptor", planner.serialize_descriptor(descriptor))
        metadata.setdefault("primitives", [primitive.tag for primitive in descriptor.primitives])
        if lighting_candidates:
            metadata.setdefault("resvg_lighting_candidate", lighting_candidates)
        if lighting_primitives:
            metadata.setdefault("lighting_primitives", lighting_primitives)
        if descriptor.filter_id:
            metadata.setdefault("filter_id", descriptor.filter_id)
        metadata.setdefault("filter_units", descriptor.filter_units)
        metadata.setdefault("primitive_units", descriptor.primitive_units)
        return FilterEffectResult(
            effect=effect.effect,
            strategy=effect.strategy,
            metadata=metadata,
            fallback=effect.fallback,
        )
    finally:
        context.pipeline_state = original_pipeline
