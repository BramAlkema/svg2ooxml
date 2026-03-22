"""PPTX packaging helpers built on top of the DrawingML writer."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
import zipfile
from collections import OrderedDict
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree as ET

from svg2ooxml.common.tempfiles import temporary_directory
from svg2ooxml.drawingml.assets import FontAsset, NavigationAsset
from svg2ooxml.drawingml.writer import DEFAULT_SLIDE_SIZE
from svg2ooxml.io.pptx_assembly import (
    ALLOWED_SLIDE_SIZE_MODES,
    CONTENT_NS,
    FONT_STYLE_ORDER,
    FONT_STYLE_TAGS,
    MASK_REL_TYPE,
    P_NS,
    PackagingContext,
    R_DOC_NS,
    REL_NS,
    SlideAssembler,
    SlideAssembly,
    THEME_FAMILY_NS,
    THEME_NS,
    MaskAsset,
    MaskMeta,
    MediaMeta,
    PackagedFont,
    PackagedMedia,
    SlideEntry,
    content_type_for_extension as _content_type_for_extension,
    normalize_style_kind as _normalize_style_kind,
    safe_int as _safe_int,
)
from svg2ooxml.ir.text import EmbeddedFontPlan

if TYPE_CHECKING:  # pragma: no cover - typing only
    from svg2ooxml.core.tracing import ConversionTracer


_REQUIRED_XML_PARTS: dict[str, str] = {
    "presProps.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"\n'
        '                  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"\n'
        '                  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>'
    ),
    "viewProps.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"\n'
        '          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"\n'
        '          xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">\n'
        '    <p:normalViewPr>\n'
        '        <p:restoredLeft sz="15620"/>\n'
        '        <p:restoredTop sz="94660"/>\n'
        '    </p:normalViewPr>\n'
        '</p:viewPr>'
    ),
    "tableStyles.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"\n'
        '               def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>'
    ),
}

_REQUIRED_PRES_RELS: tuple[tuple[str, str], ...] = (
    ("presProps.xml", f"{R_DOC_NS}/presProps"),
    ("viewProps.xml", f"{R_DOC_NS}/viewProps"),
    ("tableStyles.xml", f"{R_DOC_NS}/tableStyles"),
    ("theme/theme1.xml", f"{R_DOC_NS}/theme"),
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

    def _write_media_parts(self, package_root: Path, media_parts: Sequence[PackagedMedia]) -> None:
        if not media_parts:
            return
        media_dir = package_root / "ppt" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        unique_media: dict[str, PackagedMedia] = {}
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

    def _write_mask_parts(self, package_root: Path, mask_parts: Sequence[MaskAsset]) -> None:
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
        media_parts: Sequence[PackagedMedia],
        navigation_assets: Sequence[NavigationAsset],
        mask_parts: Sequence[MaskAsset],
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
                    "Type": MASK_REL_TYPE,
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
    ) -> list[PackagedFont]:
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

        packaged_fonts: list[PackagedFont] = []
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
                PackagedFont(
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
        fonts: Sequence[PackagedFont],
        slide_size: tuple[int, int] | None = None,
    ) -> None:
        presentation_path = package_root / "ppt" / "presentation.xml"
        tree = ET.parse(presentation_path)
        root = tree.getroot()
        ns = {"p": P_NS, "r": R_DOC_NS}

        # Update slide dimensions if provided
        # ECMA-376: sldSz cx/cy minimum is 914400 EMU (1 inch)
        _MIN_SLIDE_EMU = 914400
        if slide_size is not None:
            slide_sz = root.find("p:sldSz", ns)
            if slide_sz is not None:
                cx = max(slide_size[0], _MIN_SLIDE_EMU)
                cy = max(slide_size[1], _MIN_SLIDE_EMU)
                slide_sz.set("cx", str(cx))
                slide_sz.set("cy", str(cy))
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

            font_groups: OrderedDict[str, dict[str, PackagedFont]] = OrderedDict()
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
            if rel.get("Type") == f"{R_DOC_NS}/slide":
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
                    "Type": f"{R_DOC_NS}/slide",
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
                    "Type": f"{R_DOC_NS}/font",
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

    def _inject_slide_layout_dimensions(
        self, package_root: Path, slide_size: tuple[int, int] | None
    ) -> None:
        """Replace dimension placeholders in slide layout templates."""
        if slide_size is None:
            return
        for layout_path in (package_root / "ppt" / "slideLayouts").glob("slideLayout*.xml"):
            content = layout_path.read_text(encoding="utf-8")
            content = content.replace("{SLIDE_WIDTH}", str(slide_size[0]))
            content = content.replace("{SLIDE_HEIGHT}", str(slide_size[1]))
            layout_path.write_text(content, encoding="utf-8")

    def _write_required_presentation_parts(self, package_root: Path) -> None:
        """Write presProps, viewProps, tableStyles parts required by ECMA-376."""
        ppt_dir = package_root / "ppt"
        ppt_dir.mkdir(parents=True, exist_ok=True)

        for name, content in _REQUIRED_XML_PARTS.items():
            (ppt_dir / name).write_text(content, encoding="utf-8")
            self._trace_packaging("required_part_written", metadata={"file": name})

        rels_path = ppt_dir / "_rels" / "presentation.xml.rels"
        if not rels_path.exists():
            return
        rels_tree = ET.parse(rels_path)
        rels_root = rels_tree.getroot()
        existing_rel_ids = {rel.get("Id") for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")}
        existing_targets = {rel.get("Target") for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")}

        for target, rel_type in _REQUIRED_PRES_RELS:
            if target in existing_targets:
                continue
            next_id = 1
            while f"rId{next_id}" in existing_rel_ids:
                next_id += 1
            rel_id = f"rId{next_id}"
            ET.SubElement(
                rels_root, f"{{{REL_NS}}}Relationship",
                {"Id": rel_id, "Type": rel_type, "Target": target},
            )
            existing_rel_ids.add(rel_id)
            existing_targets.add(target)

        rels_tree.write(rels_path, encoding="utf-8", xml_declaration=True)
        self._trace_packaging(
            "presentation_rels_updated",
            metadata={"added_required_relationships": True},
        )

    def _write_content_types(
        self,
        package_root: Path,
        slides: Sequence[SlideAssembly],
        media_parts: Sequence[PackagedMedia],
        fonts: Sequence[PackagedFont],
        mask_parts: Sequence[MaskAsset],
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
        self._slide_entries: list[SlideEntry] = []
        self._media_meta: list[MediaMeta] = []
        self._mask_meta: list[MaskMeta] = []
        self._font_assets: list[FontAsset] = []
        self._packaged_fonts: list[PackagedFont] = []
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
                    MediaMeta(filename=part.filename, content_type=part.content_type)
                )

        # Write mask binary data to disk immediately
        if assembly.masks:
            self._write_mask_parts(self._temp_path, assembly.masks)
            for mask in assembly.masks:
                self._mask_meta.append(
                    MaskMeta(part_name=mask.part_name, content_type=mask.content_type)
                )

        # Accumulate font assets (small, few unique)
        self._font_assets.extend(assembly.font_assets)
        self._packaged_fonts = self._write_font_parts(self._temp_path, self._font_assets)

        # Store lightweight metadata only
        self._slide_entries.append(
            SlideEntry(
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

            self._inject_slide_layout_dimensions(self._temp_path, presentation_slide_size)

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

                all_media: list[PackagedMedia] = []
                font_assets: list[FontAsset] = []
                all_masks: list[MaskAsset] = []
                packaged_fonts: list[PackagedFont] = []

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

                self._inject_slide_layout_dimensions(temp_path, presentation_slide_size)

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


__all__ = ["PackageWriter", "StreamingPackageWriter"]
