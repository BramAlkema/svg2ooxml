from __future__ import annotations

import pytest

from svg2ooxml.core.resvg.geometry.matrix import Matrix
from svg2ooxml.core.resvg.geometry.path_normalizer import normalize_path
from svg2ooxml.core.resvg.geometry.primitives import LineTo, MoveTo


def test_rotated_elliptical_arc_flattens_to_declared_endpoint() -> None:
    path = normalize_path("M 10 0 A 30 10 45 0 1 50 40", Matrix.identity(), None)

    primitives = path.to_primitives(tolerance=0.5)

    assert isinstance(primitives[0], MoveTo)
    assert isinstance(primitives[-1], LineTo)
    assert primitives[-1].x == pytest.approx(50.0, abs=1e-6)
    assert primitives[-1].y == pytest.approx(40.0, abs=1e-6)
