from __future__ import annotations

import pytest

from svg2ooxml.common.gradient_units import parse_gradient_coordinate


def test_contextless_userspace_percent_coordinate_uses_explicit_token() -> None:
    assert parse_gradient_coordinate(
        "50%",
        units="userSpaceOnUse",
        axis="x",
        default="0%",
    ) == pytest.approx(0.5)


def test_contextless_userspace_percent_default_still_applies_when_missing() -> None:
    assert parse_gradient_coordinate(
        None,
        units="userSpaceOnUse",
        axis="x",
        default="100%",
    ) == pytest.approx(1.0)


def test_contextless_userspace_absolute_units_still_resolve_to_px() -> None:
    assert parse_gradient_coordinate(
        "0.25in",
        units="userSpaceOnUse",
        axis="x",
        default="0%",
    ) == pytest.approx(24.0)
