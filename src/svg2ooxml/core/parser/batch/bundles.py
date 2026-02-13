"""Slide bundle serialization helpers for parallel batch stitching."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
import os
from pathlib import Path
from typing import Any

from svg2ooxml.common.tempfiles import project_temp_dir
from svg2ooxml.drawingml.assets import (
    AssetRegistrySnapshot,
    FontAsset,
    MediaAsset,
    NavigationAsset,
)
from svg2ooxml.drawingml.result import DrawingMLRenderResult
from svg2ooxml.ir.text import EmbeddedFontPlan

ENV_BUNDLE_DIR = "SVG2OOXML_BUNDLE_DIR"


def bundle_root(base_dir: Path | None = None) -> Path:
    if base_dir is not None:
        root = base_dir
    else:
        override = os.environ.get(ENV_BUNDLE_DIR)
        if override:
            root = Path(override).expanduser()
        else:
            root = project_temp_dir() / "bundles"
    root.mkdir(parents=True, exist_ok=True)
    return root


def job_dir(job_id: str, base_dir: Path | None = None) -> Path:
    path = bundle_root(base_dir) / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_job_id(prefix: str = "job") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def write_slide_bundle(
    result: DrawingMLRenderResult,
    job_id: str,
    slide_index: int,
    *,
    base_dir: Path | None = None,
) -> Path:
    bundle_dir = job_dir(job_id, base_dir) / f"slide_{slide_index:04d}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    assets_dir = bundle_dir / "assets"
    media_dir = assets_dir / "media"
    fonts_dir = assets_dir / "fonts"
    masks_dir = assets_dir / "masks"
    media_dir.mkdir(parents=True, exist_ok=True)
    fonts_dir.mkdir(parents=True, exist_ok=True)
    masks_dir.mkdir(parents=True, exist_ok=True)

    (bundle_dir / "slide.xml").write_text(result.slide_xml, encoding="utf-8")

    media_entries: list[dict[str, Any]] = []
    for index, asset in enumerate(result.assets.iter_media(), start=1):
        suffix = Path(asset.filename).suffix or _suffix_for_content_type(asset.content_type)
        stored_name = f"media_{index}{suffix}"
        data_path = media_dir / stored_name
        data_path.write_bytes(asset.data)
        media_entries.append(
            {
                "relationship_id": asset.relationship_id,
                "filename": asset.filename,
                "content_type": asset.content_type,
                "width_emu": asset.width_emu,
                "height_emu": asset.height_emu,
                "source": asset.source,
                "data_path": str(Path("assets") / "media" / stored_name),
            }
        )

    font_entries: list[dict[str, Any]] = []
    for index, asset in enumerate(result.assets.iter_fonts(), start=1):
        plan = asset.plan
        encoded_metadata = _encode_json(plan.metadata or {}, fonts_dir, f"font_{index}")
        font_entries.append(
            {
                "shape_id": asset.shape_id,
                "plan": {
                    "font_family": plan.font_family,
                    "requires_embedding": plan.requires_embedding,
                    "subset_strategy": plan.subset_strategy,
                    "glyph_count": plan.glyph_count,
                    "relationship_hint": plan.relationship_hint,
                    "metadata": encoded_metadata,
                },
            }
        )

    navigation_entries = [asdict(asset) for asset in result.assets.iter_navigation()]

    mask_entries: list[dict[str, Any]] = []
    for index, mask in enumerate(result.assets.iter_masks(), start=1):
        stored_name = f"mask_{index}.bin"
        data_path = masks_dir / stored_name
        data_path.write_bytes(mask["data"])
        mask_entries.append(
            {
                "relationship_id": mask["relationship_id"],
                "part_name": mask["part_name"],
                "content_type": mask["content_type"],
                "data_path": str(Path("assets") / "masks" / stored_name),
            }
        )

    metadata = {
        "bundle_version": 1,
        "job_id": job_id,
        "slide_index": slide_index,
        "slide_size": list(result.slide_size),
        "media": media_entries,
        "fonts": font_entries,
        "navigation": navigation_entries,
        "masks": mask_entries,
        "diagnostics": list(result.assets.diagnostics),
    }

    (bundle_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return bundle_dir


def read_slide_bundle(bundle_dir: Path) -> DrawingMLRenderResult:
    metadata_path = bundle_dir / "metadata.json"
    data = json.loads(metadata_path.read_text(encoding="utf-8"))

    slide_xml = (bundle_dir / "slide.xml").read_text(encoding="utf-8")
    slide_size_raw = data.get("slide_size") or [0, 0]
    slide_size = (int(slide_size_raw[0]), int(slide_size_raw[1]))

    media_assets: list[MediaAsset] = []
    for entry in data.get("media", []):
        data_path = bundle_dir / entry["data_path"]
        media_assets.append(
            MediaAsset(
                relationship_id=entry["relationship_id"],
                filename=entry.get("filename") or "",
                content_type=entry["content_type"],
                data=data_path.read_bytes(),
                width_emu=entry.get("width_emu"),
                height_emu=entry.get("height_emu"),
                source=entry.get("source"),
            )
        )

    font_assets: list[FontAsset] = []
    for entry in data.get("fonts", []):
        plan_dict = entry["plan"]
        metadata = _decode_json(plan_dict.get("metadata") or {}, bundle_dir)
        plan = EmbeddedFontPlan(
            font_family=plan_dict["font_family"],
            requires_embedding=bool(plan_dict["requires_embedding"]),
            subset_strategy=plan_dict["subset_strategy"],
            glyph_count=int(plan_dict.get("glyph_count") or 0),
            relationship_hint=plan_dict.get("relationship_hint"),
            metadata=metadata,
        )
        font_assets.append(FontAsset(shape_id=int(entry["shape_id"]), plan=plan))

    navigation_assets = [
        NavigationAsset(**entry) for entry in data.get("navigation", [])
    ]

    mask_entries: list[dict[str, object]] = []
    for entry in data.get("masks", []):
        data_path = bundle_dir / entry["data_path"]
        mask_entries.append(
            {
                "relationship_id": entry["relationship_id"],
                "part_name": entry["part_name"],
                "content_type": entry["content_type"],
                "data": data_path.read_bytes(),
            }
        )

    diagnostics = tuple(data.get("diagnostics") or [])
    assets = AssetRegistrySnapshot(
        media=tuple(media_assets),
        fonts=tuple(font_assets),
        navigation=tuple(navigation_assets),
        diagnostics=diagnostics,
        masks=tuple(mask_entries),
    )

    return DrawingMLRenderResult(
        slide_xml=slide_xml,
        slide_size=slide_size,
        assets=assets,
    )


def load_job_bundles(job_id: str, *, base_dir: Path | None = None) -> list[DrawingMLRenderResult]:
    root = job_dir(job_id, base_dir)
    bundles = []
    for bundle in sorted(root.glob("slide_*")):
        bundles.append(read_slide_bundle(bundle))
    return bundles


def list_job_bundle_dirs(job_id: str, *, base_dir: Path | None = None) -> list[Path]:
    root = job_dir(job_id, base_dir)
    return sorted(root.glob("slide_*"))


def _suffix_for_content_type(content_type: str) -> str:
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
        "image/x-emf": ".emf",
    }
    return mapping.get(content_type, ".bin")


def _encode_json(value: Any, assets_dir: Path, prefix: str) -> Any:
    counter = {"index": 0}
    assets_dir.mkdir(parents=True, exist_ok=True)

    def _encode(obj: Any) -> Any:
        if isinstance(obj, (bytes, bytearray)):
            counter["index"] += 1
            filename = f"{prefix}_{counter['index']}.bin"
            path = assets_dir / filename
            path.write_bytes(bytes(obj))
            return {"__bytes__": str(Path("assets") / "fonts" / filename)}
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, tuple):
            return [_encode(item) for item in obj]
        if isinstance(obj, list):
            return [_encode(item) for item in obj]
        if isinstance(obj, dict):
            return {str(key): _encode(val) for key, val in obj.items()}
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        return str(obj)

    return _encode(value)


def _decode_json(value: Any, bundle_dir: Path) -> Any:
    if isinstance(value, dict) and "__bytes__" in value:
        rel = Path(value["__bytes__"])
        return (bundle_dir / rel).read_bytes()
    if isinstance(value, list):
        return [_decode_json(item, bundle_dir) for item in value]
    if isinstance(value, dict):
        return {key: _decode_json(val, bundle_dir) for key, val in value.items()}
    return value


__all__ = [
    "bundle_root",
    "job_dir",
    "new_job_id",
    "write_slide_bundle",
    "read_slide_bundle",
    "load_job_bundles",
    "list_job_bundle_dirs",
]
