"""Structural comparison helpers for source SVG IR vs generated PPTX slide XML."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import zipfile

from lxml import etree as ET

from svg2ooxml.core.parser import ParserConfig, SVGParser
from svg2ooxml.ir.entrypoints import convert_parser_output
from svg2ooxml.ir.scene import Group
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
    source_leaves = tuple(_flatten_scene_leaves(scene.elements))
    slide_leaves = tuple(_load_slide_leaves(Path(pptx_path)))
    geometry_decisions = _geometry_decisions_by_element(trace_report)

    pairs: list[SubstructurePair] = []
    for source, target in zip(source_leaves, slide_leaves):
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


def _flatten_scene_leaves(elements: list[object]) -> list[SourceLeaf]:
    leaves: list[SourceLeaf] = []

    def _walk(node: object) -> None:
        if isinstance(node, Group):
            for child in node.children:
                _walk(child)
            return
        bbox = getattr(node, "bbox", None)
        if bbox is None:
            return
        metadata = getattr(node, "metadata", {}) or {}
        element_ids = metadata.get("element_ids")
        element_id = (
            element_ids[0] if isinstance(element_ids, list) and element_ids else None
        )
        leaves.append(
            SourceLeaf(
                kind=type(node).__name__,
                element_id=element_id,
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


def _load_slide_leaves(pptx_path: Path) -> list[SlideLeaf]:
    try:
        with zipfile.ZipFile(pptx_path, "r") as archive:
            xml = archive.read("ppt/slides/slide1.xml")
    except (FileNotFoundError, KeyError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Unable to read slide1.xml from {pptx_path}") from exc

    root = ET.fromstring(xml)
    leaves: list[SlideLeaf] = []
    for element in root.xpath(".//p:sp | .//p:pic", namespaces=NS):
        xfrm = element.find("./p:spPr/a:xfrm", NS)
        if xfrm is None:
            continue
        off = xfrm.find("./a:off", NS)
        ext = xfrm.find("./a:ext", NS)
        if off is None or ext is None:
            continue
        if element.tag == f"{{{PRESENTATION_NS}}}sp":
            c_nv_pr = element.find("./p:nvSpPr/p:cNvPr", NS)
        else:
            c_nv_pr = element.find("./p:nvPicPr/p:cNvPr", NS)
        leaves.append(
            SlideLeaf(
                shape_tag=element.tag.split("}")[-1],
                shape_id=c_nv_pr.get("id") if c_nv_pr is not None else None,
                shape_name=c_nv_pr.get("name") if c_nv_pr is not None else None,
                bbox=(
                    int(off.get("x", "0")) / EMU_PER_PX,
                    int(off.get("y", "0")) / EMU_PER_PX,
                    int(ext.get("cx", "0")) / EMU_PER_PX,
                    int(ext.get("cy", "0")) / EMU_PER_PX,
                ),
            )
        )
    return leaves


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
