from __future__ import annotations

import json
from pathlib import Path

import pytest

from svg2office.core.pptx_exporter import SvgPageSource, SvgToPptxExporter
from svg2office.core.tracing import ConversionTracer


def test_exporter_returns_trace_report(tmp_path: Path) -> None:
    exporter = SvgToPptxExporter()
    tracer = ConversionTracer()
    output_path = tmp_path / "trace_output.pptx"
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>"
        "<defs>"
        "  <linearGradient id='gradA'>"
        "    <stop offset='0%' stop-color='#000000'/>"
        "    <stop offset='100%' stop-color='#ffffff'/>"
        "  </linearGradient>"
        "</defs>"
        "<rect width='40' height='40' fill='url(#gradA)'/>"
        "</svg>"
    )

    result = exporter.convert_string(svg, output_path, tracer=tracer)

    assert output_path.exists()
    assert result.trace_report is not None
    # ensure JSON serializable
    json.dumps(result.trace_report)


def test_exporter_auto_tracer_returns_trace(tmp_path: Path) -> None:
    exporter = SvgToPptxExporter()
    output_path = tmp_path / "auto_trace.pptx"
    svg = "<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'><rect width='20' height='20' fill='#f00'/></svg>"

    result = exporter.convert_string(svg, output_path)

    assert output_path.exists()
    assert result.trace_report is not None
    stage_names = {event["stage"] for event in result.trace_report.get("stage_events", [])}
    assert {"parser", "converter", "writer", "packaging"}.issubset(stage_names)


def test_exporter_convert_pages(tmp_path: Path) -> None:
    exporter = SvgToPptxExporter()
    output_path = tmp_path / "multi.pptx"
    pages = [
        SvgPageSource(
            svg_text="<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'><rect width='20' height='20' fill='#f00'/></svg>",
            title="First",
        ),
        SvgPageSource(
            svg_text="<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'><circle cx='10' cy='10' r='10' fill='#0f0'/></svg>",
            title="Second",
        ),
    ]

    result = exporter.convert_pages(pages, output_path)

    assert output_path.exists()
    assert result.slide_count == 2
    assert len(result.page_results) == 2
    assert "stage_events" in result.aggregated_trace_report
    aggregated_stages = {event["stage"] for event in result.aggregated_trace_report.get("stage_events", [])}
    assert {"packaging"}.issubset(aggregated_stages)


def test_exporter_uses_env_office_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SVG2OOXML_OFFICE_PROFILE", "office_compat")
    exporter = SvgToPptxExporter()
    assert exporter._office_profile == "office_compat"
    assert exporter._writer._office_profile == "office_compat"


def test_exporter_office_profile_arg_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SVG2OOXML_OFFICE_PROFILE", "ecma_strict")
    exporter = SvgToPptxExporter(office_profile="office_compat")
    assert exporter._office_profile == "office_compat"
    assert exporter._writer._office_profile == "office_compat"


def test_exporter_rejects_unknown_office_profile() -> None:
    with pytest.raises(ValueError, match="office_profile"):
        SvgToPptxExporter(office_profile="bad-profile")


def test_exporter_convert_pages_with_variants(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exporter = SvgToPptxExporter()
    output_path = tmp_path / "variants.pptx"
    page = SvgPageSource(
        svg_text="<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'><rect width='20' height='20' fill='#f00'/></svg>",
        title="Base",
    )

    from svg2office.core.slide_orchestrator import FallbackVariant

    monkeypatch.setattr(
        "svg2office.core.pptx_exporter.derive_variants_from_trace",
        lambda report, enable_split: [FallbackVariant(name="geometry_bitmap", policy_overrides={"geometry": {"force_bitmap": True}}, title_suffix=" (Bitmap)")] if enable_split else [],
    )

    monkeypatch.setattr(
        "svg2office.core.pptx_exporter.expand_page_with_variants",
        lambda src, variants: [
            SvgPageSource(
                svg_text=src.svg_text,
                title=(src.title or "Slide") + variant.title_suffix,
                name=f"{src.name or 'slide'}_{variant.name}",
                metadata={"variant": {"type": variant.name}, "policy_overrides": variant.policy_overrides},
            )
            for variant in variants
        ],
    )

    result = exporter.convert_pages([page], output_path, split_fallback_variants=True)

    assert result.slide_count == 2
    variant_titles = [page_result.title for page_result in result.page_results]
    assert any("Bitmap" in title for title in variant_titles)


def test_exporter_convert_pages_with_tiers(tmp_path: Path) -> None:
    exporter = SvgToPptxExporter()
    output_path = tmp_path / "tiers.pptx"
    page = SvgPageSource(
        svg_text="<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'><rect width='20' height='20' fill='#f00'/></svg>",
        title="Tiered",
    )

    result = exporter.convert_pages([page], output_path, render_tiers=True)

    assert result.slide_count == 4
    variant_types = [
        page_result.metadata.get("variant", {}).get("type")
        for page_result in result.page_results
        if page_result.metadata
    ]
    assert set(variant_types) == {"direct", "mimic", "emf", "bitmap"}
