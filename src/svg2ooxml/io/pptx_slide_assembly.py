"""Build slide-level package metadata from DrawingML render results."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path

from lxml import etree as ET

from svg2ooxml.common.boundaries import is_safe_relationship_id
from svg2ooxml.drawingml.assets import MediaAsset
from svg2ooxml.drawingml.result import DrawingMLRenderResult
from svg2ooxml.io.pptx_package_constants import R_DOC_NS, REL_NS
from svg2ooxml.io.pptx_package_model import MaskAsset, PackagedMedia, SlideAssembly
from svg2ooxml.io.pptx_part_names import (
    normalized_content_type,
    sanitize_media_filename,
    suffix_for_content_type,
)


class PackagingContext:
    """Assign unique identifiers and filenames while packaging."""

    def __init__(self) -> None:
        self._media_by_signature: dict[tuple[str, str], str] = {}
        self._used_media_filenames: set[str] = set()
        self._media_counter = 1
        self._presentation_rel_counter = 2
        self._next_slide_id = 256

    def assign_media_filename(self, asset: MediaAsset, slide_index: int) -> str:
        """Return a deterministic filename for the supplied media payload."""
        digest = hashlib.md5(asset.data, usedforsecurity=False).hexdigest()
        key = (asset.filename, digest, normalized_content_type(asset.content_type))
        existing = self._media_by_signature.get(key)
        if existing:
            return existing

        base = sanitize_media_filename(
            asset.filename or f"media_{self._media_counter}",
            asset.content_type,
        )
        path = Path(base)
        stem = path.stem or "media"
        suffix = path.suffix or self._suffix_for_content_type(asset.content_type)
        candidate = f"{stem}{suffix}"

        while candidate in self._used_media_filenames:
            candidate = f"{stem}_{slide_index}_{self._media_counter}{suffix}"
            self._media_counter += 1

        self._media_by_signature[key] = candidate
        self._used_media_filenames.add(candidate)
        self._media_counter += 1
        return candidate

    def allocate_slide_entry(self) -> tuple[str, int]:
        """Allocate presentation relationship and slide id."""
        rel_id = f"rId{self._presentation_rel_counter}"
        self._presentation_rel_counter += 1
        slide_id = self._next_slide_id
        self._next_slide_id += 1
        return rel_id, slide_id

    def allocate_media_relationship_id(
        self,
        preferred_id: object | None = None,
        *,
        existing_ids: set[str] | None = None,
    ) -> str:
        """Return a safe media relationship ID."""

        existing_ids = existing_ids or set()
        if is_safe_relationship_id(preferred_id) and preferred_id not in existing_ids:
            assert isinstance(preferred_id, str)
            return preferred_id

        while True:
            rel_id = f"rIdMedia{self._media_counter}"
            self._media_counter += 1
            if rel_id not in existing_ids:
                return rel_id

    @staticmethod
    def _suffix_for_content_type(content_type: str) -> str:
        return suffix_for_content_type(content_type)


class SlideAssembler:
    """Build slide-level packaging metadata from DrawingML render results."""

    def __init__(
        self,
        context: PackagingContext,
        *,
        slide_rels_template: str,
    ) -> None:
        self._context = context
        self._reserved_relationship_ids = _slide_relationship_template_ids(
            slide_rels_template
        )

    def assemble_one(self, result: DrawingMLRenderResult, index: int) -> SlideAssembly:
        """Assemble packaging metadata for a single render result."""
        rel_id, slide_id = self._context.allocate_slide_entry()
        slide_filename = f"slide{index}.xml"
        relationship_rewrites: dict[str, str] = {}
        used_relationship_ids = set(self._reserved_relationship_ids)
        seen_input_relationship_ids: set[str] = set()
        media_parts: list[PackagedMedia] = []
        for asset in result.assets.iter_media():
            _track_unique_input_relationship_id(
                asset.relationship_id,
                seen_input_relationship_ids,
                kind="media",
            )
            assigned_name = self._context.assign_media_filename(asset, index)
            assigned_relationship_id = self._context.allocate_media_relationship_id(
                asset.relationship_id,
                existing_ids=used_relationship_ids,
            )
            used_relationship_ids.add(assigned_relationship_id)
            _record_relationship_rewrite(
                relationship_rewrites,
                asset.relationship_id,
                assigned_relationship_id,
            )
            media_parts.append(
                PackagedMedia(
                    relationship_id=assigned_relationship_id,
                    filename=assigned_name,
                    content_type=asset.content_type,
                    data=asset.data,
                )
            )

        mask_parts: list[MaskAsset] = []
        for mask in result.assets.iter_masks():
            relationship_id = mask.get("relationship_id")
            _track_unique_input_relationship_id(
                relationship_id,
                seen_input_relationship_ids,
                kind="mask",
            )
            assigned_relationship_id = self._context.allocate_media_relationship_id(
                relationship_id,
                existing_ids=used_relationship_ids,
            )
            used_relationship_ids.add(assigned_relationship_id)
            _record_relationship_rewrite(
                relationship_rewrites,
                relationship_id,
                assigned_relationship_id,
            )
            mask_parts.append(
                MaskAsset(
                    relationship_id=assigned_relationship_id,
                    part_name=mask["part_name"],
                    content_type=mask["content_type"],
                    data=mask["data"],
                )
            )

        return SlideAssembly(
            index=index,
            filename=slide_filename,
            rel_id=rel_id,
            slide_id=slide_id,
            slide_xml=_rewrite_slide_relationship_references(
                result.slide_xml,
                relationship_rewrites,
            ),
            slide_size=result.slide_size,
            media=media_parts,
            navigation=list(result.assets.iter_navigation()),
            masks=mask_parts,
            font_assets=list(result.assets.iter_fonts()),
        )

    def assemble(self, render_results: Sequence[DrawingMLRenderResult]) -> list[SlideAssembly]:
        return [
            self.assemble_one(result, index)
            for index, result in enumerate(render_results, start=1)
        ]


def _slide_relationship_template_ids(slide_rels_template: str) -> set[str]:
    rels_root = ET.fromstring(slide_rels_template.encode("utf-8"))
    return {
        rel_id
        for rel_id in (
            rel.get("Id")
            for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")
        )
        if rel_id
    }


def _track_unique_input_relationship_id(
    relationship_id: object,
    seen_ids: set[str],
    *,
    kind: str,
) -> None:
    if not isinstance(relationship_id, str) or not relationship_id:
        return
    if relationship_id in seen_ids:
        raise ValueError(
            f"Duplicate {kind} relationship ID {relationship_id!r} in one slide."
        )
    seen_ids.add(relationship_id)


def _record_relationship_rewrite(
    rewrites: dict[str, str],
    old_id: object,
    new_id: str,
) -> None:
    if isinstance(old_id, str) and old_id and old_id != new_id:
        rewrites[old_id] = new_id


def _rewrite_slide_relationship_references(
    slide_xml: str,
    relationship_rewrites: Mapping[str, str],
) -> str:
    if not relationship_rewrites:
        return slide_xml

    parser = ET.XMLParser(resolve_entities=False, no_network=True)
    try:
        root = ET.fromstring(slide_xml.encode("utf-8"), parser)
    except ET.XMLSyntaxError as exc:
        raise ValueError(
            "Slide XML must be well-formed to rekey packaged relationships."
        ) from exc

    changed = False
    for element in root.iter():
        for attr_name, attr_value in list(element.attrib.items()):
            if (
                attr_name.startswith(f"{{{R_DOC_NS}}}")
                and attr_value in relationship_rewrites
            ):
                element.set(attr_name, relationship_rewrites[attr_value])
                changed = True
    if not changed:
        return slide_xml

    tostring_kwargs: dict[str, object] = {
        "encoding": "UTF-8",
        "xml_declaration": slide_xml.lstrip().startswith("<?xml"),
    }
    if 'standalone="yes"' in slide_xml[:200] or "standalone='yes'" in slide_xml[:200]:
        tostring_kwargs["standalone"] = True
    return ET.tostring(root, **tostring_kwargs).decode("utf-8")


__all__ = [
    "PackagingContext",
    "SlideAssembler",
]
