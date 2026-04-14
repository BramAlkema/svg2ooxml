from __future__ import annotations

from pathlib import Path

import pytest
from tools.visual.builder import PptxBuilder
from tools.visual.structure_compare import compare_substructures

from svg2ooxml.core.tracing import ConversionTracer


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


def test_pptx_builder_forwards_tracer_into_animation_writer(tmp_path: Path) -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="120" height="80">
      <rect id="rect1" x="10" y="10" width="30" height="20" fill="#ff0000">
        <animate attributeName="opacity" values="0;1" dur="1s" begin="0s" />
      </rect>
    </svg>
    """
    pptx_path = tmp_path / "animated.pptx"

    builder = PptxBuilder(
        filter_strategy="resvg",
        geometry_mode="resvg",
        slide_size_mode="same",
        allow_promotion=False,
    )
    tracer = ConversionTracer()
    builder.build_from_svg(svg, pptx_path, tracer=tracer)

    report = tracer.report().to_dict()

    assert report["stage_totals"].get("animation:fragment_emitted") == 1
    assert any(
        event["stage"] == "animation" and event["action"] == "fragment_emitted"
        for event in report["stage_events"]
    )


def test_pptx_builder_enriches_motion_metadata_before_render(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="480" height="360">
      <path id="triangle" d="M-30,0 L0,-60 L30,0 z" fill="blue" stroke="green">
        <animateMotion from="90,258" to="390,180" begin="0s" dur="3s" fill="freeze"/>
      </path>
    </svg>
    """
    pptx_path = tmp_path / "motion.pptx"

    builder = PptxBuilder(
        filter_strategy="resvg",
        geometry_mode="resvg",
        slide_size_mode="same",
        allow_promotion=False,
    )
    captured: dict[str, object] = {}

    def fake_render_scene_from_ir(scene, **kwargs):
        captured["scene"] = scene
        return object()

    def fake_build_from_results(results, output_path, **kwargs):
        return output_path

    monkeypatch.setattr(
        builder._writer,
        "render_scene_from_ir",
        fake_render_scene_from_ir,
    )
    monkeypatch.setattr(
        builder._builder,
        "build_from_results",
        fake_build_from_results,
    )

    builder.build_from_svg(svg, pptx_path)

    scene = captured["scene"]
    animations = scene.animations or []
    assert len(animations) == 1
    assert animations[0].element_motion_offset_px == (-30.0, -60.0)
    assert animations[0].motion_viewport_px == (480.0, 360.0)

    def find_animated_path(elements):
        for element in elements:
            metadata = getattr(element, "metadata", None)
            if isinstance(metadata, dict) and animations[0].element_id in metadata.get(
                "element_ids",
                [],
            ):
                return element
            children = getattr(element, "children", None)
            if children:
                match = find_animated_path(children)
                if match is not None:
                    return match
        return None

    animated_path = find_animated_path(scene.elements)

    assert animated_path is not None
    assert animated_path.bbox.x == pytest.approx(60.0)
    assert animated_path.bbox.y == pytest.approx(198.0)
