"""Helpers for filter fallback asset placement and registration."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from svg2ooxml.common.units.lengths import resolve_length_px
from svg2ooxml.drawingml.image import render_picture
from svg2ooxml.filters.metadata import (
    FilterFallbackAssetPayload,
    coerce_fallback_asset,
    fallback_asset_bytes,
)
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.scene import Image


@dataclass(frozen=True)
class FilterFallbackAsset:
    """Resolved filter fallback asset candidate from element metadata."""

    filter_id: str
    fallback: str
    asset_type: str
    asset: FilterFallbackAssetPayload
    metadata: Mapping[str, Any] | None


def resolve_filter_fallback_bounds(
    default_bounds: Rect | None,
    metadata: Mapping[str, object] | None,
) -> Rect | None:
    """Return fallback bounds overridden by filter metadata when available."""

    if not isinstance(metadata, Mapping):
        return default_bounds

    bounds_dict = metadata.get("bounds")
    if not isinstance(bounds_dict, Mapping):
        return default_bounds

    base_x = default_bounds.x if default_bounds is not None else 0.0
    base_y = default_bounds.y if default_bounds is not None else 0.0
    base_width = default_bounds.width if default_bounds is not None else 0.0
    base_height = default_bounds.height if default_bounds is not None else 0.0

    x = _metadata_length_px(bounds_dict, "x", axis="x", default=base_x)
    y = _metadata_length_px(bounds_dict, "y", axis="y", default=base_y)
    width = _metadata_length_px(bounds_dict, "width", axis="x", default=base_width)
    height = _metadata_length_px(bounds_dict, "height", axis="y", default=base_height)
    if not all(math.isfinite(value) for value in (x, y, width, height)):
        return default_bounds
    return Rect(x, y, width, height)


def _metadata_length_px(
    metadata: Mapping[str, object],
    key: str,
    *,
    axis: str,
    default: float,
) -> float:
    if key not in metadata:
        return default
    return resolve_length_px(metadata.get(key), None, axis=axis, default=math.nan)


def iter_filter_fallback_assets(
    metadata: Mapping[str, object] | None,
    *,
    infer_vector_fallback_from_metadata: bool = False,
) -> Iterator[FilterFallbackAsset]:
    """Yield filter fallback assets described by shape/group metadata."""
    if not isinstance(metadata, Mapping):
        return
    filters = metadata.get("filters")
    if not isinstance(filters, list) or not filters:
        return
    policy = metadata.get("policy")
    if not isinstance(policy, Mapping):
        return
    media_policy = policy.get("media")
    if not isinstance(media_policy, Mapping):
        return
    filter_assets = media_policy.get("filter_assets")
    if not isinstance(filter_assets, Mapping):
        return

    filter_meta = metadata.get("filter_metadata")
    if not isinstance(filter_meta, Mapping):
        filter_meta = {}

    for entry in filters:
        if not isinstance(entry, Mapping):
            continue
        filter_id = entry.get("id")
        if not isinstance(filter_id, str) or not filter_id:
            continue
        fallback = entry.get("fallback")
        fallback = fallback.lower() if isinstance(fallback, str) else None
        meta = filter_meta.get(filter_id)
        if (
            fallback is None
            and infer_vector_fallback_from_metadata
            and isinstance(meta, Mapping)
        ):
            filter_type = meta.get("filter_type")
            if isinstance(filter_type, str) and filter_type.lower() in {
                "composite",
                "flood",
            }:
                fallback = "emf"
        if fallback not in {"emf", "vector", "bitmap", "raster"}:
            continue
        assets = filter_assets.get(filter_id)
        if not isinstance(assets, list):
            continue
        asset_type = "emf" if fallback in {"emf", "vector"} else "raster"
        for asset in assets:
            typed_asset = coerce_fallback_asset(
                asset,
                asset_type=asset_type,
                copy=False,
            )
            if typed_asset is None:
                continue
            yield FilterFallbackAsset(
                filter_id=filter_id,
                fallback=fallback,
                asset_type=asset_type,
                asset=typed_asset,
                metadata=meta if isinstance(meta, Mapping) else None,
            )


def render_shape_filter_fallback(
    element,
    shape_id: int,
    metadata: Mapping[str, object],
    *,
    picture_template: str,
    policy_for: Callable[[dict[str, object] | None, str], dict[str, object]],
    register_media: Callable[[Image], str],
    trace_writer: Callable[..., None],
    hyperlink_xml: str,
) -> tuple[str, int] | None:
    """Render a shape-level filter fallback asset as a picture."""
    for candidate in iter_filter_fallback_assets(
        metadata,
        infer_vector_fallback_from_metadata=True,
    ):
        asset = candidate.asset
        image_bytes = fallback_asset_bytes(asset)
        if image_bytes is None:
            continue

        bounds = resolve_filter_fallback_bounds(
            getattr(element, "bbox", None),
            candidate.metadata,
        )
        if bounds is None or bounds.width <= 0 or bounds.height <= 0:
            continue

        image_metadata: dict[str, object] = {
            "image_source": "filter_fallback",
            "filter_id": candidate.filter_id,
            "fallback": candidate.fallback,
        }
        for source in (
            candidate.metadata,
            asset,
            (
                asset.get("metadata")
                if isinstance(asset.get("metadata"), Mapping)
                else None
            ),
        ):
            if not isinstance(source, Mapping):
                continue
            blip_color_transforms = source.get("blip_color_transforms")
            if isinstance(blip_color_transforms, list) and blip_color_transforms:
                image_metadata["blip_color_transforms"] = list(blip_color_transforms)
                break
        for source in (
            candidate.metadata,
            asset,
            (
                asset.get("metadata")
                if isinstance(asset.get("metadata"), Mapping)
                else None
            ),
        ):
            if isinstance(source, Mapping) and bool(source.get("flatten_for_powerpoint")):
                image_metadata["flatten_for_powerpoint"] = True
                break
        if candidate.asset_type == "emf":
            image_metadata["emf_asset"] = {
                "relationship_id": asset.get("relationship_id"),
                "width_emu": asset.get("width_emu"),
                "height_emu": asset.get("height_emu"),
            }
        image = Image(
            origin=Point(bounds.x, bounds.y),
            size=Rect(0.0, 0.0, bounds.width, bounds.height),
            data=image_bytes,
            format="emf" if candidate.asset_type == "emf" else "png",
            metadata=image_metadata,
        )
        xml = render_picture(
            image,
            shape_id,
            template=picture_template,
            policy_for=policy_for,
            register_media=register_media,
            hyperlink_xml=hyperlink_xml,
        )
        if xml is None:
            return None
        trace_writer(
            "filter_fallback_rendered",
            stage="filter",
            metadata={
                "shape_id": shape_id,
                "filter_id": candidate.filter_id,
                "fallback": candidate.fallback,
                "format": image.format,
            },
        )
        return xml, shape_id + 1
    return None


__all__ = [
    "FilterFallbackAsset",
    "iter_filter_fallback_assets",
    "render_shape_filter_fallback",
    "resolve_filter_fallback_bounds",
]
