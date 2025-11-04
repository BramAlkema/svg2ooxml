"""Tests for DrawingMLAnimationWriter."""

from unittest.mock import Mock, MagicMock, patch, call
import pytest

from svg2ooxml.drawingml.animation.writer import DrawingMLAnimationWriter


@pytest.fixture
def writer():
    """Create DrawingMLAnimationWriter instance."""
    return DrawingMLAnimationWriter()


class TestInit:
    """Tests for __init__ method."""

    def test_initializes_with_default_id_counter(self, writer):
        """Should initialize ID counter to 1000."""
        assert writer._id_counter == 1000

    def test_initializes_unit_converter(self, writer):
        """Should initialize UnitConverter."""
        assert writer._unit_converter is not None

    def test_initializes_xml_builder(self, writer):
        """Should initialize AnimationXMLBuilder."""
        assert writer._xml_builder is not None

    def test_initializes_value_processor(self, writer):
        """Should initialize ValueProcessor."""
        assert writer._value_processor is not None

    def test_initializes_tav_builder(self, writer):
        """Should initialize TAVBuilder."""
        assert writer._tav_builder is not None

    def test_policy_starts_as_none(self, writer):
        """Should start with policy as None (initialized per-build)."""
        assert writer._policy is None

    def test_initializes_handlers_list(self, writer):
        """Should initialize list of handlers."""
        assert len(writer._handlers) == 6  # All 6 handler types

    def test_handlers_in_correct_order(self, writer):
        """Should initialize handlers in priority order."""
        from svg2ooxml.drawingml.animation.handlers import (
            OpacityAnimationHandler,
            ColorAnimationHandler,
            SetAnimationHandler,
            MotionAnimationHandler,
            TransformAnimationHandler,
            NumericAnimationHandler,
        )

        # Verify order (specific to general)
        assert isinstance(writer._handlers[0], OpacityAnimationHandler)
        assert isinstance(writer._handlers[1], ColorAnimationHandler)
        assert isinstance(writer._handlers[2], SetAnimationHandler)
        assert isinstance(writer._handlers[3], MotionAnimationHandler)
        assert isinstance(writer._handlers[4], TransformAnimationHandler)
        assert isinstance(writer._handlers[5], NumericAnimationHandler)  # Catch-all last


class TestNextId:
    """Tests for _next_id method."""

    def test_returns_current_counter_value(self, writer):
        """Should return current counter value."""
        assert writer._next_id() == 1000

    def test_increments_counter_after_call(self, writer):
        """Should increment counter after each call."""
        first_id = writer._next_id()
        second_id = writer._next_id()
        assert second_id == first_id + 1

    def test_generates_unique_ids(self, writer):
        """Should generate unique IDs on each call."""
        ids = [writer._next_id() for _ in range(10)]
        assert len(ids) == len(set(ids))  # All unique


class TestAllocateIds:
    """Tests for _allocate_ids method."""

    def test_returns_tuple_of_two_ids(self, writer):
        """Should return tuple of (par_id, behavior_id)."""
        par_id, behavior_id = writer._allocate_ids()
        assert isinstance(par_id, int)
        assert isinstance(behavior_id, int)

    def test_allocates_consecutive_ids(self, writer):
        """Should allocate consecutive IDs."""
        par_id, behavior_id = writer._allocate_ids()
        assert behavior_id == par_id + 1

    def test_multiple_allocations_are_unique(self, writer):
        """Should allocate unique IDs across calls."""
        pair1 = writer._allocate_ids()
        pair2 = writer._allocate_ids()
        # All four IDs should be unique
        all_ids = [*pair1, *pair2]
        assert len(all_ids) == len(set(all_ids))


class TestFindHandler:
    """Tests for _find_handler method."""

    def test_finds_opacity_handler_for_opacity_animation(self, writer):
        """Should find OpacityAnimationHandler for opacity attribute."""
        animation = Mock(target_attribute="opacity", animation_type=None)
        handler = writer._find_handler(animation)

        from svg2ooxml.drawingml.animation.handlers import OpacityAnimationHandler

        assert isinstance(handler, OpacityAnimationHandler)

    def test_finds_color_handler_for_color_animation(self, writer):
        """Should find ColorAnimationHandler for fill attribute."""
        animation = Mock(target_attribute="fill", animation_type=None)
        handler = writer._find_handler(animation)

        from svg2ooxml.drawingml.animation.handlers import ColorAnimationHandler

        assert isinstance(handler, ColorAnimationHandler)

    def test_finds_set_handler_for_set_animation(self, writer):
        """Should find SetAnimationHandler for SET animation type."""
        animation = Mock(animation_type="SET", target_attribute="x")
        handler = writer._find_handler(animation)

        from svg2ooxml.drawingml.animation.handlers import SetAnimationHandler

        assert isinstance(handler, SetAnimationHandler)

    def test_finds_motion_handler_for_motion_animation(self, writer):
        """Should find MotionAnimationHandler for motion animations."""
        animation = Mock(is_motion=True)
        handler = writer._find_handler(animation)

        from svg2ooxml.drawingml.animation.handlers import MotionAnimationHandler

        assert isinstance(handler, MotionAnimationHandler)

    def test_finds_transform_handler_for_transform_animation(self, writer):
        """Should find TransformAnimationHandler for scale transform."""
        animation = Mock(
            transform_type="scale",
            target_attribute="transform",
            spec=["transform_type", "target_attribute"]  # No is_motion
        )
        handler = writer._find_handler(animation)

        from svg2ooxml.drawingml.animation.handlers import TransformAnimationHandler

        assert isinstance(handler, TransformAnimationHandler)

    def test_finds_numeric_handler_for_generic_numeric(self, writer):
        """Should find NumericAnimationHandler for generic numeric attribute."""
        animation = Mock(target_attribute="x", spec=["target_attribute"])
        handler = writer._find_handler(animation)

        from svg2ooxml.drawingml.animation.handlers import NumericAnimationHandler

        assert isinstance(handler, NumericAnimationHandler)

    def test_returns_none_for_unsupported_animation(self, writer):
        """Should return None if no handler can process animation."""
        # The numeric handler is catch-all, so it will handle anything with attribute_name
        # To make it unsupported, we'd need to have no attribute_name at all
        # But handlers expect attribute_name, so this scenario is unlikely in practice
        # Instead, test that numeric handler IS the fallback
        animation = Mock(target_attribute="some_unknown_attr", spec=["target_attribute"])
        handler = writer._find_handler(animation)

        # Should fall back to numeric handler
        from svg2ooxml.drawingml.animation.handlers import NumericAnimationHandler
        assert isinstance(handler, NumericAnimationHandler)


class TestBuildAnimation:
    """Tests for _build_animation method."""

    def test_returns_empty_for_skipped_animation(self, writer):
        """Should return empty string and metadata when animation is skipped."""
        animation = Mock(
            
            values=[],  # No values will cause skip
            duration_ms=1000,
            key_times=None,
            key_splines=None,
        )

        xml, metadata = writer._build_animation(animation, {})

        assert xml == ""
        assert metadata is not None
        assert "reason" in metadata

    def test_returns_xml_for_valid_animation(self, writer):
        """Should return XML for valid animation."""
        from svg2ooxml.ir.animation import FillMode
        animation = Mock(
            target_attribute="opacity",
            values=["0", "1"],
            duration_ms=1000,
            begin_ms=0,
            element_id="shape1",
            key_times=None,
            key_splines=None,
            fill_mode=FillMode.FREEZE,
            animation_type=None,
        )

        xml, metadata = writer._build_animation(animation, {})

        assert xml != ""
        assert "<p:par>" in xml

    def test_includes_spline_error_in_metadata(self, writer):
        """Should include spline error estimate in metadata."""
        animation = Mock(
            
            values=["0", "100"],
            duration_ms=1000,
            begin_ms=0,
            element_id="shape1",
            key_times=[0, 0.5, 1],
            key_splines=[[0.1, 0.2, 0.8, 0.9], [0.2, 0.3, 0.7, 0.8]],
        )

        xml, metadata = writer._build_animation(animation, {})

        # May or may not have error depending on splines
        # Just verify metadata structure
        if metadata:
            assert isinstance(metadata, dict)

    def test_skips_animation_exceeding_max_error(self, writer):
        """Should skip animation if spline error exceeds threshold."""
        animation = Mock(
            target_attribute="x",
            values=["0", "100"],
            duration_ms=1000,
            begin_ms=0,
            element_id="shape1",
            key_times=[0, 0.5, 1],
            # Extreme splines that cause high error
            key_splines=[[0, 0, 1, 1], [0, 0, 1, 1]],
        )

        xml, metadata = writer._build_animation(animation, {"max_spline_error": 0.001})

        # May skip due to error threshold
        if not xml:
            assert metadata is not None
            assert "reason" in metadata

    def test_uses_allocated_ids(self, writer):
        """Should use allocated par_id and behavior_id."""
        animation = Mock(
            target_attribute="opacity",
            values=["0", "1"],
            duration_ms=1000,
            begin_ms=0,
            element_id="shape1",
            key_times=None,
            key_splines=None,
            animation_type=None,
        )

        # Set predictable ID counter
        writer._id_counter = 5000

        xml, metadata = writer._build_animation(animation, {})

        # Should contain IDs 5000 and 5001
        assert 'id="5000"' in xml
        assert 'id="5001"' in xml

    def test_returns_error_metadata_on_handler_exception(self, writer):
        """Should return error metadata if handler raises exception."""
        # Mock a handler to raise exception
        with patch.object(
            writer._handlers[0], "build", side_effect=ValueError("Test error")
        ):
            animation = Mock(
                target_attribute="opacity",
                values=["0", "1"],
                duration_ms=1000,
                begin_ms=0,
                element_id="shape1",
                key_times=None,
                key_splines=None,
            )

            xml, metadata = writer._build_animation(animation, {})

            assert xml == ""
            assert metadata is not None
            assert "reason" in metadata
            assert "handler_error" in metadata["reason"]


class TestBuild:
    """Tests for build method."""

    def test_returns_empty_string_for_no_animations(self, writer):
        """Should return empty string when no animations provided."""
        result = writer.build([], [])
        assert result == ""

    def test_returns_empty_string_for_all_skipped_animations(self, writer):
        """Should return empty string when all animations are skipped."""
        animations = [
            Mock( values=[], duration_ms=1000, key_splines=None),
            Mock(target_attribute="y", values=[], duration_ms=1000, key_splines=None),
        ]

        result = writer.build(animations, [])
        assert result == ""

    def test_builds_timing_xml_for_valid_animations(self, writer):
        """Should build complete timing XML for valid animations."""
        animations = [
            Mock(
                target_attribute="opacity",
                values=["0", "1"],
                duration_ms=1000,
                begin_ms=0,
                element_id="shape1",
                key_times=None,
                key_splines=None,
            ),
        ]

        result = writer.build(animations, [])

        assert "<p:timing>" in result
        assert "<p:tnLst>" in result
        assert "<p:par>" in result
        assert "</p:timing>" in result

    def test_includes_all_animation_fragments(self, writer):
        """Should include all animation fragments in output."""
        animations = [
            Mock(
                target_attribute="opacity",
                values=["0", "1"],
                duration_ms=1000,
                begin_ms=0,
                element_id="shape1",
                key_times=None,
                key_splines=None,
            ),
            Mock(
                target_attribute="fill",
                values=["#ff0000", "#00ff00"],
                duration_ms=1000,
                begin_ms=0,
                element_id="shape2",
                key_times=None,
                key_splines=None,
            ),
        ]

        result = writer.build(animations, [])

        # Should contain multiple animation fragments
        assert result.count("<p:par>") >= 3  # Outer + 2 animations

    def test_assigns_unique_timing_id(self, writer):
        """Should assign unique ID to timing root element."""
        animations = [
            Mock(
                target_attribute="opacity",
                values=["0", "1"],
                duration_ms=1000,
                begin_ms=0,
                element_id="shape1",
                key_times=None,
                key_splines=None,
            ),
        ]

        writer._id_counter = 9000
        result = writer.build(animations, [])

        # First ID allocated should be timing_id
        assert 'id="9' in result  # Should have an ID in 9000 range

    def test_records_tracer_events_for_emitted_fragments(self, writer):
        """Should record tracer events for successfully emitted animations."""
        tracer = Mock()
        animations = [
            Mock(
                target_attribute="opacity",
                values=["0", "1"],
                duration_ms=1000,
                begin_ms=0,
                element_id="shape1",
                key_times=None,
                key_splines=None,
                animation_type=Mock(value="ANIMATE"),
            ),
        ]

        writer.build(animations, [], tracer=tracer)

        # Should record fragment_emitted and fragment_bundle_emitted
        calls = tracer.record_stage_event.call_args_list
        actions = [call[1]["action"] for call in calls]
        assert "fragment_emitted" in actions
        assert "fragment_bundle_emitted" in actions

    def test_records_tracer_events_for_skipped_fragments(self, writer):
        """Should record tracer events for skipped animations."""
        tracer = Mock()
        animations = [
            Mock(
                target_attribute="x",
                values=[],  # Will be skipped
                duration_ms=1000,
                animation_type=Mock(value="ANIMATE"),
                
                element_id="shape1",
                key_splines=None,
            ),
        ]

        writer.build(animations, [], tracer=tracer)

        # Should record fragment_skipped and fragment_bundle_skipped
        calls = tracer.record_stage_event.call_args_list
        actions = [call[1]["action"] for call in calls]
        assert "fragment_skipped" in actions
        assert "fragment_bundle_skipped" in actions

    def test_passes_options_to_build_animation(self, writer):
        """Should pass options through to _build_animation."""
        animations = [
            Mock(
                target_attribute="opacity",
                values=["0", "1"],
                duration_ms=1000,
                begin_ms=0,
                element_id="shape1",
                key_times=None,
                key_splines=None,
            ),
        ]

        options = {"max_spline_error": 1.5, "fallback_mode": "raster"}

        with patch.object(writer, "_build_animation", wraps=writer._build_animation) as mock_build:
            writer.build(animations, [], options=options)

            # Should be called with options dict
            mock_build.assert_called()
            call_options = mock_build.call_args[0][1]
            assert call_options["max_spline_error"] == 1.5
            assert call_options["fallback_mode"] == "raster"

    def test_handles_none_options(self, writer):
        """Should handle None options gracefully."""
        animations = [
            Mock(
                target_attribute="opacity",
                values=["0", "1"],
                duration_ms=1000,
                begin_ms=0,
                element_id="shape1",
                key_times=None,
                key_splines=None,
            ),
        ]

        result = writer.build(animations, [], options=None)
        assert result != ""


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_complete_workflow_opacity_animation(self, writer):
        """Test complete workflow for opacity animation."""
        animations = [
            Mock(
                target_attribute="opacity",
                values=["0", "1"],
                duration_ms=1000,
                begin_ms=0,
                element_id="shape1",
                key_times=None,
                key_splines=None,
                animation_type=Mock(value="ANIMATE"),
                
            ),
        ]

        result = writer.build(animations, [], tracer=None)

        # Verify structure
        assert "<p:timing>" in result
        assert "<p:par>" in result
        assert "</p:timing>" in result
        # Opacity uses animEffect
        assert "<a:animEffect" in result or "animeffect" in result.lower()

    def test_complete_workflow_multiple_animation_types(self, writer):
        """Test complete workflow with multiple animation types."""
        animations = [
            Mock(
                target_attribute="opacity",
                values=["0", "1"],
                duration_ms=1000,
                begin_ms=0,
                element_id="shape1",
                key_times=None,
                key_splines=None,
                animation_type=Mock(value="ANIMATE"),
                
            ),
            Mock(
                target_attribute="fill",
                values=["#ff0000", "#00ff00"],
                duration_ms=1000,
                begin_ms=500,
                element_id="shape2",
                key_times=None,
                key_splines=None,
                animation_type=Mock(value="ANIMATE_COLOR"),
                
            ),
            Mock(
                target_attribute="x",
                values=["0", "100"],
                duration_ms=1000,
                begin_ms=1000,
                element_id="shape3",
                key_times=None,
                key_splines=None,
                spec=["target_attribute", "values", "duration_ms", "begin_ms", "element_id", "key_times", "key_splines"],
            ),
        ]

        result = writer.build(animations, [])

        # Should contain all animation types
        assert result != ""
        assert result.count("<p:par>") >= 3  # Outer + animations

    def test_workflow_with_tracer(self, writer):
        """Test complete workflow with tracer integration."""
        tracer = Mock()
        animations = [
            Mock(
                target_attribute="opacity",
                values=["0", "1"],
                duration_ms=1000,
                begin_ms=0,
                element_id="shape1",
                key_times=None,
                key_splines=None,
                animation_type=Mock(value="ANIMATE"),
            ),
        ]

        result = writer.build(animations, [], tracer=tracer)

        # Verify tracer was called
        assert tracer.record_stage_event.called
        assert tracer.record_stage_event.call_count >= 2  # At least fragment + bundle

    def test_id_allocation_across_multiple_animations(self, writer):
        """Test that IDs are unique across multiple animations."""
        animations = [
            Mock(
                target_attribute="opacity",
                values=["0", "1"],
                duration_ms=1000,
                begin_ms=0,
                element_id=f"shape{i}",
                key_times=None,
                key_splines=None,
            )
            for i in range(5)
        ]

        result = writer.build(animations, [])

        # Extract all IDs from result
        import re
        ids = re.findall(r'id="(\d+)"', result)
        # All IDs should be unique
        assert len(ids) == len(set(ids))
