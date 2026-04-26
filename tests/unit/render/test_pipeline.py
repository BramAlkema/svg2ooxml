from __future__ import annotations

import pytest

pytest.importorskip("skia")
pytest.importorskip("numpy")

from svg2ooxml.core.resvg.normalizer import normalize_svg_string
from svg2ooxml.render.pipeline import render


def test_render_simple_rectangle_produces_alpha() -> None:
    svg_markup = """
        <svg width="20" height="10" viewBox="0 0 20 10">
            <rect x="2" y="2" width="10" height="6" fill="#ff0000" />
        </svg>
    """
    result = normalize_svg_string(svg_markup)
    surface = render(result.tree)

    assert surface.width == 20
    assert surface.height == 10

    rgba = surface.to_rgba8()
    assert rgba.shape == (10, 20, 4)
    assert rgba[..., 3].max() > 0
    # central pixel should be filled red with full alpha
    assert rgba[5, 7, 0] > 0 and rgba[5, 7, 3] == 255


def test_render_image_uses_resolved_percentage_geometry() -> None:
    png_data = (
        "iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAYAAAC09K7GAAAAFUlEQVR4nGP8z8DwnwEJ"
        "MCFzsAoAAGFrAgT6YybLAAAAAElFTkSuQmCC"
    )
    svg_markup = f"""
        <svg width="20" height="10">
            <image href="data:image/png;base64,{png_data}"
                   x="10%" y="20%" width="50%" height="50%"/>
        </svg>
    """
    result = normalize_svg_string(svg_markup)
    surface = render(result.tree)

    rgba = surface.to_rgba8()
    assert rgba[4, 7, 3] > 0
    assert rgba[0, 0, 3] == 0
