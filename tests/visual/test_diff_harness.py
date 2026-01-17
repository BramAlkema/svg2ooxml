"""Smoke tests for the visual diff infrastructure."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from PIL import Image  # type: ignore[import]  # noqa: E402

from tools.visual.diff import ImageDiffError


def _make_image(path: Path, color: tuple[int, int, int, int]) -> None:
    image = Image.new("RGBA", (16, 16), color)
    image.save(path)


@pytest.mark.visual
def test_image_diff_accepts_identical_images(tmp_path, visual_tools) -> None:
    generated = tmp_path / "generated"
    golden = tmp_path / "golden"
    diff_dir = tmp_path / "diff"

    generated.mkdir()
    golden.mkdir()

    _make_image(golden / "slide1.png", (255, 0, 0, 255))
    _make_image(generated / "slide1.png", (255, 0, 0, 255))

    result = visual_tools.diff.compare_directories(generated, golden, diff_dir=diff_dir)
    assert result.compared == 1
    assert result.max_delta == 0
    assert result.mean_delta == 0
    assert list(diff_dir.glob("*_diff.png"))


@pytest.mark.visual
def test_image_diff_raises_on_difference(tmp_path, visual_tools) -> None:
    generated = tmp_path / "generated"
    golden = tmp_path / "golden"

    generated.mkdir()
    golden.mkdir()

    _make_image(golden / "slide1.png", (255, 0, 0, 255))
    _make_image(generated / "slide1.png", (0, 0, 255, 255))

    with pytest.raises(ImageDiffError):
        visual_tools.diff.compare_directories(generated, golden)
