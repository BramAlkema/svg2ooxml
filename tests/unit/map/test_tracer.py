"""Tests for the conversion tracer."""

from __future__ import annotations

from svg2ooxml.core.ir import IRConverter
from svg2ooxml.core.tracing import ConversionTracer
from svg2ooxml.policy.engine import PolicyContext
from svg2ooxml.services.setup import configure_services
from tests.unit.map.test_ir_converter import _build_parse_result


def _convert_with_tracer(
    svg_markup: str,
    tracer: ConversionTracer,
    policy: PolicyContext | None = None,
):
    parse_result = _build_parse_result(svg_markup)
    services = parse_result.services or configure_services()
    converter = IRConverter(services=services, policy_context=policy, tracer=tracer)
    return converter.convert(parse_result)


def test_tracer_records_native_geometry_decision() -> None:
    tracer = ConversionTracer()
    scene = _convert_with_tracer(
        "<svg width='100' height='100' xmlns='http://www.w3.org/2000/svg'><path d='M0 0 L10 0 L10 10 Z' fill='#ff0000'/></svg>",
        tracer,
    )
    report = tracer.report()
    assert report.geometry_totals.get("native") == 1
    assert report.geometry_totals.get("emf", 0) == 0
    assert scene.metadata and "trace_report" in scene.metadata


def test_tracer_records_emf_then_bitmap_decisions() -> None:
    emf_policy = PolicyContext(selections={"geometry": {"max_segments": 1, "simplify_paths": False}})
    tracer = ConversionTracer()
    _convert_with_tracer(
        "<svg width='100' height='100' xmlns='http://www.w3.org/2000/svg'><path d='M0 0 L10 0 L10 10 L0 10 Z' fill='#00ff00'/></svg>",
        tracer,
        policy=emf_policy,
    )
    report = tracer.report()
    assert report.geometry_totals.get("emf") == 1

    bitmap_policy = PolicyContext(selections={"geometry": {"force_bitmap": True}})
    tracer.reset()
    _convert_with_tracer(
        "<svg width='100' height='100' xmlns='http://www.w3.org/2000/svg'><path d='M0 0 L10 0 L10 10 L0 10 Z' fill='#0000ff'/></svg>",
        tracer,
        policy=bitmap_policy,
    )
    bitmap_report = tracer.report()
    assert bitmap_report.geometry_totals.get("bitmap") == 1


def test_tracer_records_paint_fallback() -> None:
    svg_markup = (
        "<svg width='60' height='60' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <meshgradient id='meshGrad'>"
        "    <meshrow>"
        "      <meshpatch><stop offset='0' stop-color='#ff0000'/></meshpatch>"
        "      <meshpatch><stop offset='1' stop-color='#0000ff'/></meshpatch>"
        "    </meshrow>"
        "  </meshgradient>"
        "</defs>"
        "<rect width='30' height='30' fill='url(#meshGrad)'/>"
        "</svg>"
    )
    tracer = ConversionTracer()
    parse_result = _build_parse_result(svg_markup)
    services = parse_result.services or configure_services()
    converter = IRConverter(services=services, tracer=tracer)
    converter.convert(parse_result)
    report = tracer.report()
    assert report.paint_totals.get("emf") == 1


def test_tracer_records_clip_mask_filter() -> None:
    tracer = ConversionTracer()
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='60' height='60'>"
        "<defs>"
        "  <clipPath id='clipA'><rect x='0' y='0' width='30' height='30'/></clipPath>"
        "  <mask id='maskA'><rect x='0' y='0' width='30' height='30' fill='#ffffff'/></mask>"
        "  <filter id='blurA'><feGaussianBlur stdDeviation='2'/></filter>"
        "</defs>"
        "<rect x='5' y='5' width='40' height='40' fill='#0088ff' clip-path='url(#clipA)' mask='url(#maskA)' filter='url(#blurA)'/>"
        "</svg>"
    )

    _convert_with_tracer(svg, tracer)
    report = tracer.report()

    assert any(event.tag == "mask" for event in report.geometry_events)
    assert any("clip_id" in (event.metadata or {}) for event in report.geometry_events)
    assert report.paint_totals.get("bitmap", 0) >= 1 or report.paint_totals.get("emf", 0) >= 1


def test_tracer_records_stage_events() -> None:
    tracer = ConversionTracer()
    tracer.record_stage_event(stage="parser", action="normalization", metadata={"changes": 2})
    tracer.record_stage_event(stage="parser", action="warning", subject="duplicate-id")
    report = tracer.report()
    key = "parser:normalization"
    assert report.stage_totals.get(key) == 1
    assert any(event.action == "warning" and event.subject == "duplicate-id" for event in report.stage_events)


def test_legacy_module_still_exposes_tracer() -> None:
    from svg2ooxml.map import tracer as legacy_tracer

    assert legacy_tracer.ConversionTracer is ConversionTracer
