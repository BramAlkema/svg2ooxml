"""Mask asset deduplication store for DrawingML output."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

MaskKind = Literal["vector", "raster", "emf"]


def _normalize_xml(xml: str | None) -> str:
    if not xml:
        return ""
    # Collapse whitespace to normalise mask geometry serialisation.
    return " ".join(xml.split())


def _hash_bytes(payload: bytes | bytearray | memoryview | None) -> str:
    if payload is None:
        return ""
    data = bytes(payload)
    return hashlib.sha256(data).hexdigest()


def _hash_string(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class MaskAsset:
    """Registered mask asset entry."""

    asset_id: str
    relationship_id: str
    part_name: str
    content_type: str
    kind: MaskKind
    mode: str
    key: str
    geometry_hash: str | None = None
    data_hash: str | None = None
    data: bytes | None = None
    sources: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    bounds_px: tuple[float, float, float, float] | None = None
    target_bounds: tuple[float, float, float, float] | None = None

    def add_source(self, source_id: str | None) -> None:
        if source_id:
            self.sources.add(source_id)

    def clone(self) -> MaskAsset:
        return MaskAsset(
            asset_id=self.asset_id,
            relationship_id=self.relationship_id,
            part_name=self.part_name,
            content_type=self.content_type,
            kind=self.kind,
            mode=self.mode,
            key=self.key,
            geometry_hash=self.geometry_hash,
            data_hash=self.data_hash,
            data=bytes(self.data) if self.data is not None else None,
            sources=set(self.sources),
            metadata=dict(self.metadata),
            bounds_px=self.bounds_px,
            target_bounds=self.target_bounds,
        )


@dataclass(frozen=True)
class MaskAssetHandle:
    """Lightweight reference returned to callers when registering a mask."""

    asset_id: str
    relationship_id: str
    part_name: str
    content_type: str
    kind: MaskKind
    mode: str


class MaskAssetStore:
    """Deduplicate and track mask assets for DrawingML output."""

    VECTOR_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.drawingml.mask+xml"

    def __init__(
        self,
        *,
        mask_directory: str = "/ppt/masks",
        relationship_prefix: str = "rIdMask",
    ) -> None:
        self._mask_directory = mask_directory.rstrip("/") or "/ppt/masks"
        self._relationship_prefix = relationship_prefix
        self._next_index = 1
        self._entries: list[MaskAsset] = []
        self._key_index: dict[str, MaskAsset] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def register_vector_mask(
        self,
        *,
        mask_id: str | None,
        geometry_xml: str | None,
        mode: str,
        mask_units: str | None = None,
        mask_content_units: str | None = None,
        bounds_px: tuple[float, float, float, float] | None = None,
        target_bounds: tuple[float, float, float, float] | None = None,
        metadata: Mapping[str, Any] | None = None,
        data: bytes | None = None,
    ) -> MaskAssetHandle:
        """Register a vector mask definition."""

        geometry_xml = geometry_xml or ""
        normalized_xml = _normalize_xml(geometry_xml)
        xml_hash = _hash_string(normalized_xml)
        key = self._vector_key(normalized_xml, mode, mask_units, mask_content_units)
        entry = self._key_index.get(key)
        if entry is not None:
            entry.add_source(mask_id)
            handle = MaskAssetHandle(
                asset_id=entry.asset_id,
                relationship_id=entry.relationship_id,
                part_name=entry.part_name,
                content_type=entry.content_type,
                kind=entry.kind,
                mode=entry.mode,
            )
            return handle

        relationship_id, part_name = self._allocate_part(kind="vector")
        metadata_dict = dict(metadata or {})
        entry = MaskAsset(
            asset_id=self._asset_identifier(),
            relationship_id=relationship_id,
            part_name=part_name,
            content_type=self.VECTOR_CONTENT_TYPE,
            kind="vector",
            mode=mode,
            key=key,
            geometry_hash=xml_hash,
            data_hash=_hash_bytes(data),
            data=bytes(data) if data is not None else None,
            metadata=metadata_dict,
            bounds_px=bounds_px,
            target_bounds=target_bounds,
        )
        entry.add_source(mask_id)
        self._record_entry(entry)
        return MaskAssetHandle(
            asset_id=entry.asset_id,
            relationship_id=entry.relationship_id,
            part_name=entry.part_name,
            content_type=entry.content_type,
            kind=entry.kind,
            mode=entry.mode,
        )

    def register_raster_mask(
        self,
        *,
        mask_id: str | None,
        image_bytes: bytes,
        mode: str,
        image_format: str = "png",
        bounds_px: tuple[float, float, float, float] | None = None,
        target_bounds: tuple[float, float, float, float] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MaskAssetHandle:
        """Register a raster mask fallback."""

        data_hash = _hash_bytes(image_bytes)
        key = self._raster_key(data_hash, mode, image_format)
        entry = self._key_index.get(key)
        if entry is not None:
            entry.add_source(mask_id)
            handle = MaskAssetHandle(
                asset_id=entry.asset_id,
                relationship_id=entry.relationship_id,
                part_name=entry.part_name,
                content_type=entry.content_type,
                kind=entry.kind,
                mode=entry.mode,
            )
            return handle

        relationship_id, part_name = self._allocate_part(kind="raster", suffix=f".{image_format.lower() or 'png'}")
        metadata_dict = dict(metadata or {})
        entry = MaskAsset(
            asset_id=self._asset_identifier(),
            relationship_id=relationship_id,
            part_name=part_name,
            content_type=_content_type_from_format(image_format),
            kind="raster",
            mode=mode,
            key=key,
            geometry_hash=None,
            data_hash=data_hash,
            data=bytes(image_bytes),
            metadata=metadata_dict,
            bounds_px=bounds_px,
            target_bounds=target_bounds,
        )
        entry.add_source(mask_id)
        self._record_entry(entry)
        return MaskAssetHandle(
            asset_id=entry.asset_id,
            relationship_id=entry.relationship_id,
            part_name=entry.part_name,
            content_type=entry.content_type,
            kind=entry.kind,
            mode=entry.mode,
        )

    def register_emf_mask(
        self,
        *,
        mask_id: str | None,
        emf_bytes: bytes,
        mode: str,
        bounds_px: tuple[float, float, float, float] | None = None,
        target_bounds: tuple[float, float, float, float] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MaskAssetHandle:
        data_hash = _hash_bytes(emf_bytes)
        key = self._raster_key(data_hash, mode, "emf")
        entry = self._key_index.get(key)
        if entry is not None:
            entry.add_source(mask_id)
            return MaskAssetHandle(
                asset_id=entry.asset_id,
                relationship_id=entry.relationship_id,
                part_name=entry.part_name,
                content_type=entry.content_type,
                kind=entry.kind,
                mode=entry.mode,
            )

        relationship_id, part_name = self._allocate_part(kind="emf", suffix=".emf")
        metadata_dict = dict(metadata or {})
        entry = MaskAsset(
            asset_id=self._asset_identifier(),
            relationship_id=relationship_id,
            part_name=part_name,
            content_type="image/x-emf",
            kind="emf",
            mode=mode,
            key=key,
            geometry_hash=None,
            data_hash=data_hash,
            data=bytes(emf_bytes),
            metadata=metadata_dict,
            bounds_px=bounds_px,
            target_bounds=target_bounds,
        )
        entry.add_source(mask_id)
        self._record_entry(entry)
        return MaskAssetHandle(
            asset_id=entry.asset_id,
            relationship_id=entry.relationship_id,
            part_name=entry.part_name,
            content_type=entry.content_type,
            kind=entry.kind,
            mode=entry.mode,
        )

    def iter_assets(self) -> Iterable[MaskAsset]:
        """Iterate registered assets."""
        return iter(self._entries)

    def snapshot(self) -> Sequence[MaskAsset]:
        """Return an immutable view of the registered assets."""
        return tuple(entry.clone() for entry in self._entries)

    def clear(self) -> None:
        """Reset the store."""
        self._entries.clear()
        self._key_index.clear()
        self._next_index = 1

    def clone(self) -> MaskAssetStore:
        """Return a deep-cloned store."""
        cloned = MaskAssetStore(
            mask_directory=self._mask_directory,
            relationship_prefix=self._relationship_prefix,
        )
        cloned._next_index = self._next_index
        for entry in self._entries:
            cloned_entry = entry.clone()
            cloned._entries.append(cloned_entry)
            cloned._key_index[cloned_entry.key] = cloned_entry
        return cloned

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _record_entry(self, entry: MaskAsset) -> None:
        self._entries.append(entry)
        self._key_index[entry.key] = entry

    def _allocate_part(self, *, kind: MaskKind, suffix: str | None = None) -> tuple[str, str]:
        index = self._next_sequence()
        relationship_id = f"{self._relationship_prefix}{index}"
        if kind == "vector":
            filename = f"mask{index}.xml"
        elif kind == "raster":
            extension = suffix or ".png"
            if not extension.startswith("."):
                extension = f".{extension}"
            filename = f"mask_bitmap{index}{extension}"
        else:  # emf
            extension = suffix or ".emf"
            if not extension.startswith("."):
                extension = f".{extension}"
            filename = f"mask_emf{index}{extension}"
        part_name = f"{self._mask_directory}/{filename}"
        return relationship_id, part_name

    def _next_sequence(self) -> int:
        current = self._next_index
        self._next_index += 1
        return current

    def _asset_identifier(self) -> str:
        return f"mask-{len(self._entries) + 1}"

    @staticmethod
    def _vector_key(
        normalized_xml: str,
        mode: str,
        mask_units: str | None,
        mask_content_units: str | None,
    ) -> str:
        token = "|".join(
            [
                "vector",
                mode or "",
                (mask_units or "").lower(),
                (mask_content_units or "").lower(),
                normalized_xml,
            ]
        )
        return _hash_string(token)

    @staticmethod
    def _raster_key(data_hash: str, mode: str, image_format: str) -> str:
        token = "|".join(
            [
                "raster",
                mode or "",
                (image_format or "").lower(),
                data_hash,
            ]
        )
        return _hash_string(token)


def _content_type_from_format(image_format: str) -> str:
    fmt = (image_format or "").lower()
    if fmt in {"png", ""}:
        return "image/png"
    if fmt in {"jpg", "jpeg"}:
        return "image/jpeg"
    if fmt == "gif":
        return "image/gif"
    return "application/octet-stream"


__all__ = ["MaskAsset", "MaskAssetHandle", "MaskAssetStore"]
