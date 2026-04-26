"""Low-level PPTX package part writers."""

from __future__ import annotations

import uuid
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

from lxml import etree as ET

from svg2ooxml.common.boundaries import next_relationship_id
from svg2ooxml.io.pptx_assembly import (
    CONTENT_NS,
    R_DOC_NS,
    REL_NS,
    THEME_FAMILY_NS,
    THEME_NS,
    MaskAsset,
    MaskMeta,
    MediaMeta,
    PackagedFont,
    PackagedMedia,
    SlideAssembly,
    SlideEntry,
)

TracePackaging = Callable[..., None]

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


def inject_slide_layout_dimensions(
    package_root: Path,
    slide_size: tuple[int, int] | None,
) -> None:
    """Replace dimension placeholders in slide layout templates."""

    if slide_size is None:
        return
    for layout_path in (package_root / "ppt" / "slideLayouts").glob("slideLayout*.xml"):
        content = layout_path.read_text(encoding="utf-8")
        content = content.replace("{SLIDE_WIDTH}", str(slide_size[0]))
        content = content.replace("{SLIDE_HEIGHT}", str(slide_size[1]))
        layout_path.write_text(content, encoding="utf-8")


def write_required_presentation_parts(
    package_root: Path,
    *,
    trace_packaging: TracePackaging | None = None,
) -> None:
    """Write presentation support parts required by ECMA-376."""

    ppt_dir = package_root / "ppt"
    ppt_dir.mkdir(parents=True, exist_ok=True)

    for name, content in _REQUIRED_XML_PARTS.items():
        (ppt_dir / name).write_text(content, encoding="utf-8")
        if trace_packaging is not None:
            trace_packaging("required_part_written", metadata={"file": name})

    rels_path = ppt_dir / "_rels" / "presentation.xml.rels"
    if not rels_path.exists():
        return

    rels_tree = ET.parse(rels_path)
    rels_root = rels_tree.getroot()
    existing_rel_ids = {
        rel.get("Id") for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")
    }
    existing_targets = {
        rel.get("Target") for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")
    }

    for target, rel_type in _REQUIRED_PRES_RELS:
        if target in existing_targets:
            continue
        rel_id = next_relationship_id(existing_rel_ids)
        ET.SubElement(
            rels_root,
            f"{{{REL_NS}}}Relationship",
            {"Id": rel_id, "Type": rel_type, "Target": target},
        )
        existing_rel_ids.add(rel_id)
        existing_targets.add(target)

    rels_tree.write(rels_path, encoding="utf-8", xml_declaration=True)
    if trace_packaging is not None:
        trace_packaging(
            "presentation_rels_updated",
            metadata={"added_required_relationships": True},
        )


def write_content_types(
    content_types_template: str,
    package_root: Path,
    slides: Sequence[SlideAssembly | SlideEntry],
    media_parts: Sequence[PackagedMedia | MediaMeta],
    fonts: Sequence[PackagedFont],
    mask_parts: Sequence[MaskAsset | MaskMeta],
) -> None:
    content_types_path = package_root / "[Content_Types].xml"
    root = ET.fromstring(content_types_template.encode("utf-8"))

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

    required_parts = (
        (
            "/ppt/presProps.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.presProps+xml",
        ),
        (
            "/ppt/viewProps.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml",
        ),
        (
            "/ppt/tableStyles.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml",
        ),
    )
    for part_name, content_type in required_parts:
        if part_name not in existing_overrides:
            existing_overrides[part_name] = ET.SubElement(
                root,
                f"{{{CONTENT_NS}}}Override",
                {"PartName": part_name, "ContentType": content_type},
            )

    ET.ElementTree(root).write(content_types_path, encoding="utf-8", xml_declaration=True)


def ensure_theme_extension(package_root: Path) -> None:
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


def zip_package(package_root: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in package_root.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(package_root))


__all__ = [
    "ensure_theme_extension",
    "inject_slide_layout_dimensions",
    "write_content_types",
    "write_required_presentation_parts",
    "zip_package",
]
