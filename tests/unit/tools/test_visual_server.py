from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("PIL")

from fastapi.testclient import TestClient
from PIL import Image
from tools.visual.browser_renderer import RenderedSvg
from tools.visual.renderer import RenderedSlideSet, VisualRendererError
from tools.visual.server import create_app


class StubBuildResult:
    def __init__(self, pptx_path: Path, slide_count: int = 1) -> None:
        self.pptx_path = pptx_path
        self.slide_count = slide_count


class StubBuilder:
    _slide_size_mode = "same"

    def build_from_svg(
        self, svg_text: str, output_path: Path
    ) -> StubBuildResult:  # noqa: ARG002
        output_path.write_bytes(b"pptx")
        return StubBuildResult(output_path, slide_count=1)


class StubRenderer:
    available = True

    def render(
        self, pptx_path: Path, output_dir: Path
    ) -> RenderedSlideSet:  # noqa: ARG002
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = output_dir / "slide-1.png"
        Image.new("RGB", (16, 16), (255, 255, 255)).save(image_path)
        return RenderedSlideSet(images=(image_path,), renderer="stub")


class StubBrowserRenderer:
    available = True

    def render_svg(
        self,
        svg_text: str,  # noqa: ARG002
        output_path: Path,
        *,
        source_path: Path | None = None,  # noqa: ARG002
    ) -> RenderedSvg:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (16, 16), (255, 255, 255)).save(output_path)
        return RenderedSvg(image=output_path, renderer="stub-browser")


class FailingRenderer:
    available = True

    def render(
        self, pptx_path: Path, output_dir: Path
    ) -> RenderedSlideSet:  # noqa: ARG002
        raise VisualRendererError("LibreOffice failed to render PPTX.")


def test_visual_server_serves_fixture_listing(tmp_path) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    sample_svg = fixture_dir / "sample.svg"
    sample_svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>")

    app = create_app(
        fixture_root=fixture_dir,
        output_root=tmp_path / "out",
        builder=StubBuilder(),
        renderer=StubRenderer(),
        browser_renderer=StubBrowserRenderer(),
    )

    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert 'data-testid="fixture-list"' in response.text
    assert 'data-testid="fixture-item"' in response.text
    assert "sample.svg" in response.text

    compare = client.get("/compare", params={"name": "sample.svg"})
    assert compare.status_code == 200
    assert 'data-testid="download-links"' in compare.text
    assert 'data-testid="download-resvg"' in compare.text
    assert 'data-testid="download-browser"' in compare.text
    assert 'data-testid="pane-browser"' in compare.text
    assert 'data-testid="pane-browser-diff"' in compare.text
    assert 'data-testid="pane-resvg"' in compare.text
    assert 'data-testid="pane-structure"' in compare.text
    assert 'data-testid="structure-report"' in compare.text
    assert 'data-testid="browser-metrics"' in compare.text


def test_visual_server_keeps_structure_report_when_renderer_fails(tmp_path) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    sample_svg = fixture_dir / "sample.svg"
    sample_svg.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'>"
        "<rect id='rect1' x='2' y='2' width='10' height='10' fill='red'/>"
        "</svg>"
    )

    app = create_app(
        fixture_root=fixture_dir,
        output_root=tmp_path / "out",
        builder=StubBuilder(),
        renderer=FailingRenderer(),
        browser_renderer=StubBrowserRenderer(),
    )

    client = TestClient(app)

    compare = client.get("/compare", params={"name": "sample.svg"})
    assert compare.status_code == 200
    assert 'data-testid="pane-structure"' in compare.text
    assert 'data-testid="structure-report"' in compare.text
    assert "Resvg render failed" in compare.text
