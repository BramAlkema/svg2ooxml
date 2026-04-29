"""Fallback asset materialization helpers for DrawingML filter rendering."""

from __future__ import annotations

import math

from lxml import etree

from svg2ooxml.common.boundaries import is_safe_relationship_id
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import FilterResult
from svg2ooxml.filters.metadata import (
    FilterFallbackAssetPayload,
    coerce_fallback_asset,
    fallback_asset_data_hex,
)

_ALLOWED_BLIP_TAGS = frozenset(
    {
        "alphaModFix",
        "alphaMod",
        "alphaOff",
        "satMod",
        "satOff",
        "hueOff",
        "lumMod",
        "lumOff",
        "tint",
        "shade",
    }
)
_RESERVED_SLIDE_RELATIONSHIP_IDS = {"rId1"}


class FilterRendererAssetMixin:
    """Build fallback EMF/raster effect fragments and metadata assets."""

    def _placeholder_emf(
        self,
        metadata: dict[str, object],
        result: FilterResult,
        *,
        policy: dict[str, object] | None,
    ) -> str:
        try:
            asset = self._ensure_emf_asset(metadata, result)
        except Exception:  # pragma: no cover - defensive fallback
            self._logger.debug(
                "EMF adapter failed; falling back to placeholder", exc_info=True
            )
            asset = None

        if not asset:
            return self._placeholder_emf_reuse(metadata, policy)

        rel_id = asset.get("relationship_id")
        if not is_safe_relationship_id(
            rel_id,
            reserved_ids=_RESERVED_SLIDE_RELATIONSHIP_IDS,
        ):
            rel_id = self._allocate_reuse_id("rIdEmfReuse")
            asset["relationship_id"] = rel_id
        assert isinstance(rel_id, str)

        width_emu = self._coerce_int(asset.get("width_emu"))
        height_emu = self._coerce_int(asset.get("height_emu"))
        data_hex = self._asset_data_hex(asset)

        comment_parts = [f'relationship="{rel_id}"']
        if width_emu is not None:
            comment_parts.append(f'width="{width_emu}"')
        if height_emu is not None:
            comment_parts.append(f'height="{height_emu}"')
        comment = " ".join(comment_parts)

        effectLst = a_elem("effectLst")
        effectLst.append(
            etree.Comment(self._safe_comment_text(f"svg2ooxml:emf {comment}"))
        )
        blip = self._append_blip_fill(effectLst, rel_id)
        self._apply_blip_enrichment(blip, metadata, policy)

        if data_hex:
            extLst = a_sub(blip, "extLst")
            ext = a_sub(extLst, "ext", uri="{28A0092B-C50C-407E-A947-70E740481C1C}")
            ext.text = data_hex

        return to_string(effectLst)

    def _placeholder_emf_reuse(
        self,
        metadata: dict[str, object],
        policy: dict[str, object] | None,
    ) -> str:
        assets = self._prune_unpackageable_assets(metadata, "emf")
        placeholder_id = self._allocate_reuse_id("rIdEmfReuse")
        assets.append(
            {
                "type": "emf",
                "relationship_id": placeholder_id,
                "placeholder": True,
            }
        )
        effectLst = a_elem("effectLst")
        effectLst.append(
            etree.Comment(
                self._safe_comment_text(
                    f'svg2ooxml:emf placeholder="" relationship="{placeholder_id}"'
                )
            )
        )
        blip = self._append_blip_fill(effectLst, placeholder_id)
        self._apply_blip_enrichment(blip, metadata, policy)
        return to_string(effectLst)

    def _placeholder_raster(
        self,
        metadata: dict[str, object],
        result: FilterResult,
        *,
        policy: dict[str, object] | None,
    ) -> str:
        existing_asset = self._existing_raster_asset(metadata)
        if existing_asset is not None:
            return self._render_existing_raster_asset(existing_asset, metadata, policy)
        return self._render_generated_raster_placeholder(metadata, policy)

    def _existing_raster_asset(
        self,
        metadata: dict[str, object],
    ) -> FilterFallbackAssetPayload | None:
        assets_list = metadata.get("fallback_assets")
        if isinstance(assets_list, list):
            for asset in assets_list:
                typed_asset = coerce_fallback_asset(
                    asset,
                    asset_type="raster",
                    copy=False,
                )
                if (
                    typed_asset is not None
                    and self._asset_data_hex(typed_asset) is not None
                ):
                    return typed_asset
        return None

    def _render_existing_raster_asset(
        self,
        asset: FilterFallbackAssetPayload,
        metadata: dict[str, object],
        policy: dict[str, object] | None,
    ) -> str:
        rel_id = asset.get("relationship_id")
        if not is_safe_relationship_id(
            rel_id,
            reserved_ids=_RESERVED_SLIDE_RELATIONSHIP_IDS,
        ):
            rel_id = self._allocate_reuse_id("rIdRasterReuse")
            asset["relationship_id"] = rel_id
        assert isinstance(rel_id, str)
        width_px = self._coerce_int(asset.get("width_px"))
        height_px = self._coerce_int(asset.get("height_px"))
        data_hex = self._asset_data_hex(asset)

        effectLst = a_elem("effectLst")
        comment_parts = [f'relationship="{rel_id}"']
        if width_px is not None:
            comment_parts.append(f'width="{width_px}"')
        if height_px is not None:
            comment_parts.append(f'height="{height_px}"')
        comment = " ".join(comment_parts)
        effectLst.append(
            etree.Comment(self._safe_comment_text(f"svg2ooxml:raster {comment}"))
        )
        blip = self._append_blip_fill(effectLst, rel_id)
        self._apply_blip_enrichment(blip, metadata, policy)

        if data_hex:
            extLst = a_sub(blip, "extLst")
            ext = a_sub(extLst, "ext", uri="{svg2ooxml:raster}")
            ext.text = data_hex

        return to_string(effectLst)

    def _render_generated_raster_placeholder(
        self,
        metadata: dict[str, object],
        policy: dict[str, object] | None,
    ) -> str:
        placeholder_meta: dict[str, object] = {}
        for key in ("policy", "radius_effective", "alpha", "color", "radius_max"):
            if key in metadata:
                placeholder_meta[key] = metadata[key]

        raster = self._raster_adapter.generate_placeholder(metadata=placeholder_meta)
        assets = self._prune_unpackageable_assets(metadata, "raster")
        assets.append(
            {
                "type": "raster",
                "relationship_id": raster.relationship_id,
                "width_px": raster.width_px,
                "height_px": raster.height_px,
                "metadata": raster.metadata,
                "data_hex": raster.image_bytes.hex(),
            }
        )

        effectLst = a_elem("effectLst")
        comment_text = (
            f' svg2ooxml:raster relationship="{raster.relationship_id}" '
            f'size="{len(raster.image_bytes)}" '
        )
        effectLst.append(etree.Comment(self._safe_comment_text(comment_text)))
        blip = self._append_blip_fill(effectLst, raster.relationship_id)
        self._apply_blip_enrichment(blip, metadata, policy)

        extLst = a_sub(blip, "extLst")
        ext = a_sub(extLst, "ext", uri="{svg2ooxml:raster}")
        ext.text = raster.image_bytes.hex()

        return to_string(effectLst)

    @staticmethod
    def _append_blip_fill(effectLst, relationship_id: str):
        blipFill = a_sub(effectLst, "blipFill", rotWithShape="0")
        blip = a_sub(blipFill, "blip")
        blip.set(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed",
            relationship_id,
        )
        return blip

    def _ensure_emf_asset(
        self,
        metadata: dict[str, object],
        result: FilterResult,
    ) -> FilterFallbackAssetPayload | None:
        asset = self._active_emf_asset(metadata)
        if asset is not None:
            return asset

        filter_type = self._filter_type(metadata, result)
        try:
            source_meta = (
                result.metadata if isinstance(result.metadata, dict) else metadata
            )
            if isinstance(source_meta, dict):
                source_meta = dict(source_meta)
            else:
                source_meta = metadata if isinstance(metadata, dict) else {}
            emf = self._emf_adapter.render_filter(filter_type, source_meta)
        except Exception:
            self._logger.debug(
                "Failed to render EMF for filter %s", filter_type, exc_info=True
            )
            return None

        asset: FilterFallbackAssetPayload = {
            "type": "emf",
            "relationship_id": emf.relationship_id,
            "width_emu": emf.width_emu,
            "height_emu": emf.height_emu,
            "metadata": emf.metadata,
            "data_hex": emf.emf_bytes.hex(),
        }
        self._prune_unpackageable_assets(metadata, "emf").append(asset)
        emf_meta = metadata.setdefault("emf_asset", {})
        if isinstance(emf_meta, dict):
            emf_meta.setdefault("width_emu", emf.width_emu)
            emf_meta.setdefault("height_emu", emf.height_emu)
            emf_meta.setdefault(
                "filter_type", emf.metadata.get("filter_type", filter_type)
            )
        return asset

    def _active_emf_asset(
        self,
        metadata: dict[str, object],
    ) -> FilterFallbackAssetPayload | None:
        assets_list = metadata.get("fallback_assets")
        if isinstance(assets_list, list):
            for asset in assets_list:
                typed_asset = coerce_fallback_asset(
                    asset,
                    asset_type="emf",
                    copy=False,
                )
                if (
                    typed_asset is not None
                    and self._asset_data_hex(typed_asset) is not None
                ):
                    return typed_asset
        return None

    @staticmethod
    def _metadata_copy(metadata: dict[str, object] | None) -> dict[str, object]:
        copied = dict(metadata or {})
        assets = copied.get("fallback_assets")
        if isinstance(assets, list):
            copied["fallback_assets"] = [
                dict(asset) if isinstance(asset, dict) else asset for asset in assets
            ]
        return copied

    @staticmethod
    def _ensure_asset_list(
        metadata: dict[str, object],
    ) -> list[FilterFallbackAssetPayload]:
        assets = metadata.get("fallback_assets")
        if not isinstance(assets, list):
            assets = []
            metadata["fallback_assets"] = assets
        return assets

    @classmethod
    def _prune_unpackageable_assets(
        cls,
        metadata: dict[str, object],
        asset_type: str,
    ) -> list[FilterFallbackAssetPayload]:
        pruned: list[FilterFallbackAssetPayload] = []
        assets = metadata.get("fallback_assets")
        if isinstance(assets, list):
            for asset in assets:
                copied = coerce_fallback_asset(asset)
                if copied is None:
                    continue
                if (
                    copied.get("type") == asset_type
                    and cls._asset_data_hex(copied) is None
                ):
                    continue
                pruned.append(copied)
        metadata["fallback_assets"] = pruned
        return pruned

    @staticmethod
    def _asset_data_hex(asset: FilterFallbackAssetPayload) -> str | None:
        return fallback_asset_data_hex(asset)

    @staticmethod
    def _coerce_int(value: object) -> int | None:
        try:
            parsed = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if not math.isfinite(parsed):
            return None
        return int(parsed)

    @staticmethod
    def _safe_comment_text(value: str) -> str:
        text = value.replace("--", "- -")
        if text.endswith("-"):
            text += " "
        return text

    @classmethod
    def _comment_xml(cls, value: str) -> str:
        return f"<!-- {cls._safe_comment_text(value)} -->"

    def _filter_type(self, metadata: dict[str, object], result: FilterResult) -> str:
        if isinstance(metadata, dict):
            token = metadata.get("filter_type")
            if isinstance(token, str) and token:
                return token
        meta = result.metadata if isinstance(result.metadata, dict) else {}
        token = meta.get("filter_type") if isinstance(meta, dict) else None
        if isinstance(token, str) and token:
            return token
        return "generic"

    def _allocate_reuse_id(self, prefix: str) -> str:
        self._reuse_counter += 1
        return f"{prefix}{self._reuse_counter}"

    def _apply_blip_enrichment(
        self,
        blip,
        metadata: dict[str, object],
        policy: dict[str, object] | None,
    ) -> None:
        if not isinstance(policy, dict):
            return
        if not bool(policy.get("enable_blip_effect_enrichment", False)):
            return
        candidates = metadata.get("blip_color_transforms")
        if not isinstance(candidates, list):
            return

        applied = False
        for candidate in candidates:
            if self._apply_blip_enrichment_candidate(blip, candidate):
                applied = True
        if applied:
            metadata["blip_effect_enrichment_applied"] = True

    def _apply_blip_enrichment_candidate(self, blip, candidate: object) -> bool:
        if not isinstance(candidate, dict):
            return False
        tag = candidate.get("tag")
        if not isinstance(tag, str) or tag not in _ALLOWED_BLIP_TAGS:
            return False
        attrs: dict[str, str] = {}
        for attr_name in ("val", "amt"):
            if attr_name not in candidate:
                continue
            raw = candidate[attr_name]
            if isinstance(raw, (int, float)):
                attrs[attr_name] = str(int(round(raw)))
            elif isinstance(raw, str) and raw.strip():
                attrs[attr_name] = raw.strip()
        if not attrs:
            return False
        a_sub(blip, tag, **attrs)
        return True


__all__ = ["FilterRendererAssetMixin"]
