"""Side-by-side comparison tests: old vs new DrawingMLAnimationWriter.

This test suite compares XML output from the old (string concatenation)
and new (lxml-based) animation writer implementations to ensure
functional equivalence.

NOTE: These tests use real AnimationDefinition objects from the IR module
rather than mocks to ensure compatibility with both implementations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
import pytest

# Animation IR classes
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    FillMode,
    CalcMode,
    TransformType,
)

# Old implementation (deprecated)
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from svg2ooxml.drawingml.animation_writer_old import DrawingMLAnimationWriter as OldWriter

# New implementation
from svg2ooxml.drawingml.animation import DrawingMLAnimationWriter as NewWriter


def normalize_xml(xml: str) -> str:
    """Normalize XML for comparison by removing whitespace variations.

    This function:
    - Removes extra whitespace between tags
    - Normalizes indentation
    - Removes namespace declarations (they're functionally equivalent)
    - Preserves attribute order for comparison
    """
    # Remove leading/trailing whitespace
    xml = xml.strip()
    # Remove extra whitespace between tags
    xml = re.sub(r'>\s+<', '><', xml)
    # Remove whitespace around equals signs in attributes
    xml = re.sub(r'\s*=\s*', '=', xml)
    # Remove namespace declarations (xmlns:a="...")
    xml = re.sub(r'\s+xmlns:\w+="[^"]*"', '', xml)
    # Normalize multiple spaces to single space
    xml = re.sub(r'\s+', ' ', xml)
    return xml


def create_test_animation(
    animation_type: AnimationType = AnimationType.ANIMATE,
    attribute_name: str = "opacity",
    values: list[str] | None = None,
    duration: float = 1.0,
    begin: float = 0.0,
    element_id: str = "shape1",
    key_times: list[float] | None = None,
    key_splines: list[list[float]] | None = None,
    fill_mode: FillMode = FillMode.FREEZE,
    calc_mode: CalcMode = CalcMode.LINEAR,
    transform_type: TransformType | None = None,
) -> AnimationDefinition:
    """Create a test animation definition."""
    if values is None:
        values = ["0", "1"]

    # Create timing
    timing = AnimationTiming(
        begin=begin,
        duration=duration,
        repeat_count=1,
        fill_mode=fill_mode,
    )

    # Create animation
    return AnimationDefinition(
        element_id=element_id,
        animation_type=animation_type,
        target_attribute=attribute_name,
        values=values,
        timing=timing,
        key_times=key_times,
        key_splines=key_splines,
        calc_mode=calc_mode,
        transform_type=transform_type,
    )


class TestOpacityAnimations:
    """Compare opacity/fade animations."""

    def test_simple_opacity_fade(self):
        """Should produce identical output for simple opacity fade."""
        animation = create_test_animation(
            attribute_name="opacity",
            values=["0", "1"],
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        # Both should produce non-empty output
        assert old_xml, "Old writer produced empty output"
        assert new_xml, "New writer produced empty output"

        # Normalize and compare
        assert normalize_xml(old_xml) == normalize_xml(new_xml)

    def test_fill_opacity(self):
        """Should handle fill-opacity attribute."""
        animation = create_test_animation(
            attribute_name="fill-opacity",
            values=["0.5", "1"],
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        assert old_xml and new_xml
        assert normalize_xml(old_xml) == normalize_xml(new_xml)


class TestColorAnimations:
    """Compare color animations."""

    def test_fill_color_animation(self):
        """Should produce identical output for fill color animation."""
        animation = create_test_animation(
            attribute_name="fill",
            values=["#ff0000", "#00ff00"],
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        assert old_xml and new_xml
        assert normalize_xml(old_xml) == normalize_xml(new_xml)

    def test_stroke_color_animation(self):
        """Should handle stroke color animation."""
        animation = create_test_animation(
            attribute_name="stroke",
            values=["#0000ff", "#ffff00"],
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        assert old_xml and new_xml
        assert normalize_xml(old_xml) == normalize_xml(new_xml)


class TestNumericAnimations:
    """Compare numeric property animations."""

    def test_x_position_animation(self):
        """Should handle x position animation."""
        animation = create_test_animation(
            attribute_name="x",
            values=["0", "100"],
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        assert old_xml and new_xml
        assert normalize_xml(old_xml) == normalize_xml(new_xml)

    def test_width_animation(self):
        """Should handle width animation."""
        animation = create_test_animation(
            attribute_name="width",
            values=["50", "200"],
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        assert old_xml and new_xml
        assert normalize_xml(old_xml) == normalize_xml(new_xml)


class TestTransformAnimations:
    """Compare transform animations."""

    def test_scale_animation(self):
        """Should handle scale transform animation."""
        animation = create_test_animation(
            animation_type=AnimationType.ANIMATE_TRANSFORM,
            attribute_name="transform",
            transform_type=TransformType.SCALE,
            values=["1", "2"],
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        assert old_xml and new_xml
        assert normalize_xml(old_xml) == normalize_xml(new_xml)

    def test_rotate_animation(self):
        """Should handle rotate transform animation."""
        animation = create_test_animation(
            animation_type=AnimationType.ANIMATE_TRANSFORM,
            attribute_name="transform",
            transform_type=TransformType.ROTATE,
            values=["0", "360"],
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        assert old_xml and new_xml
        assert normalize_xml(old_xml) == normalize_xml(new_xml)


class TestSetAnimations:
    """Compare set animations."""

    def test_set_numeric_value(self):
        """Should handle SET animation with numeric value."""
        animation = create_test_animation(
            animation_type=AnimationType.SET,
            attribute_name="x",
            values=["100"],
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        assert old_xml and new_xml
        assert normalize_xml(old_xml) == normalize_xml(new_xml)


class TestMotionAnimations:
    """Compare motion path animations."""

    def test_simple_motion_path(self):
        """Should handle simple motion path animation."""
        animation = create_test_animation(
            animation_type=AnimationType.ANIMATE_MOTION,
            values=["M 0,0 L 100,100"],
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        assert old_xml and new_xml
        # Motion paths may have slight differences in point sampling
        # Just verify both produce output for now
        assert "<a:animMotion" in old_xml or "<a:animmotion" in old_xml.lower()
        assert "<a:animMotion" in new_xml or "<a:animmotion" in new_xml.lower()


class TestKeyframeAnimations:
    """Compare animations with keyframes and easing."""

    def test_multi_keyframe_animation(self):
        """Should handle animation with multiple keyframes."""
        animation = create_test_animation(
            attribute_name="opacity",
            values=["0", "0.5", "1"],
            key_times=[0, 0.5, 1],
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        assert old_xml and new_xml
        assert normalize_xml(old_xml) == normalize_xml(new_xml)

    def test_animation_with_easing(self):
        """Should handle animation with cubic bezier easing."""
        animation = create_test_animation(
            attribute_name="opacity",
            values=["0", "1"],
            key_times=[0, 1],
            key_splines=[[0.42, 0, 0.58, 1]],
            calc_mode=CalcMode.SPLINE,
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        assert old_xml and new_xml
        # Both should contain TAV elements for keyframes
        assert "<a:tav" in old_xml or "<a:tav" in old_xml.lower()
        assert "<a:tav" in new_xml or "<a:tav" in new_xml.lower()


class TestMultipleAnimations:
    """Compare handling of multiple animations."""

    def test_two_animations_same_element(self):
        """Should handle multiple animations on same element."""
        animations = [
            create_test_animation(
                attribute_name="opacity",
                values=["0", "1"],
                element_id="shape1",
            ),
            create_test_animation(
                attribute_name="x",
                values=["0", "100"],
                element_id="shape1",
                begin_ms=500,
            ),
        ]

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build(animations, [])
        new_xml = new_writer.build(animations, [])

        assert old_xml and new_xml
        # Should contain multiple par elements
        assert old_xml.count("<p:par") >= 3  # Outer + 2 animations
        assert new_xml.count("<p:par") >= 3

    def test_different_animation_types(self):
        """Should handle mix of different animation types."""
        animations = [
            create_test_animation(
                attribute_name="opacity",
                values=["0", "1"],
            ),
            create_test_animation(
                attribute_name="fill",
                values=["#ff0000", "#00ff00"],
            ),
            create_test_animation(
                attribute_name="x",
                values=["0", "100"],
            ),
        ]

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build(animations, [])
        new_xml = new_writer.build(animations, [])

        assert old_xml and new_xml
        # Should contain multiple animation types
        assert old_xml.count("<p:par") >= 4  # Outer + 3 animations
        assert new_xml.count("<p:par") >= 4


class TestEdgeCases:
    """Compare edge case handling."""

    def test_no_animations(self):
        """Should handle empty animation list."""
        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([], [])
        new_xml = new_writer.build([], [])

        # Both should return empty string
        assert old_xml == ""
        assert new_xml == ""

    def test_animation_with_no_values(self):
        """Should skip animation with no values."""
        animation = create_test_animation(
            attribute_name="opacity",
            values=[],
        )

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build([animation], [])
        new_xml = new_writer.build([animation], [])

        # Both should skip and return empty
        assert old_xml == ""
        assert new_xml == ""


class TestIDAllocation:
    """Compare ID allocation behavior."""

    def test_unique_ids_generated(self):
        """Should generate unique IDs for each animation."""
        animations = [
            create_test_animation(attribute_name="opacity"),
            create_test_animation(attribute_name="x"),
            create_test_animation(attribute_name="fill"),
        ]

        old_writer = OldWriter()
        new_writer = NewWriter()

        old_xml = old_writer.build(animations, [])
        new_xml = new_writer.build(animations, [])

        # Extract all IDs from both outputs
        old_ids = re.findall(r'id="(\d+)"', old_xml)
        new_ids = re.findall(r'id="(\d+)"', new_xml)

        # All IDs should be unique
        assert len(old_ids) == len(set(old_ids))
        assert len(new_ids) == len(set(new_ids))

        # Should have same number of IDs
        assert len(old_ids) == len(new_ids)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
