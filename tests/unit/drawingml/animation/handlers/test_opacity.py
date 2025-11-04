"""Tests for opacity animation handler."""

import pytest
from unittest.mock import Mock
from lxml import etree

from svg2ooxml.drawingml.animation.handlers.opacity import OpacityAnimationHandler
from svg2ooxml.drawingml.animation.handlers.base import AnimationDefinition


def create_test_animation(**kwargs):
    """Helper to create mock animation with defaults."""
    animation = Mock(spec=AnimationDefinition)
    attribute_name = kwargs.get("attribute_name", "opacity")
    target_attribute = kwargs.get("target_attribute", attribute_name)
    animation.attribute_name = attribute_name
    animation.target_attribute = target_attribute
    animation.animation_type = kwargs.get("animation_type", None)
    animation.values = kwargs.get("values", ["0", "1"])
    animation.duration_ms = kwargs.get("duration_ms", 1000)
    animation.begin_ms = kwargs.get("begin_ms", 0)
    animation.fill_mode = kwargs.get("fill_mode", "freeze")
    animation.element_id = kwargs.get("element_id", "shape1")
    animation.key_times = kwargs.get("key_times", None)
    animation.key_splines = kwargs.get("key_splines", None)
    animation.additive = kwargs.get("additive", "replace")
    animation.accumulate = kwargs.get("accumulate", "none")
    return animation


class TestInit:
    """Test OpacityAnimationHandler initialization."""

    def test_init_with_dependencies(self):
        """Handler should accept all dependencies."""
        xml_builder = Mock()
        value_processor = Mock()
        tav_builder = Mock()
        unit_converter = Mock()

        handler = OpacityAnimationHandler(
            xml_builder, value_processor, tav_builder, unit_converter
        )

        assert handler._xml is xml_builder
        assert handler._processor is value_processor
        assert handler._tav is tav_builder
        assert handler._units is unit_converter


class TestCanHandle:
    """Test can_handle method."""

    def test_handles_opacity_attribute(self):
        """Should handle 'opacity' attribute."""
        handler = OpacityAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="opacity")

        assert handler.can_handle(animation) is True

    def test_handles_fill_opacity_attribute(self):
        """Should handle 'fill-opacity' attribute."""
        handler = OpacityAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="fill-opacity")

        assert handler.can_handle(animation) is True

    def test_handles_stroke_opacity_attribute(self):
        """Should handle 'stroke-opacity' attribute."""
        handler = OpacityAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="stroke-opacity")

        assert handler.can_handle(animation) is True

    def test_does_not_handle_color_attribute(self):
        """Should not handle color attributes."""
        handler = OpacityAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="fill")

        assert handler.can_handle(animation) is False

    def test_does_not_handle_transform_attribute(self):
        """Should not handle transform attributes."""
        handler = OpacityAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="transform")

        assert handler.can_handle(animation) is False

    def test_does_not_handle_numeric_attribute(self):
        """Should not handle numeric attributes."""
        handler = OpacityAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="x")

        assert handler.can_handle(animation) is False


class TestComputeTargetOpacity:
    """Test _compute_target_opacity helper."""

    def test_uses_last_value_when_values_provided(self):
        """Should use last value from animation values."""
        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=0.8)

        handler = OpacityAnimationHandler(Mock(), value_processor, Mock(), Mock())
        animation = create_test_animation(values=["0", "0.5", "0.8"])

        result = handler._compute_target_opacity(animation)

        assert result == "0.8"
        value_processor.parse_opacity.assert_called_once_with("0.8")

    def test_uses_single_value(self):
        """Should handle single-value animations."""
        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=1.0)

        handler = OpacityAnimationHandler(Mock(), value_processor, Mock(), Mock())
        animation = create_test_animation(values=["1"])

        result = handler._compute_target_opacity(animation)

        assert result == "1.0"

    def test_defaults_to_one_for_freeze_fill(self):
        """Should default to '1' when fill_mode is 'freeze' and no values."""
        handler = OpacityAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(values=[], fill_mode="freeze")

        result = handler._compute_target_opacity(animation)

        assert result == "1"

    def test_defaults_to_zero_for_remove_fill(self):
        """Should default to '0' when fill_mode is 'remove' and no values."""
        handler = OpacityAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(values=[], fill_mode="remove")

        result = handler._compute_target_opacity(animation)

        assert result == "0"

    def test_defaults_to_zero_for_other_fill_modes(self):
        """Should default to '0' for other fill modes."""
        handler = OpacityAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(values=[], fill_mode="auto")

        result = handler._compute_target_opacity(animation)

        assert result == "0"


class TestBuild:
    """Test build method."""

    def test_returns_string(self):
        """Should return XML string."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=1.0)

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())
        animation = create_test_animation()

        result = handler.build(animation, par_id=1, behavior_id=2)

        assert isinstance(result, str)
        assert result == "<p:par/>"

    def test_calls_build_behavior_core(self):
        """Should call build_behavior_core with correct arguments."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=1.0)

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())
        animation = create_test_animation(
            duration_ms=2000,
            element_id="shape123"
        )

        handler.build(animation, par_id=10, behavior_id=20)

        xml_builder.build_behavior_core.assert_called_once_with(
            behavior_id=20,
            duration_ms=2000,
            target_shape="shape123",
        )

    def test_calls_build_par_container(self):
        """Should call build_par_container with correct arguments."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=1.0)

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())
        animation = create_test_animation(
            duration_ms=3000,
            begin_ms=500
        )

        handler.build(animation, par_id=10, behavior_id=20)

        # Check par_container was called with correct args
        call_args = xml_builder.build_par_container.call_args
        assert call_args.kwargs["par_id"] == 10
        assert call_args.kwargs["duration_ms"] == 3000
        assert call_args.kwargs["delay_ms"] == 500

    def test_builds_anim_effect_with_fade(self):
        """Should build animEffect element with fade filter."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=0.5)

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())
        animation = create_test_animation(values=["0", "0.5"])

        handler.build(animation, par_id=1, behavior_id=2)

        # Check that child_xml passed to par_container contains fade
        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:animEffect>" in child_xml
        assert '<a:transition in="1" out="0"/>' in child_xml
        assert "<a:filter>" in child_xml
        assert '<a:fade opacity="0.5"/>' in child_xml
        assert "</a:animEffect>" in child_xml

    def test_includes_behavior_core_in_anim_effect(self):
        """Should include behavior core inside animEffect."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<BEHAVIOR_CORE/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=1.0)

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())
        animation = create_test_animation()

        handler.build(animation, par_id=1, behavior_id=2)

        # Check that behavior core is included
        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<BEHAVIOR_CORE/>" in child_xml

    def test_different_opacity_values(self):
        """Should handle different opacity values."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())

        # Test with 0.0
        value_processor.parse_opacity = Mock(return_value=0.0)
        animation = create_test_animation(values=["0"])
        handler.build(animation, par_id=1, behavior_id=2)
        child_xml = (
            xml_builder.build_par_container.call_args.kwargs.get("child_content")
            or xml_builder.build_par_container.call_args.kwargs["child_xml"]
        )
        assert '<a:fade opacity="0.0"/>' in child_xml

        # Test with 1.0
        value_processor.parse_opacity = Mock(return_value=1.0)
        animation = create_test_animation(values=["1"])
        handler.build(animation, par_id=1, behavior_id=2)
        child_xml = (
            xml_builder.build_par_container.call_args.kwargs.get("child_content")
            or xml_builder.build_par_container.call_args.kwargs["child_xml"]
        )
        assert '<a:fade opacity="1.0"/>' in child_xml

        # Test with 0.75
        value_processor.parse_opacity = Mock(return_value=0.75)
        animation = create_test_animation(values=["0.75"])
        handler.build(animation, par_id=1, behavior_id=2)
        child_xml = (
            xml_builder.build_par_container.call_args.kwargs.get("child_content")
            or xml_builder.build_par_container.call_args.kwargs["child_xml"]
        )
        assert '<a:fade opacity="0.75"/>' in child_xml


class TestIntegration:
    """Test integrated workflows."""

    def test_complete_opacity_animation_workflow(self):
        """Test complete workflow: check can_handle, then build."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par>complete</p:par>")

        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=1.0)

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())
        animation = create_test_animation(attribute_name="opacity")

        # First check if handler can handle
        assert handler.can_handle(animation) is True

        # Then build
        result = handler.build(animation, par_id=1, behavior_id=2)

        assert result == "<p:par>complete</p:par>"

    def test_fade_in_animation(self):
        """Test fade-in animation (0 → 1)."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=1.0)

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())
        animation = create_test_animation(values=["0", "1"])

        handler.build(animation, par_id=1, behavior_id=2)

        # Should use final value (1.0)
        value_processor.parse_opacity.assert_called_with("1")

    def test_fade_out_animation(self):
        """Test fade-out animation (1 → 0)."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=0.0)

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())
        animation = create_test_animation(values=["1", "0"])

        handler.build(animation, par_id=1, behavior_id=2)

        # Should use final value (0.0)
        value_processor.parse_opacity.assert_called_with("0")

    def test_multi_keyframe_opacity_animation(self):
        """Test opacity animation with multiple keyframes."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=0.8)

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())
        animation = create_test_animation(values=["0", "0.5", "0.3", "0.8"])

        handler.build(animation, par_id=1, behavior_id=2)

        # Should use final value (0.8)
        value_processor.parse_opacity.assert_called_with("0.8")


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_missing_element_id(self):
        """Should handle animation without element_id."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=1.0)

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())
        animation = create_test_animation()
        delattr(animation, "element_id")

        # Should not raise
        result = handler.build(animation, par_id=1, behavior_id=2)
        assert isinstance(result, str)

    def test_handles_empty_values_list(self):
        """Should handle empty values list."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        handler = OpacityAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(values=[])

        # Should use default opacity
        opacity = handler._compute_target_opacity(animation)
        assert opacity in ["0", "1"]

    def test_handles_zero_duration(self):
        """Should handle zero duration animations."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=1.0)

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())
        animation = create_test_animation(duration_ms=0)

        # Should not raise
        result = handler.build(animation, par_id=1, behavior_id=2)
        assert isinstance(result, str)

    def test_handles_large_par_and_behavior_ids(self):
        """Should handle large ID values."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_opacity = Mock(return_value=1.0)

        handler = OpacityAnimationHandler(xml_builder, value_processor, Mock(), Mock())
        animation = create_test_animation()

        # Should not raise with large IDs
        result = handler.build(animation, par_id=999999, behavior_id=888888)
        assert isinstance(result, str)
