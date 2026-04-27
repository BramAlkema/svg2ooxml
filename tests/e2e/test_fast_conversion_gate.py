"""Fast end-to-end SVG to PPTX conversion gate."""

from __future__ import annotations

import posixpath
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from lxml import etree as ET

from svg2ooxml.core.pptx_exporter import SvgPageSource, SvgToPptxExporter

R_DOC_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB"
    "/6X8XcQAAAAASUVORK5CYII="
)

pytestmark = pytest.mark.e2e


@dataclass(frozen=True)
class E2ECase:
    name: str
    svg: str
    expected_text: tuple[str, ...] = ()
    assertions: tuple[Callable[[ET._Element, dict[str, str], set[str]], None], ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class PptxPackageSnapshot:
    xml_parts: dict[str, str]
    package_names: set[str]

    def __getitem__(self, name: str) -> str:
        return self.xml_parts[name]


def test_curated_svg_cases_convert_to_consistent_pptx(tmp_path: Path, case: E2ECase) -> None:
    exporter = SvgToPptxExporter(filter_strategy="resvg", geometry_mode="resvg-only")
    output_path = tmp_path / f"{case.name}.pptx"

    result = exporter.convert_string(case.svg, output_path, source_path=f"{case.name}.svg")

    assert result.slide_count == 1
    assert result.trace_report is not None
    package = _assert_pptx_package_is_self_consistent(output_path, expected_slides=1)
    slide_root = _parse_xml(package["ppt/slides/slide1.xml"])
    slide_xml = package["ppt/slides/slide1.xml"]
    rel_targets = _slide_relationship_targets(package.xml_parts, 1)

    for text in case.expected_text:
        assert text in slide_xml
    for assertion in case.assertions:
        assertion(slide_root, rel_targets, package.package_names)


def test_project_bee_asset_converts_to_animation_pptx(tmp_path: Path) -> None:
    source_path = Path("assets/bee-flying-svg.svg")
    exporter = SvgToPptxExporter(filter_strategy="resvg", geometry_mode="resvg-only")
    output_path = tmp_path / "bee.pptx"

    result = exporter.convert_file(source_path, output_path)

    assert result.slide_count == 1
    package = _assert_pptx_package_is_self_consistent(output_path, expected_slides=1)
    slide_root = _parse_xml(package["ppt/slides/slide1.xml"])
    assert slide_root.find(".//p:timing", namespaces=_NS) is not None


def test_multi_slide_conversion_keeps_slide_relationships_consistent(tmp_path: Path) -> None:
    exporter = SvgToPptxExporter(filter_strategy="resvg", geometry_mode="resvg-only")
    output_path = tmp_path / "multi.pptx"
    pages = [
        SvgPageSource(svg_text=_BASIC_SHAPES_TEXT, title="Basic", name="basic"),
        SvgPageSource(svg_text=_DATA_URI_IMAGE, title="Image", name="image"),
        SvgPageSource(svg_text=_ANIMATED_MIXED_GROUP, title="Animated", name="animated"),
    ]

    result = exporter.convert_pages(pages, output_path)

    assert result.slide_count == len(pages)
    package = _assert_pptx_package_is_self_consistent(output_path, expected_slides=len(pages))
    presentation = _parse_xml(package["ppt/presentation.xml"])
    slide_ids = presentation.findall(".//p:sldId", namespaces=_NS)
    assert len(slide_ids) == len(pages)
    assert "E2E BASIC" in package["ppt/slides/slide1.xml"]
    assert "<p:timing" in package["ppt/slides/slide3.xml"]


def _assert_has_media_relationship(
    _slide_root: ET._Element,
    rel_targets: dict[str, str],
    package_names: set[str],
) -> None:
    media_targets = [target for target in rel_targets.values() if target.startswith("ppt/media/")]
    assert media_targets, "expected at least one slide media relationship"
    assert all(target in package_names for target in media_targets)


def _assert_has_timing(
    slide_root: ET._Element,
    _rel_targets: dict[str, str],
    _package_names: set[str],
) -> None:
    assert slide_root.find(".//p:timing", namespaces=_NS) is not None


def _assert_has_shapes_or_pictures(
    slide_root: ET._Element,
    _rel_targets: dict[str, str],
    _package_names: set[str],
) -> None:
    shapes = slide_root.findall(".//p:sp", namespaces=_NS)
    pictures = slide_root.findall(".//p:pic", namespaces=_NS)
    assert shapes or pictures, "expected rendered DrawingML shapes or pictures"


def _assert_has_gradient_or_raster_fallback(
    slide_root: ET._Element,
    rel_targets: dict[str, str],
    _package_names: set[str],
) -> None:
    gradients = slide_root.findall(".//a:gradFill", namespaces=_NS)
    media_targets = [target for target in rel_targets.values() if target.startswith("ppt/media/")]
    assert gradients or media_targets, "expected native gradient fill or raster fallback"


def _assert_pptx_package_is_self_consistent(
    pptx_path: Path,
    *,
    expected_slides: int,
) -> PptxPackageSnapshot:
    assert pptx_path.exists()
    with zipfile.ZipFile(pptx_path, "r") as archive:
        package_names = set(archive.namelist())
        required = {
            "[Content_Types].xml",
            "_rels/.rels",
            "ppt/presentation.xml",
            "ppt/_rels/presentation.xml.rels",
            "ppt/slideMasters/slideMaster1.xml",
            "ppt/slideLayouts/slideLayout1.xml",
            "ppt/theme/theme1.xml",
            *{f"ppt/slides/slide{index}.xml" for index in range(1, expected_slides + 1)},
            *{f"ppt/slides/_rels/slide{index}.xml.rels" for index in range(1, expected_slides + 1)},
        }
        missing = required - package_names
        assert not missing, f"missing required PPTX parts: {sorted(missing)}"

        package = {
            name: archive.read(name).decode("utf-8")
            for name in package_names
            if name.endswith((".xml", ".rels"))
        }

    for name, xml in package.items():
        _parse_xml(xml, label=name)

    for rels_name, rels_xml in package.items():
        if rels_name.endswith(".rels"):
            _assert_relationship_targets_exist(rels_name, rels_xml, package_names)

    for index in range(1, expected_slides + 1):
        _assert_slide_relationship_references_are_resolved(package, index)

    return PptxPackageSnapshot(xml_parts=package, package_names=package_names)


def _assert_slide_relationship_references_are_resolved(
    package: dict[str, str],
    slide_index: int,
) -> None:
    slide_name = f"ppt/slides/slide{slide_index}.xml"
    slide_root = _parse_xml(package[slide_name], label=slide_name)
    rel_ids = set(_slide_relationship_targets(package, slide_index))
    referenced_ids = _relationship_ids_used_by_xml(slide_root)
    missing = referenced_ids - rel_ids
    assert not missing, f"{slide_name} references missing relationships: {sorted(missing)}"


def _slide_relationship_targets(package: dict[str, str], slide_index: int) -> dict[str, str]:
    rels_name = f"ppt/slides/_rels/slide{slide_index}.xml.rels"
    rels_root = _parse_xml(package[rels_name], label=rels_name)
    targets: dict[str, str] = {}
    for rel in rels_root.findall(f"{{{REL_NS}}}Relationship"):
        rel_id = rel.get("Id")
        target = rel.get("Target")
        if not rel_id or not target or rel.get("TargetMode") == "External":
            continue
        targets[rel_id] = _resolve_relationship_target(rels_name, target)
    return targets


def _assert_relationship_targets_exist(
    rels_name: str,
    rels_xml: str,
    package_names: set[str],
) -> None:
    rels_root = _parse_xml(rels_xml, label=rels_name)
    missing: list[str] = []
    for rel in rels_root.findall(f"{{{REL_NS}}}Relationship"):
        target = rel.get("Target")
        if not target or rel.get("TargetMode") == "External":
            continue
        resolved = _resolve_relationship_target(rels_name, target)
        if resolved not in package_names:
            missing.append(f"{rel.get('Id')} -> {resolved}")
    assert not missing, f"{rels_name} points at missing package parts: {missing}"


def _resolve_relationship_target(rels_name: str, target: str) -> str:
    clean_target = target.split("#", 1)[0]
    if clean_target.startswith("/"):
        resolved = posixpath.normpath(clean_target.lstrip("/"))
    else:
        resolved = posixpath.normpath(
            posixpath.join(_relationship_source_dir(rels_name), clean_target)
        )
    assert not resolved.startswith("../"), f"relationship escapes package root: {target!r}"
    return resolved


def _relationship_source_dir(rels_name: str) -> str:
    if rels_name == "_rels/.rels":
        return "."
    marker = "/_rels/"
    assert marker in rels_name, f"unexpected relationship part name: {rels_name}"
    source_dir, rel_file = rels_name.split(marker, 1)
    assert rel_file.endswith(".rels"), f"unexpected relationship file: {rels_name}"
    source_name = rel_file[:-5]
    return source_dir if source_name else "."


def _relationship_ids_used_by_xml(root: ET._Element) -> set[str]:
    return {
        value
        for element in root.iter()
        for attr_name, value in element.attrib.items()
        if attr_name.startswith(f"{{{R_DOC_NS}}}") and value
    }


def _parse_xml(xml: str, *, label: str = "xml") -> ET._Element:
    parser = ET.XMLParser(resolve_entities=False, no_network=True)
    try:
        return ET.fromstring(xml.encode("utf-8"), parser)
    except ET.XMLSyntaxError as exc:  # pragma: no cover - assertion helper
        raise AssertionError(f"{label} is not well-formed XML: {exc}") from exc


_NS = {
    "a": A_NS,
    "p": P_NS,
    "r": R_DOC_NS,
}

_BASIC_SHAPES_TEXT = """
<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90" viewBox="0 0 160 90">
  <rect id="bg" x="0" y="0" width="160" height="90" fill="#336699"/>
  <circle id="dot" cx="130" cy="22" r="14" fill="rgb(255 180 0 / 80%)"/>
  <path id="zig" d="M 10 20 L 50 35 L 90 18" fill="none" stroke="#FFFFFF" stroke-width="4"/>
  <text id="label" x="12" y="76" font-family="Arial" font-size="16" fill="#ffffff">E2E BASIC</text>
</svg>
""".strip()

_GRADIENT_PATTERN_TRANSFORMS = """
<svg xmlns="http://www.w3.org/2000/svg" width="180" height="100" viewBox="0 0 180 100">
  <defs>
    <linearGradient id="grad" gradientUnits="userSpaceOnUse"
                    x1="0" y1="0" x2="160" y2="0"
                    gradientTransform="translate(8 0) scale(0.9 1)">
      <stop offset="0" stop-color="#ff0040"/>
      <stop offset="0.5" stop-color="rgb(0 180 255 / 75%)"/>
      <stop offset="1" stop-color="#ffe000"/>
    </linearGradient>
    <pattern id="tile" x="0" y="0" width="16" height="16"
             patternUnits="userSpaceOnUse"
             patternTransform="translate(2 3) rotate(15)">
      <rect width="16" height="16" fill="#f8f8f8"/>
      <path d="M 0 16 L 16 0" stroke="#223344" stroke-width="2"/>
    </pattern>
  </defs>
  <rect x="8" y="8" width="164" height="38" fill="url(#grad)"/>
  <rect x="8" y="56" width="164" height="36" fill="url(#tile)" stroke="#111111"/>
</svg>
""".strip()

_CLIP_MASK_FILTER = """
<svg xmlns="http://www.w3.org/2000/svg" width="160" height="110" viewBox="0 0 160 110">
  <defs>
    <clipPath id="clip">
      <circle cx="80" cy="54" r="44"/>
    </clipPath>
    <linearGradient id="fade" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="160" y2="0">
      <stop offset="0" stop-color="white"/>
      <stop offset="1" stop-color="black"/>
    </linearGradient>
    <mask id="mask" maskUnits="userSpaceOnUse" x="0" y="0" width="160" height="110">
      <rect width="160" height="110" fill="url(#fade)"/>
    </mask>
    <filter id="soft" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="2"/>
    </filter>
  </defs>
  <g clip-path="url(#clip)" filter="url(#soft)">
    <rect width="160" height="110" fill="#12805c" mask="url(#mask)"/>
    <circle cx="104" cy="42" r="26" fill="#f4d35e"/>
  </g>
</svg>
""".strip()

_DATA_URI_IMAGE = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="80" height="60" viewBox="0 0 80 60">
  <rect width="80" height="60" fill="#ffffff"/>
  <image id="pixel" href="data:image/png;base64,{PNG_1X1}" x="10" y="10" width="40" height="40"/>
</svg>
""".strip()

_ANIMATED_MIXED_GROUP = """
<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80" viewBox="0 0 120 80">
  <g id="body">
    <animateTransform attributeName="transform" type="translate"
                      values="0 0;30 0" dur="1s" begin="0s"/>
    <rect id="child" x="20" y="20" width="35" height="25" fill="#223344">
      <animate attributeName="fill" values="#223344;#ff6600;#223344" dur="1s" begin="0s"/>
    </rect>
  </g>
  <circle id="spinner" cx="84" cy="34" r="10" fill="#77aa33">
    <animateTransform attributeName="transform" type="rotate"
                      values="0 84 34;360 84 34" dur="1s" begin="0s"/>
  </circle>
</svg>
""".strip()

_CASES = (
    E2ECase(
        name="basic_shapes_text",
        svg=_BASIC_SHAPES_TEXT,
        expected_text=("336699", "E2E BASIC"),
        assertions=(_assert_has_shapes_or_pictures,),
    ),
    E2ECase(
        name="gradient_pattern_transforms",
        svg=_GRADIENT_PATTERN_TRANSFORMS,
        assertions=(_assert_has_shapes_or_pictures, _assert_has_gradient_or_raster_fallback),
    ),
    E2ECase(
        name="clip_mask_filter",
        svg=_CLIP_MASK_FILTER,
        assertions=(_assert_has_shapes_or_pictures,),
    ),
    E2ECase(
        name="data_uri_image",
        svg=_DATA_URI_IMAGE,
        assertions=(_assert_has_shapes_or_pictures, _assert_has_media_relationship),
    ),
    E2ECase(
        name="animated_mixed_group",
        svg=_ANIMATED_MIXED_GROUP,
        assertions=(_assert_has_shapes_or_pictures, _assert_has_timing),
    ),
)


@pytest.fixture(params=_CASES, ids=lambda case: case.name)
def case(request: pytest.FixtureRequest) -> E2ECase:
    return request.param
