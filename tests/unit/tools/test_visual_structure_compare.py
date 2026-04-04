from __future__ import annotations

from pathlib import Path

from svg2ooxml.core.tracing import ConversionTracer
from tools.visual.builder import PptxBuilder
from tools.visual.structure_compare import compare_substructures


def test_compare_substructures_preserves_leaf_order_and_bbox(tmp_path: Path) -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="120" height="80">
      <rect id="rect1" x="10" y="10" width="30" height="20" fill="#ff0000" />
      <circle id="circle1" cx="80" cy="35" r="15" fill="#0000ff" />
    </svg>
    """
    pptx_path = tmp_path / "sample.pptx"

    builder = PptxBuilder(
        filter_strategy="resvg",
        geometry_mode="resvg",
        slide_size_mode="same",
        allow_promotion=False,
    )
    builder.build_from_svg(svg, pptx_path)

    report = compare_substructures(
        svg,
        pptx_path,
        filter_strategy="resvg",
        geometry_mode="resvg",
    )

    assert report.source_count == 2
    assert report.target_count == 2
    assert [pair.source.element_id for pair in report.pairs] == ["rect1", "circle1"]
    assert [pair.target.shape_tag for pair in report.pairs] == ["sp", "sp"]
    assert max(pair.max_abs_delta for pair in report.pairs) < 0.05


def test_compare_substructures_flags_rasterized_fallbacks(tmp_path: Path) -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="120" height="80">
      <defs>
        <pattern id="dots" patternUnits="userSpaceOnUse" width="8" height="8">
          <g transform="translate(1,1)">
            <path d="M0,0 C2,6 6,2 8,8" stroke="#000000" fill="none" />
          </g>
        </pattern>
      </defs>
      <path id="patterned" d="M10,10 L60,10 L60,40 L10,40 Z" fill="url(#dots)" />
    </svg>
    """
    pptx_path = tmp_path / "patterned.pptx"

    builder = PptxBuilder(
        filter_strategy="resvg",
        geometry_mode="resvg",
        slide_size_mode="same",
        allow_promotion=False,
    )
    from svg2ooxml.core.tracing import ConversionTracer

    tracer = ConversionTracer()
    builder.build_from_svg(svg, pptx_path, tracer=tracer)

    report = compare_substructures(
        svg,
        pptx_path,
        filter_strategy="resvg",
        geometry_mode="resvg",
        trace_report=tracer.report().to_dict(),
    )

    rasterized = report.rasterized_pairs()
    assert len(rasterized) == 1
    assert rasterized[0].source.element_id == "patterned"
    assert rasterized[0].target.shape_tag == "pic"
    assert rasterized[0].geometry_decision == "bitmap"


def test_compare_substructures_keeps_interactive_annotations_aligned(
    tmp_path: Path,
) -> None:
    fixture = (
        Path(__file__).resolve().parents[2]
        / "visual"
        / "fixtures"
        / "interactive_annotation.svg"
    )
    svg = fixture.read_text()
    pptx_path = tmp_path / "interactive_annotation.pptx"

    builder = PptxBuilder(
        filter_strategy="resvg",
        geometry_mode="resvg",
        slide_size_mode="same",
        allow_promotion=False,
    )
    tracer = ConversionTracer()
    builder.build_from_svg(svg, pptx_path, tracer=tracer, source_path=fixture)

    report = compare_substructures(
        svg,
        pptx_path,
        source_path=fixture,
        filter_strategy="resvg",
        geometry_mode="resvg",
        trace_report=tracer.report().to_dict(),
    )

    pairs_by_id = {
        pair.source.element_id: pair
        for pair in report.pairs
        if pair.source.element_id is not None
    }
    for element_id in (
        "step_start_hotspot",
        "step_branch_hotspot",
        "step_resolve_hotspot",
        "label_start",
        "label_branch",
        "label_resolve",
    ):
        assert pairs_by_id[element_id].target.shape_tag == "sp"
        assert pairs_by_id[element_id].max_abs_delta < 0.1
