"""End-to-end checks around the SVG to PPTX exporter."""

from __future__ import annotations

import json
import zipfile

import pytest
from lxml import etree as ET

from svg2ooxml.core.pptx_exporter import (
    SvgConversionError,
    SvgPageSource,
    SvgToPptxExporter,
)
from svg2ooxml.io.pptx_docprops import CUSTOM_PROPERTIES_PART, CUSTOM_TRACE_PROPERTY


def test_convert_string_produces_slide_with_expected_fill(tmp_path) -> None:
    exporter = SvgToPptxExporter()
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
        "<rect width='10' height='10' fill='#336699'/>"
        "</svg>"
    )

    output_path = tmp_path / "single-slide.pptx"
    result = exporter.convert_string(svg_markup, output_path)

    assert output_path.exists()
    assert result.slide_count == 1
    stage_totals = result.trace_report.get("stage_totals", {})
    assert stage_totals.get("parser:normalization") == 1
    assert isinstance(result.trace_report.get("resvg_metrics", {}), dict)

    with zipfile.ZipFile(output_path, "r") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

    root = ET.fromstring(slide_xml.encode())
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    fills = root.findall(".//a:solidFill/a:srgbClr", ns)
    assert any(
        fill.get("val") == "336699" for fill in fills
    ), "Expected rectangle fill colour in slide XML"


def test_convert_string_embeds_trace_docprops_only_when_requested(tmp_path) -> None:
    exporter = SvgToPptxExporter()
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
        "<rect width='10' height='10' fill='#336699'/>"
        "</svg>"
    )

    default_path = tmp_path / "default.pptx"
    exporter.convert_string(svg_markup, default_path)
    with zipfile.ZipFile(default_path, "r") as archive:
        assert CUSTOM_PROPERTIES_PART not in set(archive.namelist())

    embedded_path = tmp_path / "embedded.pptx"
    exporter.convert_string(svg_markup, embedded_path, embed_trace_docprops=True)
    with zipfile.ZipFile(embedded_path, "r") as archive:
        custom_xml = archive.read(CUSTOM_PROPERTIES_PART)

    payload = _trace_payload_from_custom_xml(custom_xml)
    assert payload["stage_totals"]["parser:normalization"] == 1


@pytest.mark.parametrize("parallel", [False, True])
def test_convert_pages_creates_multi_slide_package(tmp_path, parallel: bool) -> None:
    exporter = SvgToPptxExporter()
    slide_one = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
        "<rect width='10' height='10' fill='#ff0000'/>"
        "</svg>"
    )
    slide_two = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
        "<circle cx='5' cy='5' r='5' fill='#00ff00'/>"
        "</svg>"
    )
    pages = [
        SvgPageSource(svg_text=slide_one, title="First", name="first"),
        SvgPageSource(svg_text=slide_two, title="Second", name="second"),
    ]

    suffix = "parallel" if parallel else "serial"
    output_path = tmp_path / f"multi-slide-{suffix}.pptx"
    multi_result = exporter.convert_pages(pages, output_path, parallel=parallel)

    assert output_path.exists()
    assert multi_result.slide_count == len(pages)
    assert len(multi_result.page_results) == len(pages)

    aggregated_totals = multi_result.aggregated_trace_report.get("stage_totals", {})
    assert aggregated_totals.get("parser:normalization") == len(pages)
    assert isinstance(
        multi_result.aggregated_trace_report.get("resvg_metrics", {}), dict
    )

    packaging_totals = multi_result.packaging_report.get("stage_totals", {})
    assert packaging_totals.get("packaging:slide_xml_written") == len(pages)

    assert all(
        page.trace_report.get("stage_totals", {}).get("parser:normalization") == 1
        for page in multi_result.page_results
    )

    with zipfile.ZipFile(output_path, "r") as archive:
        names = set(archive.namelist())
        expected_slides = {
            f"ppt/slides/slide{index}.xml" for index in range(1, len(pages) + 1)
        }
        assert expected_slides.issubset(names)

        slide1_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        slide2_xml = archive.read("ppt/slides/slide2.xml").decode("utf-8")
        assert "FF0000" in slide1_xml
        assert "00FF00" in slide2_xml


def _srgb_to_linear_byte(value: int) -> int:
    """Linearise one display-sRGB byte — the transform that must NOT be applied."""

    c = value / 255.0
    linear = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return round(linear * 255)


def _linear_to_srgb_byte(value: int) -> int:
    """Encode one linear-light byte to display sRGB — likewise must NOT be applied."""

    c = value / 255.0
    encoded = c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return round(encoded * 255)


def _gamma_shifted_variants(hex_value: str) -> set[str]:
    """Both directions of a stray gamma transform applied to ``hex_value``."""

    channels = [int(hex_value[i : i + 2], 16) for i in (0, 2, 4)]
    return {
        "".join(f"{transform(channel):02X}" for channel in channels)
        for transform in (_srgb_to_linear_byte, _linear_to_srgb_byte)
    }


def test_srgb_clr_carries_display_srgb_bytes_verbatim(tmp_path) -> None:
    """``a:srgbClr`` receives the author's display-sRGB bytes with no gamma transform.

    PowerPoint interpolates gradient stops in linear light and alpha-composites in
    display sRGB. Neither is ours to compensate for: pre-linearising stop colours to
    move a gradient's midpoint would corrupt the endpoints, which are the only colours
    the author actually specified. Gradient stops carry the weight of this test because
    that is where the compensating transform is tempting to add.

    See docs/reference/research/drawingml-srgb-emission-contract.md
    """

    # Mid-tones only — #000000/#FFFFFF are fixpoints of both transfer functions and
    # would let a stray gamma transform through unnoticed.
    stop_start, stop_mid, stop_end = "808080", "336699", "CC3300"
    solid = "6699CC"

    exporter = SvgToPptxExporter()
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'>"
        "<defs><linearGradient id='grad' x1='0' y1='0' x2='1' y2='0'>"
        f"<stop offset='0' stop-color='#{stop_start}'/>"
        f"<stop offset='0.5' stop-color='#{stop_mid}' stop-opacity='0.5'/>"
        f"<stop offset='1' stop-color='#{stop_end}'/>"
        "</linearGradient></defs>"
        "<rect width='100' height='60' fill='url(#grad)'/>"
        f"<rect y='70' width='100' height='30' fill='#{solid}'"
        f" stroke='#{stop_end}' stroke-width='2'/>"
        "</svg>"
    )

    output_path = tmp_path / "srgb-fidelity.pptx"
    exporter.convert_string(svg_markup, output_path)

    with zipfile.ZipFile(output_path, "r") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

    root = ET.fromstring(slide_xml.encode())
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}

    stops = root.findall(".//a:gradFill/a:gsLst/a:gs", ns)
    assert stops, "Expected the linear gradient to emit DrawingML gradient stops"

    stop_colors = [
        color.get("val")
        for stop in stops
        if (color := stop.find("a:srgbClr", ns)) is not None
    ]
    for expected in (stop_start, stop_mid, stop_end):
        assert expected in stop_colors, (
            f"Gradient stop #{expected} must reach a:srgbClr unchanged; "
            f"got {stop_colors}"
        )

    # Alpha rides the same contract: display-sRGB compositing means the opacity is
    # scaled to PPT units, never curved.
    alphas = [
        alpha.get("val")
        for stop in stops
        if (alpha := stop.find("a:srgbClr/a:alpha", ns)) is not None
    ]
    assert "50000" in alphas, f"stop-opacity 0.5 must emit alpha 50000; got {alphas}"

    solid_fills = {
        color.get("val") for color in root.findall(".//a:solidFill/a:srgbClr", ns)
    }
    assert solid in solid_fills, f"Solid fill #{solid} must survive verbatim"
    assert stop_end in {
        color.get("val") for color in root.findall(".//a:ln//a:srgbClr", ns)
    }, f"Stroke colour #{stop_end} must survive verbatim"

    # Belt and braces: no gamma-shifted variant of any probe colour appears anywhere
    # in the slide part, in either direction.
    upper_xml = slide_xml.upper()
    for source in (stop_start, stop_mid, stop_end, solid):
        for shifted in _gamma_shifted_variants(source):
            assert shifted not in upper_xml, (
                f"Found gamma-shifted colour {shifted} in slide XML — #{source} was "
                "transformed on the way to a:srgbClr"
            )


def test_parallel_convert_pages_rejects_custom_render_components(tmp_path) -> None:
    exporter = SvgToPptxExporter(parser=object())  # type: ignore[arg-type]
    pages = [
        SvgPageSource(
            svg_text="<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>"
        )
    ]

    with pytest.raises(SvgConversionError, match="custom render components: parser"):
        exporter.convert_pages(pages, tmp_path / "custom-parallel.pptx", parallel=True)


def _trace_payload_from_custom_xml(custom_xml: bytes) -> dict[str, object]:
    root = ET.fromstring(custom_xml)
    ns = {
        "cp": "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties",
        "vt": "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes",
    }
    prop = root.find(f".//cp:property[@name='{CUSTOM_TRACE_PROPERTY}']", ns)
    assert prop is not None
    value = prop.find("vt:lpwstr", ns)
    assert value is not None and value.text
    payload = json.loads(value.text)
    assert isinstance(payload, dict)
    return payload
