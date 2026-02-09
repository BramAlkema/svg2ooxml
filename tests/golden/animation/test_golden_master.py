"""Golden master tests for animation timing XML output.

Each test generates timing XML via DrawingMLAnimationWriter and compares
against a checked-in golden master file. If a test fails, it means the
writer's output has changed — either intentionally (update the golden
master) or as a regression.

To update golden masters after intentional changes:
    python -m pytest tests/golden/animation/ --update-golden
"""

from __future__ import annotations

import pathlib

import pytest

from svg2ooxml.drawingml.animation.writer import DrawingMLAnimationWriter
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    TransformType,
)

from .compare_xml import xml_strings_equal

GOLDEN_DIR = pathlib.Path(__file__).parent


@pytest.fixture
def update_golden(request):
    return request.config.getoption("--update-golden", default=False)


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _build(animations, shape_ids=None):
    """Build timing XML via a fresh writer instance."""
    writer = DrawingMLAnimationWriter()
    return writer.build(
        animations, [], animated_shape_ids=shape_ids or ["shape1"]
    )


def _assert_golden(actual: str, golden_name: str, update: bool):
    """Compare actual output to golden master, optionally updating."""
    golden_path = GOLDEN_DIR / f"{golden_name}.xml"

    if update:
        golden_path.write_text(actual, encoding="utf-8")
        pytest.skip(f"Updated golden master: {golden_path.name}")

    assert golden_path.exists(), (
        f"Golden master not found: {golden_path}\n"
        "Run with --update-golden to create it."
    )

    expected = golden_path.read_text(encoding="utf-8")
    equal, diff = xml_strings_equal(actual, expected)
    assert equal, (
        f"Output differs from golden master {golden_name}.xml:\n{diff}\n\n"
        "Run with --update-golden to accept the new output."
    )


# ------------------------------------------------------------------ #
# Test cases                                                           #
# ------------------------------------------------------------------ #


class TestGoldenMaster:
    """Golden master regression tests for each animation type."""

    def test_opacity_fade_in(self, update_golden):
        actual = _build([
            AnimationDefinition(
                element_id="shape1",
                animation_type=AnimationType.ANIMATE,
                target_attribute="opacity",
                values=["0", "1"],
                timing=AnimationTiming(begin=0.0, duration=1.0),
            ),
        ])
        _assert_golden(actual, "opacity_fade_in", update_golden)

    def test_color_red_to_blue(self, update_golden):
        actual = _build([
            AnimationDefinition(
                element_id="shape1",
                animation_type=AnimationType.ANIMATE,
                target_attribute="fill",
                values=["#FF0000", "#0000FF"],
                timing=AnimationTiming(begin=0.0, duration=2.0),
            ),
        ])
        _assert_golden(actual, "color_red_to_blue", update_golden)

    def test_scale_uniform(self, update_golden):
        actual = _build([
            AnimationDefinition(
                element_id="shape1",
                animation_type=AnimationType.ANIMATE_TRANSFORM,
                target_attribute="transform",
                values=["1", "2"],
                timing=AnimationTiming(begin=0.0, duration=1.0),
                transform_type=TransformType.SCALE,
            ),
        ])
        _assert_golden(actual, "scale_uniform", update_golden)

    def test_rotate_90deg(self, update_golden):
        actual = _build([
            AnimationDefinition(
                element_id="shape1",
                animation_type=AnimationType.ANIMATE_TRANSFORM,
                target_attribute="transform",
                values=["0", "90"],
                timing=AnimationTiming(begin=0.0, duration=1.5),
                transform_type=TransformType.ROTATE,
            ),
        ])
        _assert_golden(actual, "rotate_90deg", update_golden)

    def test_set_visibility(self, update_golden):
        actual = _build([
            AnimationDefinition(
                element_id="shape1",
                animation_type=AnimationType.SET,
                target_attribute="visibility",
                values=["visible"],
                timing=AnimationTiming(begin=0.0, duration=0.001),
            ),
        ])
        _assert_golden(actual, "set_visibility", update_golden)

    def test_numeric_x(self, update_golden):
        actual = _build([
            AnimationDefinition(
                element_id="shape1",
                animation_type=AnimationType.ANIMATE,
                target_attribute="x",
                values=["0", "100"],
                timing=AnimationTiming(begin=0.0, duration=1.0),
            ),
        ])
        _assert_golden(actual, "numeric_x", update_golden)
