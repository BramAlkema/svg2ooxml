"""Structural comparison helpers for source SVG IR vs generated PPTX slide XML."""

from __future__ import annotations

import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from lxml import etree as ET

from svg2ooxml.core.parser import ParserConfig, SVGParser
from svg2ooxml.ir.entrypoints import convert_parser_output
from svg2ooxml.ir.scene import Group
from svg2ooxml.ir.shapes import Rectangle
from svg2ooxml.ir.text import TextFrame
from svg2ooxml.services import configure_services

EMU_PER_PX = 9525.0
PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"p": PRESENTATION_NS, "a": DRAWING_NS}


@dataclass(frozen=True)
class SourceLeaf:
    kind: str
    element_id: str | None
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class SlideLeaf:
    shape_tag: str
    shape_id: str | None
    shape_name: str | None
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class _SlideTransform:
    scale_x: float = 1.0
    scale_y: float = 1.0
    translate_x: float = 0.0
    translate_y: float = 0.0

    def apply_bbox(
        self,
        bbox: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float]:
        x, y, width, height = bbox
        return (
            x * self.scale_x + self.translate_x,
            y * self.scale_y + self.translate_y,
            width * self.scale_x,
            height * self.scale_y,
        )

    def with_group_xfrm(self, xfrm: ET._Element | None) -> _SlideTransform:
        if xfrm is None:
            return self

        off_x, off_y = _point_from_xfrm(xfrm, "off")
        ext_w, ext_h = _point_from_xfrm(xfrm, "ext")
        ch_off_x, ch_off_y = _point_from_xfrm(xfrm, "chOff")
        ch_ext_w, ch_ext_h = _point_from_xfrm(xfrm, "chExt")

        group_scale_x = ext_w / ch_ext_w if ch_ext_w else 1.0
        group_scale_y = ext_h / ch_ext_h if ch_ext_h else 1.0
        return _SlideTransform(
            scale_x=self.scale_x * group_scale_x,
            scale_y=self.scale_y * group_scale_y,
            translate_x=self.translate_x
            + self.scale_x * (off_x - ch_off_x * group_scale_x),
            translate_y=self.translate_y
            + self.scale_y * (off_y - ch_off_y * group_scale_y),
        )


@dataclass(frozen=True)
class SubstructurePair:
    source: SourceLeaf
    target: SlideLeaf
    geometry_decision: str | None
    dx: float
    dy: float
    dw: float
    dh: float
    max_abs_delta: float

    @property
    def is_rasterized(self) -> bool:
        return self.target.shape_tag == "pic" or self.geometry_decision in {
            "bitmap",
            "raster",
        }


@dataclass(frozen=True)
class SubstructureComparison:
    source_count: int
    target_count: int
    source_kind_totals: dict[str, int]
    target_kind_totals: dict[str, int]
    geometry_decision_totals: dict[str, int]
    pairs: tuple[SubstructurePair, ...]

    @property
    def matched_count(self) -> int:
        return len(self.pairs)

    @property
    def count_delta(self) -> int:
        return self.target_count - self.source_count

    def rasterized_pairs(self) -> tuple[SubstructurePair, ...]:
        return tuple(pair for pair in self.pairs if pair.is_rasterized)

    def top_bbox_mismatches(self, *, limit: int = 12) -> tuple[SubstructurePair, ...]:
        ordered = sorted(self.pairs, key=lambda pair: pair.max_abs_delta, reverse=True)
        return tuple(ordered[: max(limit, 0)])


def compare_substructures(
    svg_text: str,
    pptx_path: Path | str,
    *,
    source_path: Path | None = None,
    filter_strategy: str | None = "resvg",
    geometry_mode: str | None = "resvg",
    trace_report: dict[str, object] | None = None,
) -> SubstructureComparison:
    """Compare source IR leaves against generated PPTX slide leaves in render order."""

    parser = SVGParser(ParserConfig())
    parse_result = parser.parse(
        svg_text,
        source_path=str(source_path) if source_path is not None else None,
    )
    if not parse_result.success or parse_result.svg_root is None:
        raise ValueError(f"SVG parsing failed: {parse_result.error_message}")

    services = parse_result.services
    if services is None:
        services = configure_services(
            filter_strategy=filter_strategy,
            geometry_mode=geometry_mode,
        )
    else:
        if filter_strategy and services.filter_service is not None:
            services.filter_service.set_strategy(filter_strategy)
        policy_context = getattr(services, "policy_context", None)
        if policy_context and geometry_mode:
            geometry_policy = policy_context.get("geometry", {})
            if isinstance(geometry_policy, dict):
                geometry_policy["geometry_mode"] = geometry_mode

    scene = convert_parser_output(parse_result, services=services)
    source_leaves = tuple(
        _flatten_scene_leaves(scene.elements, source_path=source_path)
    )
    slide_leaves = tuple(_load_slide_leaves(Path(pptx_path)))
    geometry_decisions = _geometry_decisions_by_element(trace_report)

    pairs: list[SubstructurePair] = []
    for source, target in zip(source_leaves, slide_leaves, strict=False):
        dx = target.bbox[0] - source.bbox[0]
        dy = target.bbox[1] - source.bbox[1]
        dw = target.bbox[2] - source.bbox[2]
        dh = target.bbox[3] - source.bbox[3]
        pairs.append(
            SubstructurePair(
                source=source,
                target=target,
                geometry_decision=geometry_decisions.get(source.element_id),
                dx=dx,
                dy=dy,
                dw=dw,
                dh=dh,
                max_abs_delta=max(abs(dx), abs(dy), abs(dw), abs(dh)),
            )
        )

    return SubstructureComparison(
        source_count=len(source_leaves),
        target_count=len(slide_leaves),
        source_kind_totals=dict(Counter(leaf.kind for leaf in source_leaves)),
        target_kind_totals=dict(Counter(leaf.shape_tag for leaf in slide_leaves)),
        geometry_decision_totals=dict(Counter(geometry_decisions.values())),
        pairs=tuple(pairs),
    )


def _flatten_scene_leaves(
    elements: list[object],
    *,
    source_path: Path | None = None,
) -> list[SourceLeaf]:
    leaves: list[SourceLeaf] = []

    def _walk(node: object) -> None:
        if isinstance(node, Group):
            for child in node.children:
                _walk(child)
            return
        if _should_skip_source_leaf(node, source_path):
            return
        glyph_leaves = _text_glyph_source_leaves(node)
        if glyph_leaves is not None:
            leaves.extend(glyph_leaves)
            return
        bbox = getattr(node, "bbox", None)
        if bbox is None:
            return
        metadata = getattr(node, "metadata", {}) or {}
        leaves.append(
            SourceLeaf(
                kind=type(node).__name__,
                element_id=_primary_element_id(metadata),
                bbox=(
                    float(bbox.x),
                    float(bbox.y),
                    float(bbox.width),
                    float(bbox.height),
                ),
            )
        )

    for element in elements:
        _walk(element)
    return leaves


def _should_skip_source_leaf(node: object, source_path: Path | None) -> bool:
    if not isinstance(node, Rectangle):
        return False
    if source_path is None:
        return False
    normalized = str(source_path).replace("\\", "/")
    if not (normalized.startswith("tests/svg/") or "/tests/svg/" in normalized):
        return False
    return "test-frame" in _element_ids(node)


def _text_glyph_source_leaves(node: object) -> list[SourceLeaf] | None:
    if not isinstance(node, TextFrame):
        return None
    metadata = getattr(node, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        return None
    per_char = metadata.get("per_char")
    if not isinstance(per_char, dict):
        return None
    abs_x = per_char.get("abs_x")
    abs_y = per_char.get("abs_y")
    rotate = per_char.get("rotate")
    if not isinstance(abs_x, list) or not isinstance(abs_y, list):
        return None
    if not isinstance(rotate, list) or not rotate:
        return None

    text = node.text_content
    if not text:
        return None
    bbox = getattr(node, "bbox", None)
    if bbox is None:
        return None
    element_id = _primary_element_id(metadata)
    precise_leaves = _precise_text_glyph_source_leaves(
        node,
        per_char=per_char,
        element_id=element_id,
    )
    if precise_leaves:
        return precise_leaves

    right = float(bbox.x + bbox.width)
    leaves: list[SourceLeaf] = []
    for index, char in enumerate(text):
        if index >= len(abs_x) or index >= len(abs_y):
            break
        if not char.strip():
            continue
        try:
            x = float(abs_x[index])
            y = float(bbox.y)
        except (TypeError, ValueError):
            continue
        width = _glyph_width_from_positions(index, abs_x, right)
        height = max(float(bbox.height), 0.01)
        leaves.append(
            SourceLeaf(
                kind="TextGlyph",
                element_id=element_id,
                bbox=(x, y, width, height),
            )
        )
    return leaves or None


def _precise_text_glyph_source_leaves(
    node: TextFrame,
    *,
    per_char: dict[str, object],
    element_id: str | None,
) -> list[SourceLeaf] | None:
    runs = getattr(node, "runs", None) or []
    if not runs:
        return None
    run = runs[0]
    bbox = getattr(node, "bbox", None)
    if bbox is None:
        return None
    try:
        from svg2ooxml.drawingml.glyph_renderer import (
            SKIA_AVAILABLE,
            compute_glyph_placements,
            compute_positioned_glyph_bboxes,
        )
    except ImportError:
        return None
    if not SKIA_AVAILABLE:
        return None

    placements = compute_glyph_placements(
        node.text_content,
        run.font_family,
        run.font_size_pt,
        float(bbox.x),
        float(bbox.y + bbox.height),
        dx=_float_list_or_none(per_char.get("dx")),
        dy=_float_list_or_none(per_char.get("dy")),
        abs_x=_float_list_or_none(per_char.get("abs_x")),
        abs_y=_float_list_or_none(per_char.get("abs_y")),
        rotate=_float_list_or_none(per_char.get("rotate")),
    )
    glyph_bboxes = compute_positioned_glyph_bboxes(
        node.text_content,
        run.font_family,
        run.font_size_pt,
        placements,
    )
    return [
        SourceLeaf(
            kind="TextGlyph",
            element_id=element_id,
            bbox=tuple(float(value) for value in glyph.bbox),
        )
        for glyph in glyph_bboxes
    ] or None


def _float_list_or_none(values: object) -> list[float] | None:
    if not isinstance(values, list):
        return None
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        result.append(float(value))
    return result


def _glyph_width_from_positions(
    index: int,
    abs_x: list[object],
    right: float,
) -> float:
    current = float(abs_x[index])
    for next_value in abs_x[index + 1 :]:
        try:
            next_x = float(next_value)
        except (TypeError, ValueError):
            continue
        width = next_x - current
        if width > 0:
            return max(width, 0.01)
    return max(right - current, 0.01)


def _primary_element_id(metadata: object) -> str | None:
    if not isinstance(metadata, dict):
        return None
    element_ids = metadata.get("element_ids")
    return element_ids[0] if isinstance(element_ids, list) and element_ids else None


def _element_ids(node: object) -> tuple[str, ...]:
    metadata = getattr(node, "metadata", {}) or {}
    element_ids = metadata.get("element_ids") if isinstance(metadata, dict) else None
    if not isinstance(element_ids, list):
        return ()
    return tuple(str(element_id) for element_id in element_ids)


def _load_slide_leaves(pptx_path: Path) -> list[SlideLeaf]:
    try:
        with zipfile.ZipFile(pptx_path, "r") as archive:
            xml = archive.read("ppt/slides/slide1.xml")
    except (FileNotFoundError, KeyError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Unable to read slide1.xml from {pptx_path}") from exc

    root = ET.fromstring(xml)
    leaves: list[SlideLeaf] = []
    shape_tree = root.find("./p:cSld/p:spTree", NS)
    _collect_slide_leaves(
        shape_tree if shape_tree is not None else root,
        _SlideTransform(),
        leaves,
    )
    return leaves


def _collect_slide_leaves(
    container: ET._Element,
    transform: _SlideTransform,
    leaves: list[SlideLeaf],
) -> None:
    for element in container:
        local_name = ET.QName(element).localname
        if local_name == "grpSp":
            group_xfrm = element.find("./p:grpSpPr/a:xfrm", NS)
            _collect_slide_leaves(
                element,
                transform.with_group_xfrm(group_xfrm),
                leaves,
            )
            continue
        if local_name not in {"sp", "pic"}:
            continue
        leaf = _slide_leaf(element, transform)
        if leaf is not None:
            leaves.append(leaf)


def _slide_leaf(
    element: ET._Element,
    transform: _SlideTransform,
) -> SlideLeaf | None:
    xfrm = element.find("./p:spPr/a:xfrm", NS)
    if xfrm is None:
        return None
    off_x, off_y = _point_from_xfrm(xfrm, "off")
    ext_w, ext_h = _point_from_xfrm(xfrm, "ext")
    if element.tag == f"{{{PRESENTATION_NS}}}sp":
        c_nv_pr = element.find("./p:nvSpPr/p:cNvPr", NS)
    else:
        c_nv_pr = element.find("./p:nvPicPr/p:cNvPr", NS)
    return SlideLeaf(
        shape_tag=ET.QName(element).localname,
        shape_id=c_nv_pr.get("id") if c_nv_pr is not None else None,
        shape_name=c_nv_pr.get("name") if c_nv_pr is not None else None,
        bbox=transform.apply_bbox((off_x, off_y, ext_w, ext_h)),
    )


def _point_from_xfrm(xfrm: ET._Element, tag_name: str) -> tuple[float, float]:
    point = xfrm.find(f"./a:{tag_name}", NS)
    if point is None:
        return (0.0, 0.0)
    return (
        int(point.get("x", point.get("cx", "0"))) / EMU_PER_PX,
        int(point.get("y", point.get("cy", "0"))) / EMU_PER_PX,
    )


def _geometry_decisions_by_element(
    trace_report: dict[str, object] | None,
) -> dict[str, str]:
    if not trace_report:
        return {}
    events = trace_report.get("geometry_events")
    if not isinstance(events, list):
        return {}
    decisions: dict[str, str] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        element_id = event.get("element_id")
        decision = event.get("decision")
        if isinstance(element_id, str) and isinstance(decision, str):
            decisions[element_id] = decision
    return decisions


__all__ = [
    "SourceLeaf",
    "SlideLeaf",
    "SubstructurePair",
    "SubstructureComparison",
    "compare_substructures",
]
