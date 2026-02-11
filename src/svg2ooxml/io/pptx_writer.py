"""PPTX packaging helpers built on top of the DrawingML writer."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
import zipfile
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree as ET

from svg2ooxml.common.tempfiles import temporary_directory
from svg2ooxml.core.ir import IRScene
from svg2ooxml.drawingml.assets import FontAsset, MediaAsset, NavigationAsset
from svg2ooxml.drawingml.result import DrawingMLRenderResult
from svg2ooxml.drawingml.writer import DEFAULT_SLIDE_SIZE, DrawingMLWriter
from svg2ooxml.ir.text import EmbeddedFontPlan

if TYPE_CHECKING:  # pragma: no cover - typing only
    from svg2ooxml.core.tracing import ConversionTracer

ASSETS_ROOT = Path(__file__).resolve().parents[3] / "assets" / "pptx_templates"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_DOC_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
THEME_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
THEME_FAMILY_NS = "http://schemas.microsoft.com/office/thememl/2012/main"
ET.register_namespace("thm15", THEME_FAMILY_NS)
# PowerPoint masks reference normal ImagePart relationships; no dedicated mask rel type exists.
# Examples: standard PowerPoint .rels files authored by Microsoft Office only emit the image URI.
MASK_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
FONT_STYLE_TAGS: dict[str, str] = {
    "regular": "regular",
    "bold": "bold",
    "italic": "italic",
    "boldItalic": "boldItalic",
}
FONT_STYLE_ORDER: tuple[str, ...] = ("regular", "bold", "italic", "boldItalic")


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
class SlideAssembly:
    index: int
    filename: str
    rel_id: str
    slide_id: int
    slide_xml: str
    slide_size: tuple[int, int]
    media: list[_PackagedMedia]
    navigation: list[NavigationAsset] = field(default_factory=list)
    masks: list[_MaskAsset] = field(default_factory=list)
    font_assets: list[FontAsset] = field(default_factory=list)


@dataclass
class _PackagedFont:
    filename: str
    relationship_id: str
    font_family: str
    subsetted: bool
    content_type: str
    style_kind: str = "regular"
    style_flags: dict[str, bool] = field(default_factory=dict)
    guid: str | None = None
    root_string: str | None = None
    subset_prefix: str | None = None
    pitch_family: int | None = None
    charset: int | None = None


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


@dataclass(frozen=True, slots=True)
class _SlideEntry:
    """Lightweight slide metadata retained during streaming (no XML/binary data)."""

    index: int
    filename: str
    rel_id: str
    slide_id: int
    slide_size: tuple[int, int]


@dataclass(frozen=True, slots=True)
class _MediaMeta:
    """Lightweight media metadata for content-type tracking (no binary data)."""

    filename: str
    content_type: str


@dataclass(frozen=True, slots=True)
class _MaskMeta:
    """Lightweight mask metadata for content-type tracking (no binary data)."""

    part_name: str
    content_type: str


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


class SlideAssembler:
    """Build slide-level packaging metadata from DrawingML render results."""

    def __init__(self, context: PackagingContext) -> None:
        self._context = context

    def assemble_one(self, result: DrawingMLRenderResult, index: int) -> SlideAssembly:
        """Assemble packaging metadata for a single render result."""
        rel_id, slide_id = self._context.allocate_slide_entry()
        slide_filename = f"slide{index}.xml"
        media_parts: list[_PackagedMedia] = []
        for asset in result.assets.iter_media():
            assigned_name = self._context.assign_media_filename(asset, index)
            media_parts.append(
                _PackagedMedia(
                    relationship_id=asset.relationship_id,
                    filename=assigned_name,
                    content_type=asset.content_type,
                    data=asset.data,
                )
            )

        mask_parts: list[_MaskAsset] = []
        for mask in result.assets.iter_masks():
            mask_parts.append(
                _MaskAsset(
                    relationship_id=mask["relationship_id"],
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
            slide_xml=result.slide_xml,
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


ALLOWED_SLIDE_SIZE_MODES = {"multipage", "same"}


class PPTXPackageBuilder:
    """Create PPTX packages using the clean-slate template library."""

    def __init__(self, *, assets_root: Path | None = None, slide_size_mode: str | None = None) -> None:
        self._assets_root = assets_root or ASSETS_ROOT
        self._base_template = self._assets_root / "clean_slate"
        self._content_types_template = (self._assets_root / "content_types.xml").read_text(encoding="utf-8")
        self._slide_rels_template = (
            self._base_template / "ppt" / "slides" / "_rels" / "slide.xml.rels"
        ).read_text(encoding="utf-8")
        self._writer = DrawingMLWriter(template_dir=self._assets_root)
        if slide_size_mode is not None and slide_size_mode not in ALLOWED_SLIDE_SIZE_MODES:
            raise ValueError(
                f"Unsupported slide_size_mode {slide_size_mode!r}. "
                f"Expected one of {sorted(ALLOWED_SLIDE_SIZE_MODES)}."
            )
        self._slide_size_mode = slide_size_mode

    def build(
        self,
        scene: IRScene,
        output_path: str | Path,
        *,
        tracer: ConversionTracer | None = None,
        persist_trace: bool | None = None,
    ) -> Path:
        """Materialise a PPTX file for the supplied IR scene."""
        return self.build_scenes([scene], output_path, tracer=tracer, persist_trace=persist_trace)

    def build_scenes(
        self,
        scenes: Sequence[IRScene],
        output_path: str | Path,
        *,
        tracer: ConversionTracer | None = None,
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
        tracer: ConversionTracer | None = None,
        persist_trace: bool | None = None,
        slide_size_mode: str | None = None,
    ) -> Path:
        """Package pre-rendered slides returned by DrawingMLWriter."""
        if not render_results:
            raise ValueError("At least one render result is required to build a PPTX package.")

        context = PackagingContext()
        slide_assemblies = SlideAssembler(context).assemble(render_results)
        package_writer = PackageWriter(
            base_template=self._base_template,
            content_types_template=self._content_types_template,
            slide_rels_template=self._slide_rels_template,
            slide_size_mode=self._slide_size_mode,
        )
        return package_writer.write_package(
            slide_assemblies,
            output_path,
            tracer=tracer,
            persist_trace=persist_trace,
            slide_size_mode=slide_size_mode,
        )

    def begin_streaming(
        self,
        *,
        tracer: ConversionTracer | None = None,
    ) -> StreamingPackageWriter:
        """Create a streaming writer for incremental slide addition.

        Use as a context manager::

            with builder.begin_streaming() as stream:
                stream.add_slide(result1)
                stream.add_slide(result2)
                path = stream.finalize(output_path)
        """
        return StreamingPackageWriter(
            base_template=self._base_template,
            content_types_template=self._content_types_template,
            slide_rels_template=self._slide_rels_template,
            slide_size_mode=self._slide_size_mode,
            tracer=tracer,
        )


class _PackageWriterBase:
    """Shared infrastructure for PPTX package writers."""

    def __init__(
        self,
        *,
        base_template: Path,
        content_types_template: str,
        slide_rels_template: str,
        slide_size_mode: str | None = None,
    ) -> None:
        self._base_template = base_template
        self._content_types_template = content_types_template
        self._slide_rels_template = slide_rels_template
        self._slide_size_mode = slide_size_mode
        self._tracer: ConversionTracer | None = None

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
            font_data = metadata.get("eot_bytes") or metadata.get("font_data")
            if not isinstance(font_data, (bytes, bytearray)):
                continue
            font_bytes = bytes(font_data)
            digest = hashlib.md5(font_bytes, usedforsecurity=False).hexdigest()
            key = (
                metadata.get("resolved_family") or plan.font_family,
                plan.font_family,
                plan.subset_strategy,
                plan.glyph_count,
                plan.relationship_hint,
                digest,
                metadata.get("font_style_kind"),
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
        font_index = 1

        for plan, metadata, font_bytes in entries:
            font_family = (
                metadata.get("resolved_family")
                or plan.font_family
                or metadata.get("font_family")
                or "EmbeddedFont"
            )
            style_kind = _normalize_style_kind(metadata.get("font_style_kind"))
            style_flags = metadata.get("font_style_flags")
            if not isinstance(style_flags, dict):
                style_flags = {"style_kind": style_kind}
            extension = "fntdata"

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

            filename = f"font{font_index}.{extension}"
            font_index += 1
            while (fonts_dir / filename).exists():
                filename = f"font{font_index}.{extension}"
                font_index += 1
            target_path = fonts_dir / filename
            with target_path.open("wb") as handle:
                handle.write(font_bytes)
            guid_value = metadata.get("font_guid")
            if isinstance(guid_value, uuid.UUID):
                guid_str = str(guid_value)
            elif isinstance(guid_value, str) and guid_value:
                guid_str = guid_value
            else:
                guid_str = None
            self._trace_packaging(
                "font_part_written",
                stage="font",
                metadata={
                    "filename": filename,
                    "relationship_id": rel_id,
                    "font_family": font_family,
                    "style_kind": style_kind,
                    "guid": guid_str,
                },
            )

            packaged_fonts.append(
                _PackagedFont(
                    filename=filename,
                    relationship_id=rel_id,
                    font_family=font_family,
                    subsetted=bool(plan.glyph_count),
                    content_type=_content_type_for_extension(extension),
                    style_kind=style_kind,
                    style_flags=style_flags,
                    guid=guid_str,
                    root_string=metadata.get("font_root_string"),
                    subset_prefix=metadata.get("subset_prefix"),
                    pitch_family=_safe_int(metadata.get("font_pitch_family")),
                    charset=_safe_int(metadata.get("font_charset")),
                )
            )

        return packaged_fonts

    def _update_presentation_parts(
        self,
        package_root: Path,
        slides: Sequence[SlideAssembly],
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

        for entry in slides:
            attrs = {
                "id": str(entry.slide_id),
                f"{{{R_DOC_NS}}}id": entry.rel_id,
            }
            ET.SubElement(slide_list, f"{{{P_NS}}}sldId", attrs)

        if fonts:
            font_list = root.find("p:embeddedFontLst", ns)
            if font_list is None:
                font_list = ET.Element(f"{{{P_NS}}}embeddedFontLst")
                default_text = root.find("p:defaultTextStyle", ns)
                if default_text is not None:
                    root.insert(list(root).index(default_text), font_list)
                else:
                    root.append(font_list)
            else:
                for child in list(font_list):
                    font_list.remove(child)

            font_groups: OrderedDict[str, dict[str, _PackagedFont]] = OrderedDict()
            for font in fonts:
                slot = font_groups.setdefault(font.font_family, {})
                slot[font.style_kind] = font

            for family, style_map in font_groups.items():
                entry_elem = ET.SubElement(font_list, f"{{{P_NS}}}embeddedFont")
                representative = (
                    style_map.get("regular")
                    or style_map.get("bold")
                    or style_map.get("italic")
                    or style_map.get("boldItalic")
                )
                font_attrs = {"typeface": family}
                if representative and representative.pitch_family is not None:
                    font_attrs["pitchFamily"] = str(representative.pitch_family)
                else:
                    font_attrs["pitchFamily"] = "0"
                if representative and representative.charset is not None:
                    font_attrs["charset"] = str(representative.charset)
                else:
                    font_attrs["charset"] = "0"
                ET.SubElement(entry_elem, f"{{{P_NS}}}font", font_attrs)
                for style_kind in FONT_STYLE_ORDER:
                    tagged = style_map.get(style_kind)
                    if tagged is None:
                        continue
                    attrs = {f"{{{R_DOC_NS}}}id": tagged.relationship_id}
                    ET.SubElement(entry_elem, f"{{{P_NS}}}{FONT_STYLE_TAGS[style_kind]}", attrs)

        tree.write(presentation_path, encoding="utf-8", xml_declaration=True)

        rels_path = package_root / "ppt" / "_rels" / "presentation.xml.rels"
        rels_tree = ET.parse(rels_path)
        rels_root = rels_tree.getroot()

        for rel in list(rels_root.findall(f"{{{REL_NS}}}Relationship")):
            if rel.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide":
                rels_root.remove(rel)

        existing_rel_ids = {rel.get("Id") for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")}

        for entry in slides:
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

    def _resolve_slide_size_mode(self, override: str | None) -> str:
        resolved = override or self._slide_size_mode or "multipage"
        if resolved not in ALLOWED_SLIDE_SIZE_MODES:
            raise ValueError(
                f"Unsupported slide_size_mode {resolved!r}. "
                f"Expected one of {sorted(ALLOWED_SLIDE_SIZE_MODES)}."
            )
        return resolved

    def _select_slide_size(
        self,
        slides: Sequence[SlideAssembly],
        *,
        slide_size_mode: str | None,
    ) -> tuple[int, int] | None:
        if not slides:
            return None

        mode = self._resolve_slide_size_mode(slide_size_mode)
        if mode == "same":
            selected = slides[0].slide_size
        else:
            widths = [slide.slide_size[0] for slide in slides]
            heights = [slide.slide_size[1] for slide in slides]
            max_width = max([DEFAULT_SLIDE_SIZE[0], *widths])
            max_height = max([DEFAULT_SLIDE_SIZE[1], *heights])
            selected = (max_width, max_height)

        self._trace_packaging(
            "slide_size_mode_resolved",
            metadata={
                "mode": mode,
                "width_emu": selected[0],
                "height_emu": selected[1],
                "slide_count": len(slides),
            },
        )
        return selected

    def _write_required_presentation_parts(self, package_root: Path) -> None:
        """Write required PPTX parts that PowerPoint expects.

        Per ECMA-376, PowerPoint requires these files to validate properly:
        - presProps.xml: Presentation properties
        - viewProps.xml: View properties
        - tableStyles.xml: Table styles
        """
        ppt_dir = package_root / "ppt"
        ppt_dir.mkdir(parents=True, exist_ok=True)

        # presProps.xml - Minimal presentation properties
        pres_props_content = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>'''

        pres_props_path = ppt_dir / "presProps.xml"
        pres_props_path.write_text(pres_props_content, encoding="utf-8")
        self._trace_packaging(
            "required_part_written",
            metadata={"file": "presProps.xml"},
        )

        # viewProps.xml - View properties with default normal view settings
        view_props_content = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
          xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
    <p:normalViewPr>
        <p:restoredLeft sz="15620"/>
        <p:restoredTop sz="94660"/>
    </p:normalViewPr>
</p:viewPr>'''

        view_props_path = ppt_dir / "viewProps.xml"
        view_props_path.write_text(view_props_content, encoding="utf-8")
        self._trace_packaging(
            "required_part_written",
            metadata={"file": "viewProps.xml"},
        )

        # tableStyles.xml - Table styles with default style reference
        table_styles_content = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
               def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>'''

        table_styles_path = ppt_dir / "tableStyles.xml"
        table_styles_path.write_text(table_styles_content, encoding="utf-8")
        self._trace_packaging(
            "required_part_written",
            metadata={"file": "tableStyles.xml"},
        )

        # Update presentation.xml.rels to include relationships to these files
        rels_path = ppt_dir / "_rels" / "presentation.xml.rels"
        if rels_path.exists():
            rels_tree = ET.parse(rels_path)
            rels_root = rels_tree.getroot()

            existing_rel_ids = {rel.get("Id") for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")}
            existing_targets = {rel.get("Target") for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")}

            # Add presProps relationship if not present
            if "presProps.xml" not in existing_targets:
                # Find next available numeric ID
                next_id = 1
                while f"rId{next_id}" in existing_rel_ids:
                    next_id += 1
                pres_props_rel_id = f"rId{next_id}"

                ET.SubElement(
                    rels_root,
                    f"{{{REL_NS}}}Relationship",
                    {
                        "Id": pres_props_rel_id,
                        "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps",
                        "Target": "presProps.xml",
                    },
                )
                existing_rel_ids.add(pres_props_rel_id)
                existing_targets.add("presProps.xml")

            # Add viewProps relationship if not present
            if "viewProps.xml" not in existing_targets:
                next_id = 1
                while f"rId{next_id}" in existing_rel_ids:
                    next_id += 1
                view_props_rel_id = f"rId{next_id}"

                ET.SubElement(
                    rels_root,
                    f"{{{REL_NS}}}Relationship",
                    {
                        "Id": view_props_rel_id,
                        "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps",
                        "Target": "viewProps.xml",
                    },
                )
                existing_rel_ids.add(view_props_rel_id)
                existing_targets.add("viewProps.xml")

            # Add tableStyles relationship if not present
            if "tableStyles.xml" not in existing_targets:
                next_id = 1
                while f"rId{next_id}" in existing_rel_ids:
                    next_id += 1
                table_styles_rel_id = f"rId{next_id}"

                ET.SubElement(
                    rels_root,
                    f"{{{REL_NS}}}Relationship",
                    {
                        "Id": table_styles_rel_id,
                        "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles",
                        "Target": "tableStyles.xml",
                    },
                )
                existing_rel_ids.add(table_styles_rel_id)
                existing_targets.add("tableStyles.xml")

            # Add theme relationship if not present (CRITICAL for PowerPoint)
            if "theme/theme1.xml" not in existing_targets:
                next_id = 1
                while f"rId{next_id}" in existing_rel_ids:
                    next_id += 1
                theme_rel_id = f"rId{next_id}"

                ET.SubElement(
                    rels_root,
                    f"{{{REL_NS}}}Relationship",
                    {
                        "Id": theme_rel_id,
                        "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme",
                        "Target": "theme/theme1.xml",
                    },
                )

            rels_tree.write(rels_path, encoding="utf-8", xml_declaration=True)
            self._trace_packaging(
                "presentation_rels_updated",
                metadata={"added_required_relationships": True},
            )

    def _write_content_types(
        self,
        package_root: Path,
        slides: Sequence[SlideAssembly],
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

        for entry in slides:
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
            elif default.get("ContentType") != content_type:
                default.set("ContentType", content_type)

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

        # Add required PPTX parts per ECMA-376
        required_parts = [
            ("/ppt/presProps.xml", "application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"),
            ("/ppt/viewProps.xml", "application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"),
            ("/ppt/tableStyles.xml", "application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"),
        ]

        for part_name, content_type in required_parts:
            if part_name not in existing_overrides:
                existing_overrides[part_name] = ET.SubElement(
                    root,
                    f"{{{CONTENT_NS}}}Override",
                    {"PartName": part_name, "ContentType": content_type},
                )

        ET.ElementTree(root).write(content_types_path, encoding="utf-8", xml_declaration=True)

    def _ensure_theme_extension(self, package_root: Path) -> None:
        theme_path = package_root / "ppt" / "theme" / "theme1.xml"
        if not theme_path.exists():
            return
        try:
            tree = ET.parse(theme_path)
            root = tree.getroot()
        except ET.XMLSyntaxError:
            return

        ext_lst = root.find(f"{{{THEME_NS}}}extLst")
        if ext_lst is None:
            ext_lst = ET.SubElement(root, f"{{{THEME_NS}}}extLst")

        target_uri = "{05A4C25C-085E-4340-85A3-A5531E510DB2}"
        existing = [
            ext
            for ext in ext_lst.findall(f"{{{THEME_NS}}}ext")
            if ext.get("uri") == target_uri
        ]
        if existing:
            return

        ext = ET.SubElement(ext_lst, f"{{{THEME_NS}}}ext", uri=target_uri)
        theme_family = ET.SubElement(ext, f"{{{THEME_FAMILY_NS}}}themeFamily")
        theme_family.set("name", "svg2ooxml")
        theme_family.set("id", f"{{{str(uuid.uuid4()).upper()}}}")
        theme_family.set("vid", f"{{{str(uuid.uuid4()).upper()}}}")
        tree.write(theme_path, encoding="utf-8", xml_declaration=True)


class StreamingPackageWriter(_PackageWriterBase):
    """Write PPTX packages one slide at a time with O(1) memory."""

    def __init__(
        self,
        *,
        tracer: ConversionTracer | None = None,
        base_template: Path,
        content_types_template: str,
        slide_rels_template: str,
        slide_size_mode: str | None = None,
    ) -> None:
        super().__init__(
            base_template=base_template,
            content_types_template=content_types_template,
            slide_rels_template=slide_rels_template,
            slide_size_mode=slide_size_mode,
        )
        self._tracer = tracer
        self._temp_path: Path | None = None
        self._temp_dir_ctx: object | None = None
        self._slides_dir: Path | None = None
        self._context: PackagingContext | None = None
        self._assembler: SlideAssembler | None = None
        self._slide_entries: list[_SlideEntry] = []
        self._media_meta: list[_MediaMeta] = []
        self._mask_meta: list[_MaskMeta] = []
        self._font_assets: list[FontAsset] = []
        self._packaged_fonts: list[_PackagedFont] = []
        self._slide_index = 0
        self._begun = False
        self._finalized = False

    def begin(self) -> None:
        """Prepare the temp directory and template for incremental slide addition."""
        if self._begun:
            raise RuntimeError("begin() already called")

        self._context = PackagingContext()
        self._assembler = SlideAssembler(self._context)
        self._temp_dir_ctx = temporary_directory(prefix="svg2ooxml_pptx_")
        self._temp_path = self._temp_dir_ctx.__enter__()
        shutil.copytree(self._base_template, self._temp_path, dirs_exist_ok=True)
        self._ensure_theme_extension(self._temp_path)

        self._slides_dir = self._temp_path / "ppt" / "slides"
        self._slides_dir.mkdir(parents=True, exist_ok=True)
        (self._slides_dir / "_rels").mkdir(exist_ok=True)
        template_rels = self._slides_dir / "_rels" / "slide.xml.rels"
        if template_rels.exists():
            template_rels.unlink()

        self._begun = True
        self._trace_packaging("packaging_start", metadata={"streaming": True})

    def add_slide(self, result: DrawingMLRenderResult) -> None:
        """Assemble one slide, flush XML and media to disk, release the result."""
        if not self._begun:
            raise RuntimeError("begin() must be called before add_slide()")
        if self._finalized:
            raise RuntimeError("Cannot add slides after finalize()")

        self._slide_index += 1
        assembly = self._assembler.assemble_one(result, self._slide_index)

        # Write slide XML to disk
        (self._slides_dir / assembly.filename).write_text(
            assembly.slide_xml, encoding="utf-8"
        )
        self._trace_packaging(
            "slide_xml_written",
            metadata={"filename": assembly.filename, "index": assembly.index},
        )

        # Write slide relationships
        self._write_slide_relationships(
            self._slides_dir,
            assembly.index,
            assembly.media,
            assembly.navigation,
            assembly.masks,
        )

        # Write media binary data to disk immediately
        if assembly.media:
            self._write_media_parts(self._temp_path, assembly.media)
            for part in assembly.media:
                self._media_meta.append(
                    _MediaMeta(filename=part.filename, content_type=part.content_type)
                )

        # Write mask binary data to disk immediately
        if assembly.masks:
            self._write_mask_parts(self._temp_path, assembly.masks)
            for mask in assembly.masks:
                self._mask_meta.append(
                    _MaskMeta(part_name=mask.part_name, content_type=mask.content_type)
                )

        # Accumulate font assets (small, few unique)
        self._font_assets.extend(assembly.font_assets)
        self._packaged_fonts = self._write_font_parts(self._temp_path, self._font_assets)

        # Store lightweight metadata only
        self._slide_entries.append(
            _SlideEntry(
                index=assembly.index,
                filename=assembly.filename,
                rel_id=assembly.rel_id,
                slide_id=assembly.slide_id,
                slide_size=assembly.slide_size,
            )
        )

    def finalize(self, output_path: str | Path) -> Path:
        """Write presentation metadata, content types, and ZIP the package."""
        if not self._begun:
            raise RuntimeError("begin() must be called before finalize()")
        if self._finalized:
            raise RuntimeError("finalize() already called")
        if not self._slide_entries:
            raise ValueError("At least one slide must be added before finalize()")

        self._finalized = True
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        try:
            presentation_slide_size = self._select_slide_size(
                self._slide_entries, slide_size_mode=None
            )

            self._update_presentation_parts(
                self._temp_path,
                self._slide_entries,
                self._packaged_fonts,
                presentation_slide_size,
            )
            self._write_required_presentation_parts(self._temp_path)

            if presentation_slide_size:
                for layout_path in (
                    self._temp_path / "ppt" / "slideLayouts"
                ).glob("slideLayout*.xml"):
                    content = layout_path.read_text(encoding="utf-8")
                    content = content.replace(
                        "{SLIDE_WIDTH}", str(presentation_slide_size[0])
                    )
                    content = content.replace(
                        "{SLIDE_HEIGHT}", str(presentation_slide_size[1])
                    )
                    layout_path.write_text(content, encoding="utf-8")

            self._write_content_types(
                self._temp_path,
                self._slide_entries,
                self._media_meta,
                self._packaged_fonts,
                self._mask_meta,
            )

            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for file_path in self._temp_path.rglob("*"):
                    if file_path.is_file():
                        archive.write(file_path, file_path.relative_to(self._temp_path))

            self._trace_packaging("pptx_written", metadata={"path": str(output)})
            return output
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        if self._temp_dir_ctx is not None:
            self._temp_dir_ctx.__exit__(None, None, None)
            self._temp_dir_ctx = None
            self._temp_path = None

    def __enter__(self) -> StreamingPackageWriter:
        self.begin()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._cleanup()


class PackageWriter(_PackageWriterBase):
    """Write PPTX packages using prepared slide assemblies."""

    def write_package(
        self,
        slides: Sequence[SlideAssembly],
        output_path: str | Path,
        *,
        tracer: ConversionTracer | None = None,
        persist_trace: bool | None = None,
        slide_size_mode: str | None = None,
    ) -> Path:
        """Package prepared slide assemblies into a PPTX file."""
        prev_tracer = self._tracer
        self._tracer = tracer
        should_persist_trace = (tracer is not None) if persist_trace is None else (bool(persist_trace) and tracer is not None)

        if not slides:
            raise ValueError("At least one slide assembly is required to build a PPTX package.")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        try:
            with temporary_directory(prefix="svg2ooxml_pptx_") as temp_path:
                shutil.copytree(self._base_template, temp_path, dirs_exist_ok=True)
                self._ensure_theme_extension(temp_path)
                self._trace_packaging(
                    "packaging_start",
                    metadata={"slide_count": len(slides)},
                )

                slides_dir = temp_path / "ppt" / "slides"
                slides_dir.mkdir(parents=True, exist_ok=True)
                (slides_dir / "_rels").mkdir(exist_ok=True)
                # The clean-slate template ships a placeholder `slide.xml.rels` that references
                # the stock layout. Delete it so the package only contains the slides we emit.
                template_slide_rels = slides_dir / "_rels" / "slide.xml.rels"
                if template_slide_rels.exists():
                    template_slide_rels.unlink()

                all_media: list[_PackagedMedia] = []
                font_assets: list[FontAsset] = []
                all_masks: list[_MaskAsset] = []
                packaged_fonts: list[_PackagedFont] = []

                for slide in slides:
                    (slides_dir / slide.filename).write_text(slide.slide_xml, encoding="utf-8")
                    self._trace_packaging(
                        "slide_xml_written",
                        metadata={"filename": slide.filename, "index": slide.index},
                    )

                    for part in slide.media:
                        self._trace_packaging(
                            "media_enqueued",
                            metadata={
                                "relationship_id": part.relationship_id,
                                "filename": part.filename,
                                "content_type": part.content_type,
                            },
                        )

                    for mask in slide.masks:
                        self._trace_packaging(
                            "mask_enqueued",
                            metadata={
                                "relationship_id": mask.relationship_id,
                                "part_name": mask.part_name,
                            },
                        )

                    self._write_slide_relationships(
                        slides_dir,
                        slide.index,
                        slide.media,
                        slide.navigation,
                        slide.masks,
                    )
                    self._trace_packaging(
                        "slide_relationships_updated",
                        metadata={"index": slide.index, "media_count": len(slide.media), "mask_count": len(slide.masks)},
                    )

                    all_media.extend(slide.media)
                    font_assets.extend(slide.font_assets)
                    all_masks.extend(slide.masks)

                    self._write_media_parts(temp_path, all_media)
                    self._write_mask_parts(temp_path, all_masks)
                    packaged_fonts = self._write_font_parts(temp_path, font_assets)

                presentation_slide_size = self._select_slide_size(
                    slides,
                    slide_size_mode=slide_size_mode,
                )

                self._update_presentation_parts(temp_path, slides, packaged_fonts, presentation_slide_size)
                self._write_required_presentation_parts(temp_path)

                # Inject dimensions into slide layouts
                if presentation_slide_size:
                    for layout_path in (temp_path / "ppt" / "slideLayouts").glob("slideLayout*.xml"):
                        content = layout_path.read_text(encoding="utf-8")
                        content = content.replace("{SLIDE_WIDTH}", str(presentation_slide_size[0]))
                        content = content.replace("{SLIDE_HEIGHT}", str(presentation_slide_size[1]))
                        layout_path.write_text(content, encoding="utf-8")

                self._write_content_types(temp_path, slides, all_media, packaged_fonts, all_masks)
                self._trace_packaging(
                    "content_types_updated",
                    metadata={
                        "slide_count": len(slides),
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


def write_pptx(scene: IRScene, output_path: str | Path) -> Path:
    """Public helper mirroring the historical API."""

    builder = PPTXPackageBuilder()
    return builder.build(scene, output_path)


def _content_type_for_extension(extension: str) -> str:
    """Get OOXML-compliant content type for font file extensions.

    Per ECMA-376 and Office Open XML specification:
    - TTF/OTF fonts should use 'application/x-fontdata'
    - Obfuscated fonts use the dedicated OOXML type
    - Web fonts (WOFF/WOFF2) use standard MIME types
    """
    mapping = {
        "ttf": "application/x-fontdata",  # PowerPoint-compliant (was x-font-ttf)
        "otf": "application/x-fontdata",  # PowerPoint-compliant (was x-font-otf)
        "woff": "application/font-woff",
        "woff2": "application/font-woff2",
        "odttf": "application/vnd.openxmlformats-officedocument.obfuscatedFont",
        "fntdata": "application/x-fontdata",
    }
    return mapping.get(extension.lower(), "application/octet-stream")


def _normalize_style_kind(value: object) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "bolditalic":
            return "boldItalic"
        if lowered in FONT_STYLE_TAGS:
            return lowered
    return "regular"


def _safe_int(value: object | None) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return None
    return None


__all__ = ["PPTXPackageBuilder", "write_pptx"]
