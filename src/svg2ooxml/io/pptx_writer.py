"""PPTX packaging helpers built on top of the DrawingML writer."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence, TYPE_CHECKING

from lxml import etree as ET

from svg2ooxml.common.tempfiles import temporary_directory
from svg2ooxml.drawingml.assets import FontAsset, MediaAsset, NavigationAsset
from svg2ooxml.drawingml.result import DrawingMLRenderResult
from svg2ooxml.drawingml.writer import DrawingMLWriter
from svg2ooxml.core.ir import IRScene
from svg2ooxml.ir.text import EmbeddedFontPlan

if TYPE_CHECKING:  # pragma: no cover - typing only
    from svg2ooxml.core.tracing import ConversionTracer

ASSETS_ROOT = Path(__file__).resolve().parents[3] / "assets" / "pptx_templates"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_DOC_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
# PowerPoint masks reference normal ImagePart relationships; no dedicated mask rel type exists.
# Examples: standard PowerPoint .rels files authored by Microsoft Office only emit the image URI.
MASK_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"


@dataclass
class _PackagedMedia:
    relationship_id: str
    filename: str
    content_type: str
    data: bytes

    @property
    def package_path(self) -> Path:
        return Path("ppt") / "media" / self.filename

    @property
    def relationship_target(self) -> str:
        return f"../media/{self.filename}"


@dataclass
class _SlideEntry:
    index: int
    filename: str
    rel_id: str
    slide_id: int
    media: list[_PackagedMedia]
    navigation: list[NavigationAsset] = field(default_factory=list)
    masks: list[_MaskAsset] = field(default_factory=list)


@dataclass
class _PackagedFont:
    filename: str
    relationship_id: str
    font_family: str
    subsetted: bool
    content_type: str


@dataclass
class _MaskAsset:
    relationship_id: str
    part_name: str
    content_type: str
    data: bytes

    @property
    def package_path(self) -> Path:
        part = self.part_name.lstrip("/")
        return Path(part)

    @property
    def relationship_target(self) -> str:
        path = self.package_path
        if path.parts and path.parts[0] == "ppt":
            relative_parts = ["..", *path.parts[1:]]
            return "/".join(relative_parts)
        return path.as_posix()


class _PackagingContext:
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
        key = (asset.filename, digest)
        existing = self._media_by_signature.get(key)
        if existing:
            return existing

        base = asset.filename or f"media_{self._media_counter}"
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

    @staticmethod
    def _suffix_for_content_type(content_type: str) -> str:
        mapping = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "image/svg+xml": ".svg",
            "image/x-emf": ".emf",
        }
        return mapping.get(content_type, ".bin")


class PPTXPackageBuilder:
    """Create PPTX packages using the clean-slate template library."""

    def __init__(self, *, assets_root: Path | None = None) -> None:
        self._assets_root = assets_root or ASSETS_ROOT
        self._base_template = self._assets_root / "clean_slate"
        self._content_types_template = (self._assets_root / "content_types.xml").read_text(encoding="utf-8")
        self._slide_rels_template = (
            self._base_template / "ppt" / "slides" / "_rels" / "slide.xml.rels"
        ).read_text(encoding="utf-8")
        self._writer = DrawingMLWriter(template_dir=self._assets_root)
        self._tracer: "ConversionTracer | None" = None

    def build(
        self,
        scene: IRScene,
        output_path: str | Path,
        *,
        tracer: "ConversionTracer | None" = None,
        persist_trace: bool | None = None,
    ) -> Path:
        """Materialise a PPTX file for the supplied IR scene."""
        return self.build_scenes([scene], output_path, tracer=tracer, persist_trace=persist_trace)

    def build_scenes(
        self,
        scenes: Sequence[IRScene],
        output_path: str | Path,
        *,
        tracer: "ConversionTracer | None" = None,
        persist_trace: bool | None = None,
    ) -> Path:
        """Materialise a PPTX file for a sequence of IR scenes."""
        render_results = []
        for scene in scenes:
            animation_payload = None
            if isinstance(scene.metadata, dict):
                animation_payload = scene.metadata.get("animation_raw")
            render_results.append(
                self._writer.render_scene_from_ir(
                    scene,
                    tracer=tracer,
                    animation_payload=animation_payload,
                )
            )
        return self.build_from_results(render_results, output_path, tracer=tracer, persist_trace=persist_trace)

    def build_from_results(
        self,
        render_results: Sequence[DrawingMLRenderResult],
        output_path: str | Path,
        *,
        tracer: "ConversionTracer | None" = None,
        persist_trace: bool | None = None,
    ) -> Path:
        """Package pre-rendered slides returned by DrawingMLWriter."""

        prev_tracer = self._tracer
        self._tracer = tracer
        should_persist_trace = (tracer is not None) if persist_trace is None else (bool(persist_trace) and tracer is not None)

        if not render_results:
            raise ValueError("At least one render result is required to build a PPTX package.")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        context = _PackagingContext()

        try:
            with temporary_directory(prefix="svg2ooxml_pptx_") as temp_path:
                shutil.copytree(self._base_template, temp_path, dirs_exist_ok=True)
                self._trace_packaging(
                    "packaging_start",
                    metadata={"slide_count": len(render_results)},
                )

                slides_dir = temp_path / "ppt" / "slides"
                slides_dir.mkdir(parents=True, exist_ok=True)
                (slides_dir / "_rels").mkdir(exist_ok=True)
                # The clean-slate template ships a placeholder `slide.xml.rels` that references
                # the stock layout. Delete it so the package only contains the slides we emit.
                template_slide_rels = slides_dir / "_rels" / "slide.xml.rels"
                if template_slide_rels.exists():
                    template_slide_rels.unlink()

                slide_entries: list[_SlideEntry] = []
                all_media: list[_PackagedMedia] = []
                font_assets: list[FontAsset] = []
                all_masks: list[_MaskAsset] = []

                for index, result in enumerate(render_results, start=1):
                    rel_id, slide_id = context.allocate_slide_entry()
                    slide_filename = f"slide{index}.xml"
                    (slides_dir / slide_filename).write_text(result.slide_xml, encoding="utf-8")
                    self._trace_packaging(
                        "slide_xml_written",
                    metadata={"filename": slide_filename, "index": index},
                )

                    media_parts: list[_PackagedMedia] = []
                    mask_parts: list[_MaskAsset] = []
                    navigation_assets = list(result.assets.iter_navigation())
                    for asset in result.assets.iter_media():
                        assigned_name = context.assign_media_filename(asset, index)
                        media_parts.append(
                            _PackagedMedia(
                                relationship_id=asset.relationship_id,
                                filename=assigned_name,
                                content_type=asset.content_type,
                                data=asset.data,
                            )
                        )
                        self._trace_packaging(
                            "media_enqueued",
                            metadata={
                                "relationship_id": asset.relationship_id,
                                "filename": assigned_name,
                                "content_type": asset.content_type,
                            },
                        )
                    mask_snapshot = list(result.assets.iter_masks())
                    for mask in mask_snapshot:
                        mask_parts.append(
                            _MaskAsset(
                                relationship_id=mask["relationship_id"],
                                part_name=mask["part_name"],
                                content_type=mask["content_type"],
                                data=mask["data"],
                            )
                        )
                        self._trace_packaging(
                            "mask_enqueued",
                            metadata={
                                "relationship_id": mask["relationship_id"],
                                "part_name": mask["part_name"],
                            },
                        )
                    self._write_slide_relationships(slides_dir, index, media_parts, navigation_assets, mask_parts)
                    self._trace_packaging(
                        "slide_relationships_updated",
                        metadata={"index": index, "media_count": len(media_parts), "mask_count": len(mask_parts)},
                    )

                    slide_entries.append(
                        _SlideEntry(
                            index=index,
                            filename=slide_filename,
                            rel_id=rel_id,
                            slide_id=slide_id,
                            media=media_parts,
                            masks=mask_parts,
                            navigation=navigation_assets,
                        )
                    )

                    all_media.extend(media_parts)
                    font_assets.extend(result.assets.iter_fonts())
                    all_masks.extend(mask_parts)

                    self._write_media_parts(temp_path, all_media)
                    self._write_mask_parts(temp_path, all_masks)
                    packaged_fonts = self._write_font_parts(temp_path, font_assets)

                # Determine presentation slide size from first slide
                # (all slides should have the same dimensions)
                presentation_slide_size = render_results[0].slide_size if render_results else None

                self._update_presentation_parts(temp_path, slide_entries, packaged_fonts, presentation_slide_size)
                self._write_content_types(temp_path, slide_entries, all_media, packaged_fonts, all_masks)
                self._trace_packaging(
                        "content_types_updated",
                        metadata={
                            "slide_count": len(slide_entries),
                            "media_count": len(all_media),
                            "font_count": len(packaged_fonts),
                            "mask_count": len(all_masks),
                        },
                    )

                with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                    for file_path in temp_path.rglob("*"):
                        if file_path.is_file():
                            archive.write(file_path, file_path.relative_to(temp_path))
                self._trace_packaging(
                    "pptx_written",
                    metadata={"path": str(output)},
                )

                if should_persist_trace and tracer is not None:
                    trace_path = output.with_suffix(".trace.json")
                    trace_payload = tracer.report().to_dict()
                    trace_path.write_text(json.dumps(trace_payload, indent=2), encoding="utf-8")
                    self._trace_packaging(
                        "trace_persisted",
                        metadata={"path": str(trace_path)},
                    )

                self._trace_packaging(
                    "packaging_complete",
                    metadata={"path": str(output)},
                )

                return output
        finally:
            self._tracer = prev_tracer

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _trace_packaging(
        self,
        action: str,
        *,
        metadata: dict[str, object] | None = None,
        subject: str | None = None,
        stage: str = "packaging",
    ) -> None:
        tracer = self._tracer
        if tracer is None:
            return
        tracer.record_stage_event(stage=stage, action=action, metadata=metadata, subject=subject)

    def _write_media_parts(self, package_root: Path, media_parts: Sequence[_PackagedMedia]) -> None:
        if not media_parts:
            return
        media_dir = package_root / "ppt" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        unique_media: dict[str, _PackagedMedia] = {}
        for part in media_parts:
            unique_media.setdefault(part.filename, part)
        for part in unique_media.values():
            target = media_dir / part.filename
            with target.open("wb") as handle:
                handle.write(part.data)
            self._trace_packaging(
                "media_part_written",
                metadata={
                    "filename": part.filename,
                    "content_type": part.content_type,
                },
                subject=part.relationship_id,
            )

    def _write_mask_parts(self, package_root: Path, mask_parts: Sequence[_MaskAsset]) -> None:
        if not mask_parts:
            return
        written: set[Path] = set()
        for part in mask_parts:
            path = package_root / part.package_path
            if path in written:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as handle:
                handle.write(part.data)
            written.add(path)
            self._trace_packaging(
                "mask_part_written",
                metadata={"path": str(part.package_path)},
                subject=part.relationship_id,
            )

    def _write_slide_relationships(
        self,
        slides_dir: Path,
        slide_index: int,
        media_parts: Sequence[_PackagedMedia],
        navigation_assets: Sequence[NavigationAsset],
        mask_parts: Sequence[_MaskAsset],
    ) -> None:
        rels_path = slides_dir / "_rels" / f"slide{slide_index}.xml.rels"
        rels_root = ET.fromstring(self._slide_rels_template.encode("utf-8"))
        existing_ids = {rel.get("Id") for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")}

        for part in media_parts:
            if part.relationship_id in existing_ids:
                continue
            ET.SubElement(
                rels_root,
                f"{{{REL_NS}}}Relationship",
                {
                    "Id": part.relationship_id,
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                    "Target": part.relationship_target,
                },
            )
            existing_ids.add(part.relationship_id)

        for mask in mask_parts:
            if mask.relationship_id in existing_ids:
                continue
            ET.SubElement(
                rels_root,
                f"{{{REL_NS}}}Relationship",
                {
                    "Id": mask.relationship_id,
                    "Type": MASK_REL_TYPE,
                    "Target": mask.relationship_target,
                },
            )
            existing_ids.add(mask.relationship_id)

        for asset in navigation_assets:
            if not asset.requires_relationship():
                continue
            rel_id = asset.relationship_id
            if rel_id in existing_ids or asset.relationship_type is None or asset.target is None:
                continue
            attributes = {
                "Id": rel_id,
                "Type": asset.relationship_type,
                "Target": asset.target,
            }
            if asset.target_mode:
                attributes["TargetMode"] = asset.target_mode
            ET.SubElement(
                rels_root,
                f"{{{REL_NS}}}Relationship",
                attributes,
            )
            existing_ids.add(rel_id)

        ET.ElementTree(rels_root).write(rels_path, encoding="utf-8", xml_declaration=True)

    def _write_font_parts(
        self,
        package_root: Path,
        font_assets: Sequence[FontAsset],
    ) -> list[_PackagedFont]:
        if not font_assets:
            return []

        entries: list[tuple[EmbeddedFontPlan, dict[str, object], bytes]] = []
        seen_keys: set[tuple[object, ...]] = set()
        for asset in font_assets:
            plan = asset.plan
            if not plan.requires_embedding:
                continue
            metadata = plan.metadata or {}
            font_data = metadata.get("font_data")
            if not isinstance(font_data, (bytes, bytearray)):
                continue
            font_bytes = bytes(font_data)
            digest = hashlib.md5(font_bytes, usedforsecurity=False).hexdigest()
            key = (
                plan.font_family,
                plan.subset_strategy,
                plan.glyph_count,
                plan.relationship_hint,
                digest,
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entries.append((plan, metadata, font_bytes))

        if not entries:
            return []

        fonts_dir = package_root / "ppt" / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)

        packaged_fonts: list[_PackagedFont] = []
        used_relationships: set[str] = set()
        rel_seed = 1
        filename_index = 1

        for plan, metadata, font_bytes in entries:
            font_family = plan.font_family or metadata.get("font_family") or "EmbeddedFont"
            font_path_hint = metadata.get("font_path")
            extension = None
            if isinstance(font_path_hint, str):
                extension = Path(font_path_hint).suffix.lstrip(".")
            if not extension:
                extension = "ttf"
            extension = extension.lower()

            rel_id = plan.relationship_hint if isinstance(plan.relationship_hint, str) and plan.relationship_hint else None
            if rel_id and rel_id in used_relationships:
                rel_id = None
            if rel_id is None:
                while True:
                    candidate = f"rIdFont{rel_seed}"
                    rel_seed += 1
                    if candidate not in used_relationships:
                        rel_id = candidate
                        break
            used_relationships.add(rel_id)

            filename = f"font{filename_index}.{extension}"
            filename_index += 1
            target_path = fonts_dir / filename
            with target_path.open("wb") as handle:
                handle.write(font_bytes)
            self._trace_packaging(
                "font_part_written",
                stage="font",
                metadata={
                    "filename": filename,
                    "relationship_id": rel_id,
                    "font_family": font_family,
                },
            )

            packaged_fonts.append(
                _PackagedFont(
                    filename=filename,
                    relationship_id=rel_id,
                    font_family=font_family,
                    subsetted=bool(plan.glyph_count),
                    content_type=_content_type_for_extension(extension),
                )
            )

        return packaged_fonts

    def _update_presentation_parts(
        self,
        package_root: Path,
        slide_entries: Sequence[_SlideEntry],
        fonts: Sequence[_PackagedFont],
        slide_size: tuple[int, int] | None = None,
    ) -> None:
        presentation_path = package_root / "ppt" / "presentation.xml"
        tree = ET.parse(presentation_path)
        root = tree.getroot()
        ns = {"p": P_NS, "r": R_DOC_NS}

        # Update slide dimensions if provided
        if slide_size is not None:
            slide_sz = root.find("p:sldSz", ns)
            if slide_sz is not None:
                slide_sz.set("cx", str(slide_size[0]))
                slide_sz.set("cy", str(slide_size[1]))
                self._trace_packaging(
                    "presentation_dimensions_updated",
                    metadata={
                        "width_emu": slide_size[0],
                        "height_emu": slide_size[1],
                        "width_inches": slide_size[0] / 914400,
                        "height_inches": slide_size[1] / 914400,
                    },
                )

        slide_list = root.find("p:sldIdLst", ns)
        if slide_list is None:
            slide_list = ET.SubElement(root, f"{{{P_NS}}}sldIdLst")
        else:
            for child in list(slide_list):
                slide_list.remove(child)

        for entry in slide_entries:
            attrs = {
                "id": str(entry.slide_id),
                f"{{{R_DOC_NS}}}id": entry.rel_id,
            }
            ET.SubElement(slide_list, f"{{{P_NS}}}sldId", attrs)

        if fonts:
            font_list = root.find("p:embeddedFontLst", ns)
            if font_list is None:
                font_list = ET.SubElement(root, f"{{{P_NS}}}embeddedFontLst")
            existing_families: set[str] = {
                font_elem.find("p:font", ns).get("typeface")
                for font_elem in font_list.findall("p:embeddedFont", ns)
                if font_elem.find("p:font", ns) is not None
            }

            for font in fonts:
                if font.font_family in existing_families:
                    continue
                entry_elem = ET.SubElement(font_list, f"{{{P_NS}}}embeddedFont")
                ET.SubElement(entry_elem, f"{{{P_NS}}}font", {"typeface": font.font_family})
                attrs = {
                    f"{{{R_DOC_NS}}}id": font.relationship_id,
                    f"{{{R_DOC_NS}}}subsetted": "1" if font.subsetted else "0",
                }
                ET.SubElement(entry_elem, f"{{{P_NS}}}regular", attrs)
                existing_families.add(font.font_family)

        tree.write(presentation_path, encoding="utf-8", xml_declaration=True)

        rels_path = package_root / "ppt" / "_rels" / "presentation.xml.rels"
        rels_tree = ET.parse(rels_path)
        rels_root = rels_tree.getroot()

        for rel in list(rels_root.findall(f"{{{REL_NS}}}Relationship")):
            if rel.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide":
                rels_root.remove(rel)

        existing_rel_ids = {rel.get("Id") for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")}

        for entry in slide_entries:
            if entry.rel_id in existing_rel_ids:
                continue
            ET.SubElement(
                rels_root,
                f"{{{REL_NS}}}Relationship",
                {
                    "Id": entry.rel_id,
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
                    "Target": f"slides/{entry.filename}",
                },
            )
            existing_rel_ids.add(entry.rel_id)

        for font in fonts:
            if font.relationship_id in existing_rel_ids:
                continue
            ET.SubElement(
                rels_root,
                f"{{{REL_NS}}}Relationship",
                {
                    "Id": font.relationship_id,
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font",
                    "Target": f"fonts/{font.filename}",
                },
            )
            existing_rel_ids.add(font.relationship_id)

        rels_tree.write(rels_path, encoding="utf-8", xml_declaration=True)

    def _write_content_types(
        self,
        package_root: Path,
        slide_entries: Sequence[_SlideEntry],
        media_parts: Sequence[_PackagedMedia],
        fonts: Sequence[_PackagedFont],
        mask_parts: Sequence[_MaskAsset],
    ) -> None:
        content_types_path = package_root / "[Content_Types].xml"
        root = ET.fromstring(self._content_types_template.encode("utf-8"))

        for node in list(root.findall(f"{{{CONTENT_NS}}}Override")):
            part = node.get("PartName", "")
            if part.startswith("/ppt/slides/slide"):
                root.remove(node)

        for entry in slide_entries:
            ET.SubElement(
                root,
                f"{{{CONTENT_NS}}}Override",
                {
                    "PartName": f"/ppt/slides/{entry.filename}",
                    "ContentType": "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
                },
            )

        existing_defaults = {
            node.get("Extension"): node for node in root.findall(f"{{{CONTENT_NS}}}Default")
        }
        unique_media_ext: dict[str, str] = {}
        for part in media_parts:
            ext = Path(part.filename).suffix.lstrip(".").lower()
            if not ext:
                continue
            unique_media_ext.setdefault(ext, part.content_type)

        for ext, content_type in unique_media_ext.items():
            default = existing_defaults.get(ext)
            if default is None:
                existing_defaults[ext] = ET.SubElement(
                    root,
                    f"{{{CONTENT_NS}}}Default",
                    {"Extension": ext, "ContentType": content_type},
                )

        existing_overrides = {
            node.get("PartName"): node for node in root.findall(f"{{{CONTENT_NS}}}Override")
        }

        for font in fonts:
            ext = Path(font.filename).suffix.lstrip(".").lower()
            if ext and ext not in existing_defaults:
                existing_defaults[ext] = ET.SubElement(
                    root,
                    f"{{{CONTENT_NS}}}Default",
                    {"Extension": ext, "ContentType": font.content_type},
                )
            part_name = f"/ppt/fonts/{font.filename}"
            if part_name not in existing_overrides:
                existing_overrides[part_name] = ET.SubElement(
                    root,
                    f"{{{CONTENT_NS}}}Override",
                    {"PartName": part_name, "ContentType": font.content_type},
                )

        for mask in mask_parts:
            part_name = mask.part_name
            if part_name not in existing_overrides:
                existing_overrides[part_name] = ET.SubElement(
                    root,
                    f"{{{CONTENT_NS}}}Override",
                    {"PartName": part_name, "ContentType": mask.content_type},
                )

        ET.ElementTree(root).write(content_types_path, encoding="utf-8", xml_declaration=True)


def write_pptx(scene: IRScene, output_path: str | Path) -> Path:
    """Public helper mirroring the historical API."""

    builder = PPTXPackageBuilder()
    return builder.build(scene, output_path)


def _content_type_for_extension(extension: str) -> str:
    mapping = {
        "ttf": "application/x-font-ttf",
        "otf": "application/x-font-otf",
        "woff": "application/font-woff",
        "woff2": "application/font-woff2",
        "odttf": "application/vnd.openxmlformats-officedocument.obfuscatedFont",
    }
    return mapping.get(extension.lower(), "application/octet-stream")


__all__ = ["PPTXPackageBuilder", "write_pptx"]
