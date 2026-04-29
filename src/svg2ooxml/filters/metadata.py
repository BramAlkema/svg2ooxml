"""Typed metadata helpers for filter fallback assets."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any, TypedDict, cast


class FilterFallbackAssetPayload(TypedDict, total=False):
    """Known fields for EMF/raster fallback assets carried in filter metadata."""

    type: str
    relationship_id: str
    width_px: int
    height_px: int
    width_emu: int
    height_emu: int
    metadata: Mapping[str, Any]
    data_hex: str
    data: bytes | bytearray
    placeholder: bool


def coerce_fallback_asset(
    value: Any,
    *,
    asset_type: str | None = None,
    copy: bool = True,
) -> FilterFallbackAssetPayload | None:
    """Return a typed fallback asset payload when *value* has a valid shape."""

    if not isinstance(value, Mapping):
        return None
    raw_type = value.get("type")
    if not isinstance(raw_type, str) or not raw_type:
        return None
    if asset_type is not None and raw_type != asset_type:
        return None
    if not copy and isinstance(value, dict):
        return cast(FilterFallbackAssetPayload, value)
    return cast(
        FilterFallbackAssetPayload,
        {key: item for key, item in value.items() if isinstance(key, str)},
    )


def fallback_asset_data_hex(
    asset: MutableMapping[str, object],
) -> str | None:
    """Return normalized hex payload for a fallback asset, if available."""

    data_hex = asset.get("data_hex")
    if isinstance(data_hex, str) and data_hex.strip():
        token = data_hex.strip()
        try:
            bytes.fromhex(token)
        except ValueError:
            asset.pop("data_hex", None)
        else:
            asset["data_hex"] = token
            return token

    raw = asset.get("data")
    if isinstance(raw, (bytes, bytearray)):
        token = bytes(raw).hex()
        asset["data_hex"] = token
        return token
    return None


def fallback_asset_bytes(asset: MutableMapping[str, object]) -> bytes | None:
    """Return fallback asset bytes from normalized hex or raw bytes metadata."""

    data_hex = fallback_asset_data_hex(asset)
    if data_hex is not None:
        return bytes.fromhex(data_hex)
    return None


def collect_fallback_asset_payloads(
    metadata: Mapping[str, Any] | None,
    *,
    asset_type: str | None = None,
    require_data: bool = False,
) -> list[FilterFallbackAssetPayload]:
    """Collect validated fallback asset payloads from a metadata mapping."""

    if not isinstance(metadata, Mapping):
        return []
    raw_assets = metadata.get("fallback_assets")
    if not isinstance(raw_assets, list):
        return []

    assets: list[FilterFallbackAssetPayload] = []
    for raw_asset in raw_assets:
        asset = coerce_fallback_asset(raw_asset, asset_type=asset_type)
        if asset is None:
            continue
        if require_data and fallback_asset_data_hex(asset) is None:
            continue
        assets.append(asset)
    return assets


__all__ = [
    "FilterFallbackAssetPayload",
    "coerce_fallback_asset",
    "collect_fallback_asset_payloads",
    "fallback_asset_bytes",
    "fallback_asset_data_hex",
]
