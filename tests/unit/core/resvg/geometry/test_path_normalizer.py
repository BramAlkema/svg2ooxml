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


def test_path_primitives_apply_affine_transform_through_bridge() -> None:
    transform = Matrix(a=1.0, b=0.0, c=0.0, d=1.0, e=2.0, f=3.0)
    path = normalize_path("M 1 2 L 4 6", transform, None)

    primitives = path.to_primitives()

    assert primitives == (
        MoveTo(3.0, 5.0),
        LineTo(6.0, 9.0),
    )


def test_truncated_move_or_line_commands_do_not_raise() -> None:
    assert normalize_path("M 10", Matrix.identity(), None).to_primitives() == ()
    assert normalize_path("M 0 0 L 10", Matrix.identity(), None).to_primitives() == (
        MoveTo(0.0, 0.0),
    )
