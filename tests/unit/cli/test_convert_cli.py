from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from click.testing import CliRunner

from cli.commands.convert import convert
from svg2ooxml.core.pptx_exporter import SvgPageSource


class _MockResponse:
    def __init__(self, data: bytes, content_type: str = "image/svg+xml; charset=utf-8") -> None:
        self._data = data
        self.headers = SimpleNamespace(get_content_charset=lambda: "utf-8")
        self.status = 200
        self.reason = "OK"

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_MockResponse":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


def test_convert_accepts_http_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    svg_markup = dedent(
        """\
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
            <rect width="20" height="20" fill="#00FF00"/>
        </svg>
        """
    ).strip().encode("utf-8")

    def fake_urlopen(uri: str):
        assert uri == "https://example.com/test.svg"
        return _MockResponse(svg_markup)

    monkeypatch.setattr("cli.commands.convert.urlopen", fake_urlopen)

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(convert, ["https://example.com/test.svg", "--verbose"], catch_exceptions=False)
        assert result.exit_code == 0
        pptx_path = Path("test.pptx")
        assert pptx_path.exists()
        trace_path = pptx_path.with_suffix(".pptx.trace.json")
        assert trace_path.exists()


def test_convert_uri_reports_fetch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_urlopen(_uri: str):
        raise URLError("network unreachable")

    monkeypatch.setattr("cli.commands.convert.urlopen", failing_urlopen)

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(convert, ["https://example.com/bad.svg"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "Failed to fetch SVG" in result.output


def test_convert_cli_with_extra_slides() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("base.svg").write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'><rect width='10' height='10' fill='#f00'/></svg>",
            encoding="utf-8",
        )
        Path("second.svg").write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'><rect width='10' height='10' fill='#0f0'/></svg>",
            encoding="utf-8",
        )

        result = runner.invoke(
            convert,
            ["base.svg", "--slide", "second.svg", "--verbose"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        pptx_path = Path("base.pptx")
        assert pptx_path.exists()

        trace_path = pptx_path.with_suffix(".pptx.trace.json")
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        assert "aggregated" in payload
        assert len(payload["pages"]) == 2


def test_convert_cli_split_pages_option() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        multipage_svg = dedent(
            """\
            <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
                <g class="page" id="page-1">
                    <rect width="10" height="10" fill="#f00"/>
                </g>
                <g class="page" id="page-2">
                    <circle cx="5" cy="5" r="5" fill="#00f"/>
                </g>
            </svg>
            """
        )
        Path("multipage.svg").write_text(multipage_svg, encoding="utf-8")

        result = runner.invoke(convert, ["multipage.svg", "--verbose"], catch_exceptions=False)
        assert result.exit_code == 0

        trace_path = Path("multipage.pptx.trace.json")
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        assert len(payload["pages"]) == 2


def test_convert_cli_disable_split_pages() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        multipage_svg = dedent(
            """\
            <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
                <g class="page" id="page-1">
                    <rect width="10" height="10" fill="#f00"/>
                </g>
                <g class="page" id="page-2">
                    <circle cx="5" cy="5" r="5" fill="#00f"/>
                </g>
            </svg>
            """
        )
        Path("multipage.svg").write_text(multipage_svg, encoding="utf-8")

        result = runner.invoke(
            convert,
            ["multipage.svg", "--no-split-pages", "--verbose"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        trace_path = Path("multipage.pptx.trace.json")
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        if "pages" in payload:
            assert len(payload["pages"]) == 1
        else:
            # single-slide run falls back to legacy structure
            assert "stage_events" in payload


def test_convert_cli_split_fallback_slides(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("shape.svg").write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'><rect width='10' height='10' fill='#f00'/></svg>",
            encoding="utf-8",
        )

        from svg2ooxml.core.slide_orchestrator import FallbackVariant

        monkeypatch.setattr(
            "svg2ooxml.core.pptx_exporter.derive_variants_from_trace",
            lambda report, enable_split: [FallbackVariant(name="geometry_bitmap", policy_overrides={"geometry": {"force_bitmap": True}}, title_suffix=" (Bitmap)")] if enable_split else [],
        )

        def fake_expand(page, variants):
            clones = []
            for variant in variants:
                metadata = {"variant": {"type": variant.name}, "policy_overrides": variant.policy_overrides}
                clones.append(
                    SvgPageSource(
                        svg_text=page.svg_text,
                        title=(page.title or "Slide") + variant.title_suffix,
                        name=f"{page.name}_{variant.name}" if page.name else variant.name,
                        metadata=metadata,
                    )
                )
            return clones

        monkeypatch.setattr("svg2ooxml.core.pptx_exporter.expand_page_with_variants", fake_expand)

        result = runner.invoke(
            convert,
            ["shape.svg", "--split-fallback-slides", "--verbose"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        trace_path = Path("shape.pptx.trace.json")
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        assert len(payload["pages"]) == 2
