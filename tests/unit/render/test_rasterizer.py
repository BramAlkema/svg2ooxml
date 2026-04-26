from __future__ import annotations

from svg2ooxml.core.resvg.normalizer import normalize_svg_string
from svg2ooxml.render.rasterizer import Viewport


def test_viewport_from_tree_resolves_absolute_root_units() -> None:
    result = normalize_svg_string(
        """
        <svg xmlns="http://www.w3.org/2000/svg" width="1in" height="0.5in">
            <rect width="100%" height="100%"/>
        </svg>
        """
    )

    viewport = Viewport.from_tree(result.tree)

    assert viewport.width == 96
    assert viewport.height == 48
