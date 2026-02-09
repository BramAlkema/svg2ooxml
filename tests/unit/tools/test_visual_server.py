from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from tools.visual.renderer import RenderedSlideSet
from tools.visual.server import create_app


class StubBuildResult:
    def __init__(self, pptx_path: Path, slide_count: int = 1) -> None:
        self.pptx_path = pptx_path
        self.slide_count = slide_count


class StubBuilder:
    _slide_size_mode = "same"

    def build_from_svg(self, svg_text: str, output_path: Path) -> StubBuildResult:  # noqa: ARG002
        output_path.write_bytes(b"pptx")
        return StubBuildResult(output_path, slide_count=1)


class StubRenderer:
    available = True

    def render(self, pptx_path: Path, output_dir: Path) -> RenderedSlideSet:  # noqa: ARG002
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = output_dir / "slide-1.png"
        image_path.write_bytes(b"png")
        return RenderedSlideSet(images=(image_path,), renderer="stub")


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
    )

    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert "sample.svg" in response.text

    compare = client.get("/compare", params={"name": "sample.svg"})
    assert compare.status_code == 200
    assert "Download PPTX" in compare.text
    assert "PPTX Render" in compare.text
