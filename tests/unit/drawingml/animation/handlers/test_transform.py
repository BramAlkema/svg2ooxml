"""Tests for transform animation handler."""

import pytest
from unittest.mock import Mock, call
from lxml import etree

from svg2ooxml.drawingml.animation.handlers.transform import TransformAnimationHandler
from svg2ooxml.drawingml.animation.handlers.base import AnimationDefinition


def create_test_animation(**kwargs):
    """Helper to create mock animation with defaults."""
    animation = Mock(spec=AnimationDefinition)
    animation.transform_type = kwargs.get("transform_type", "scale")
    attribute_name = kwargs.get("attribute_name", "transform")
    target_attribute = kwargs.get("target_attribute", attribute_name)
    animation.attribute_name = attribute_name
    animation.target_attribute = target_attribute
    animation.animation_type = kwargs.get("animation_type", None)
    animation.values = kwargs.get("values", ["1", "2"])
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
    """Test TransformAnimationHandler initialization."""

    def test_init_with_dependencies(self):
        """Handler should accept all dependencies."""
        xml_builder = Mock()
        value_processor = Mock()
        tav_builder = Mock()
        unit_converter = Mock()

        handler = TransformAnimationHandler(
            xml_builder, value_processor, tav_builder, unit_converter
        )

        assert handler._xml is xml_builder
        assert handler._processor is value_processor
        assert handler._tav is tav_builder
        assert handler._units is unit_converter


class TestCanHandle:
    """Test can_handle method."""

    def test_handles_scale_transform(self):
        """Should handle scale transform."""
        handler = TransformAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(transform_type="scale")

        assert handler.can_handle(animation) is True

    def test_handles_rotate_transform(self):
        """Should handle rotate transform."""
        handler = TransformAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(transform_type="rotate")

        assert handler.can_handle(animation) is True

    def test_handles_translate_transform(self):
        """Should handle translate transform."""
        handler = TransformAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(transform_type="translate")

        assert handler.can_handle(animation) is True

    def test_handles_matrix_transform(self):
        """Should handle matrix transform when reducible."""
        handler = TransformAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(transform_type="matrix")

        assert handler.can_handle(animation) is True

    def test_does_not_handle_missing_transform_type(self):
        """Should not handle animations without transform_type."""
        handler = TransformAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation()
        delattr(animation, "transform_type")

        assert handler.can_handle(animation) is False

    def test_does_not_handle_unknown_transform_type(self):
        """Should not handle unknown transform types."""
        handler = TransformAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(transform_type="skew")

        assert handler.can_handle(animation) is False


class TestBuild:
    """Test build method dispatch."""

    def test_dispatches_to_scale_for_scale_transform(self):
        """Should dispatch to _build_scale_animation for scale."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_scale_pair = Mock(return_value=(1.0, 1.0))

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(transform_type="scale")

        result = handler.build(animation, par_id=1, behavior_id=2)

        # Should call parse_scale_pair
        assert value_processor.parse_scale_pair.called
        assert isinstance(result, str)

    def test_dispatches_to_rotate_for_rotate_transform(self):
        """Should dispatch to _build_rotate_animation for rotate."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_angle = Mock(return_value=0.0)
        value_processor.format_ppt_angle = Mock(return_value="0")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(transform_type="rotate", values=["0", "360"])

        result = handler.build(animation, par_id=1, behavior_id=2)

        # Should call parse_angle
        assert value_processor.parse_angle.called
        assert isinstance(result, str)

    def test_builds_translate_animation(self):
        """Should build animMotion element for translate."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_translation_pair = Mock(side_effect=[(0.0, 0.0), (10.0, 20.0)])

        tav_builder = Mock()

        def to_emu(value, axis):
            factor = 1000 if axis == "x" else 2000
            return value * factor

        unit_converter = Mock()
        unit_converter.to_emu = Mock(side_effect=to_emu)

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, unit_converter)
        animation = create_test_animation(transform_type="translate", values=["0 0", "10 20"])

        handler.build(animation, par_id=5, behavior_id=6)

        # Verify translation values were parsed
        assert value_processor.parse_translation_pair.call_args_list == [
            call("0 0"),
            call("10 20"),
        ]

        # Verify EMU conversion called with delta values
        assert unit_converter.to_emu.call_args_list == [
            call(10.0, axis="x"),
            call(20.0, axis="y"),
        ]

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:animMotion>" in child_xml
        assert "<a:by" in child_xml
        expected_x = int(round(to_emu(10.0, axis="x")))
        expected_y = int(round(to_emu(20.0, axis="y")))
        assert f'<a:by x="{expected_x}" y="{expected_y}"/>' in child_xml

    def test_builds_matrix_translation_animation(self):
        """Should reduce matrix translation to animMotion."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        unit_converter = Mock()
        unit_converter.to_emu = Mock(side_effect=lambda value, axis: value * 1000)

        handler = TransformAnimationHandler(xml_builder, Mock(), Mock(), unit_converter)
        animation = create_test_animation(
            transform_type="matrix",
            values=["1 0 0 1 0 0", "1 0 0 1 15 5"],
        )

        handler.build(animation, par_id=7, behavior_id=8)

        xml_builder.build_behavior_core.assert_called_once()
        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:animMotion>" in child_xml
        assert '<a:by x="15000" y="5000"/>' in child_xml

    def test_builds_matrix_scale_animation(self):
        """Should reduce matrix scale to animScale."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_tav_list_container = Mock(return_value=etree.fromstring("<a:tavLst xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'/>"))
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, Mock(), tav_builder, Mock())
        animation = create_test_animation(
            transform_type="matrix",
            values=["2 0 0 2 0 0", "3 0 0 3 0 0"],
        )

        handler.build(animation, par_id=9, behavior_id=10)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:animScale>" in child_xml
        assert '<a:pt x="2.0" y="2.0"/>' in child_xml
        assert '<a:pt x="3.0" y="3.0"/>' in child_xml

    def test_builds_matrix_rotate_animation(self):
        """Should reduce matrix rotation to animRot."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, Mock(), tav_builder, Mock())
        rotation_matrix = "0.8660254 0.5 -0.5 0.8660254 0 0"  # ≈ rotate(30)
        animation = create_test_animation(
            transform_type="matrix",
            values=[rotation_matrix, "1 0 0 1 0 0"],
        )

        handler.build(animation, par_id=11, behavior_id=12)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:animRot>" in child_xml
        assert 'a:by' in child_xml

    def test_matrix_with_mixed_components_returns_empty(self):
        """Should skip matrix animations that combine multiple components."""
        handler = TransformAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(
            transform_type="matrix",
            values=["2 0 0 2 5 5"],
        )

        result = handler.build(animation, par_id=13, behavior_id=14)

        assert result == ""

    def test_inserts_origin_for_single_translate_value(self):
        """Should add origin point when only a single translate value is provided."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_translation_pair = Mock(return_value=(15.0, -5.0))

        unit_converter = Mock()
        unit_converter.to_emu = Mock(side_effect=lambda value, axis: value * 1000)

        handler = TransformAnimationHandler(xml_builder, value_processor, Mock(), unit_converter)
        animation = create_test_animation(transform_type="translate", values=["15 -5"])

        handler.build(animation, par_id=2, behavior_id=3)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert '<a:by x="15000" y="-5000"/>' in child_xml

    def test_returns_empty_for_missing_transform_type(self):
        """Should return empty string if transform_type missing."""
        handler = TransformAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation()
        delattr(animation, "transform_type")

        result = handler.build(animation, par_id=1, behavior_id=2)

        assert result == ""


class TestScaleAnimation:
    """Test scale animation building."""

    def test_builds_anim_scale_element(self):
        """Should build animScale element."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_scale_pair = Mock(side_effect=[(1.0, 1.0), (2.0, 2.0)])

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(transform_type="scale", values=["1", "2"])

        handler.build(animation, par_id=1, behavior_id=2)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:animScale>" in child_xml
        assert "<a:from>" in child_xml
        assert '<a:pt x="1.0" y="1.0"/>' in child_xml
        assert "<a:to>" in child_xml
        assert '<a:pt x="2.0" y="2.0"/>' in child_xml
        assert "</a:animScale>" in child_xml

    def test_parses_from_and_to_scale_values(self):
        """Should parse first and last scale values."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_scale_pair = Mock(return_value=(1.0, 1.0))

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["1", "1.5", "2"])

        handler._build_scale_animation(animation, 1, 2)

        # Should parse each value exactly once
        assert value_processor.parse_scale_pair.call_count == 3
        value_processor.parse_scale_pair.assert_any_call("1")
        value_processor.parse_scale_pair.assert_any_call("2")

    def test_includes_tav_list_for_multi_keyframe(self):
        """Should include TAV list for multi-keyframe scale."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_tav_list_container = Mock(return_value=etree.fromstring("<a:tavLst xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'><a:tav tm='25000'/></a:tavLst>"))
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_scale_pair = Mock(side_effect=[
            (1.0, 1.0), (2.0, 2.0),  # from/to
            (1.0, 1.0), (1.5, 1.5), (2.0, 2.0)  # TAV list
        ])

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=(["<tav1/>", "<tav2/>"], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["1", "1.5", "2"])

        handler._build_scale_animation(animation, 1, 2)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:tavLst" in child_xml
        assert '<a:tav tm="25000"/>' in child_xml
        assert '<a:tav tm="25000"/>' in child_xml

    def test_returns_empty_for_no_values(self):
        """Should return empty string if no values."""
        handler = TransformAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(values=[])

        result = handler._build_scale_animation(animation, 1, 2)

        assert result == ""


class TestRotateAnimation:
    """Test rotate animation building."""

    def test_builds_anim_rot_element(self):
        """Should build animRot element."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_angle = Mock(side_effect=[0.0, 360.0])
        value_processor.format_ppt_angle = Mock(return_value="21600000")  # 360 * 60000

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(transform_type="rotate", values=["0", "360"])

        handler.build(animation, par_id=1, behavior_id=2)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:animRot>" in child_xml
        assert '<a:by val="21600000"/>' in child_xml
        assert "</a:animRot>" in child_xml

    def test_calculates_rotation_delta(self):
        """Should calculate rotation delta correctly."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_angle = Mock(side_effect=[45.0, 90.0])
        value_processor.format_ppt_angle = Mock(return_value="2700000")  # 45 * 60000

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(transform_type="rotate", values=["45", "90"])

        handler._build_rotate_animation(animation, 1, 2)

        # Should calculate delta: 90 - 45 = 45 degrees
        value_processor.format_ppt_angle.assert_called_with(45.0)

    def test_includes_tav_list_for_multi_keyframe(self):
        """Should include TAV list for multi-keyframe rotate."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_tav_list_container = Mock(return_value=etree.fromstring("<a:tavLst xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'><a:tav tm='25000'/></a:tavLst>"))
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_angle = Mock(side_effect=[
            0.0, 360.0,  # from/to
            0.0, 180.0, 360.0  # TAV list
        ])
        value_processor.format_ppt_angle = Mock(return_value="21600000")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=(["<tav1/>", "<tav2/>"], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(transform_type="rotate", values=["0", "180", "360"])

        handler._build_rotate_animation(animation, 1, 2)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:tavLst" in child_xml
        assert '<a:tav tm="25000"/>' in child_xml

    def test_returns_empty_for_no_values(self):
        """Should return empty string if no values."""
        handler = TransformAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(transform_type="rotate", values=[])

        result = handler._build_rotate_animation(animation, 1, 2)

        assert result == ""


class TestBuildScaleTAVList:
    """Test _build_scale_tav_list helper."""

    def test_returns_empty_for_two_values(self):
        """Should return empty for simple two-value animation."""
        tav_builder = Mock()

        handler = TransformAnimationHandler(Mock(), Mock(), tav_builder, Mock())
        animation = create_test_animation(values=["1", "2"], key_times=None)
        scale_pairs = [(1.0, 1.0), (2.0, 2.0)]

        tav_elements, needs_ns = handler._build_scale_tav_list(animation, scale_pairs)

        assert tav_elements == []
        assert needs_ns is False

    def test_builds_tav_list_for_three_values(self):
        """Should build TAV list for three+ values."""
        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=(["<tav1/>"], False))

        handler = TransformAnimationHandler(Mock(), Mock(), tav_builder, Mock())
        animation = create_test_animation(values=["1", "1.5", "2"])
        scale_pairs = [(1.0, 1.0), (1.5, 1.5), (2.0, 2.0)]

        tav_elements, needs_ns = handler._build_scale_tav_list(animation, scale_pairs)

        # Should call tav_builder with formatted scale strings
        call_args = tav_builder.build_tav_list.call_args
        assert call_args.kwargs["values"] == ["1.0 1.0", "1.5 1.5", "2.0 2.0"]

    def test_uses_point_formatter(self):
        """Should use format_point_value formatter."""
        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(Mock(), Mock(), tav_builder, Mock())
        animation = create_test_animation(values=["1", "2"])

        # Force TAV list build with explicit key_times
        animation.key_times = [0.0, 1.0]
        scale_pairs = [(1.0, 1.0), (2.0, 2.0)]
        handler._build_scale_tav_list(animation, scale_pairs)

        # Verify formatter is format_point_value
        call_args = tav_builder.build_tav_list.call_args
        formatter = call_args.kwargs["value_formatter"]
        assert formatter.__name__ == "format_point_value"


class TestBuildRotateTAVList:
    """Test _build_rotate_tav_list helper."""

    def test_returns_empty_for_two_values(self):
        """Should return empty for simple two-value animation."""
        tav_builder = Mock()

        handler = TransformAnimationHandler(Mock(), Mock(), tav_builder, Mock())
        animation = create_test_animation(transform_type="rotate", values=["0", "360"], key_times=None)

        angles = [0.0, 360.0]
        tav_elements, needs_ns = handler._build_rotate_tav_list(animation, angles, 0.0)

        assert tav_elements == []
        assert needs_ns is False

    def test_builds_tav_list_with_cumulative_deltas(self):
        """Should build TAV list with cumulative angle deltas."""
        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=(["<tav1/>"], False))

        handler = TransformAnimationHandler(Mock(), Mock(), tav_builder, Mock())
        animation = create_test_animation(transform_type="rotate", values=["0", "180", "360"])

        angles = [0.0, 180.0, 360.0]
        tav_elements, needs_ns = handler._build_rotate_tav_list(animation, angles, 0.0)

        # Should call tav_builder with deltas from start
        call_args = tav_builder.build_tav_list.call_args
        assert call_args.kwargs["values"] == ["0.0", "180.0", "360.0"]

    def test_uses_angle_formatter(self):
        """Should use format_angle_value formatter."""
        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(Mock(), Mock(), tav_builder, Mock())
        animation = create_test_animation(transform_type="rotate", values=["0", "360"])

        # Force TAV list build with explicit key_times
        animation.key_times = [0.0, 1.0]
        angles = [0.0, 360.0]
        handler._build_rotate_tav_list(animation, angles, 0.0)

        # Verify formatter is format_angle_value
        call_args = tav_builder.build_tav_list.call_args
        formatter = call_args.kwargs["value_formatter"]
        assert formatter.__name__ == "format_angle_value"


class TestIntegration:
    """Test integrated workflows."""

    def test_complete_scale_workflow(self):
        """Test complete scale animation workflow."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par>complete</p:par>")

        value_processor = Mock()
        value_processor.parse_scale_pair = Mock(side_effect=[(1.0, 1.0), (2.0, 2.0)])

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(transform_type="scale")

        assert handler.can_handle(animation) is True
        result = handler.build(animation, par_id=1, behavior_id=2)
        assert result == "<p:par>complete</p:par>"

    def test_complete_rotate_workflow(self):
        """Test complete rotate animation workflow."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par>complete</p:par>")

        value_processor = Mock()
        value_processor.parse_angle = Mock(side_effect=[0.0, 360.0])
        value_processor.format_ppt_angle = Mock(return_value="21600000")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(transform_type="rotate")

        assert handler.can_handle(animation) is True
        result = handler.build(animation, par_id=1, behavior_id=2)
        assert result == "<p:par>complete</p:par>"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_single_scale_value(self):
        """Should handle scale animation with single value."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_scale_pair = Mock(return_value=(2.0, 2.0))

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["2"])

        result = handler._build_scale_animation(animation, 1, 2)
        assert isinstance(result, str)

    def test_handles_single_rotate_value(self):
        """Should handle rotate animation with single value."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_angle = Mock(return_value=45.0)
        value_processor.format_ppt_angle = Mock(return_value="0")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(transform_type="rotate", values=["45"])

        result = handler._build_rotate_animation(animation, 1, 2)
        assert isinstance(result, str)

    def test_handles_missing_element_id(self):
        """Should handle animation without element_id."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_scale_pair = Mock(return_value=(1.0, 1.0))

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation()
        delattr(animation, "element_id")

        result = handler._build_scale_animation(animation, 1, 2)
        assert isinstance(result, str)
