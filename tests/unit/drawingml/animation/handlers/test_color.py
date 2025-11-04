"""Tests for color animation handler."""

import pytest
from unittest.mock import Mock
from lxml import etree

from svg2ooxml.drawingml.animation.handlers.color import ColorAnimationHandler
from svg2ooxml.drawingml.animation.handlers.base import AnimationDefinition


def create_test_animation(**kwargs):
    """Helper to create mock animation with defaults."""
    animation = Mock(spec=AnimationDefinition)
    attribute_name = kwargs.get("attribute_name", "fill")
    target_attribute = kwargs.get("target_attribute", attribute_name)
    animation.attribute_name = attribute_name
    animation.target_attribute = target_attribute
    animation.animation_type = kwargs.get("animation_type", None)
    animation.values = kwargs.get("values", ["#FF0000", "#00FF00"])
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
    """Test ColorAnimationHandler initialization."""

    def test_init_with_dependencies(self):
        """Handler should accept all dependencies."""
        xml_builder = Mock()
        value_processor = Mock()
        tav_builder = Mock()
        unit_converter = Mock()

        handler = ColorAnimationHandler(
            xml_builder, value_processor, tav_builder, unit_converter
        )

        assert handler._xml is xml_builder
        assert handler._processor is value_processor
        assert handler._tav is tav_builder
        assert handler._units is unit_converter


class TestCanHandle:
    """Test can_handle method."""

    def test_handles_fill_attribute(self):
        """Should handle 'fill' attribute."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="fill")

        assert handler.can_handle(animation) is True

    def test_handles_stroke_attribute(self):
        """Should handle 'stroke' attribute."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="stroke")

        assert handler.can_handle(animation) is True

    def test_handles_stop_color_attribute(self):
        """Should handle 'stop-color' attribute."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="stop-color")

        assert handler.can_handle(animation) is True

    def test_handles_stopcolor_attribute(self):
        """Should handle 'stopcolor' attribute."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="stopcolor")

        assert handler.can_handle(animation) is True

    def test_handles_flood_color_attribute(self):
        """Should handle 'flood-color' attribute."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="flood-color")

        assert handler.can_handle(animation) is True

    def test_handles_lighting_color_attribute(self):
        """Should handle 'lighting-color' attribute."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="lighting-color")

        assert handler.can_handle(animation) is True

    def test_does_not_handle_opacity_attribute(self):
        """Should not handle opacity attributes."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="opacity")

        assert handler.can_handle(animation) is False

    def test_does_not_handle_transform_attribute(self):
        """Should not handle transform attributes."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="transform")

        assert handler.can_handle(animation) is False

    def test_does_not_handle_numeric_attribute(self):
        """Should not handle numeric attributes."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="x")

        assert handler.can_handle(animation) is False


class TestMapColorAttribute:
    """Test _map_color_attribute helper."""

    def test_maps_fill_to_fillClr(self):
        """Should map 'fill' to 'fillClr'."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._map_color_attribute("fill")
        assert result == "fillClr"

    def test_maps_stroke_to_lnClr(self):
        """Should map 'stroke' to 'lnClr'."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._map_color_attribute("stroke")
        assert result == "lnClr"

    def test_maps_stop_color_to_fillClr(self):
        """Should map 'stop-color' to 'fillClr'."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._map_color_attribute("stop-color")
        assert result == "fillClr"

    def test_defaults_to_fillClr_for_unknown(self):
        """Should default to 'fillClr' for unknown attributes."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._map_color_attribute("unknown-color")
        assert result == "fillClr"


class TestBuildColorTAVList:
    """Test _build_color_tav_list helper."""

    def test_returns_empty_for_two_values_no_key_times(self):
        """Should return empty list for simple two-value animation."""
        tav_builder = Mock()
        handler = ColorAnimationHandler(Mock(), Mock(), tav_builder, Mock())
        animation = create_test_animation(values=["#FF0000", "#00FF00"], key_times=None)

        tav_elements, needs_ns = handler._build_color_tav_list(animation)

        assert tav_elements == []
        assert needs_ns is False
        # Should not call tav_builder
        tav_builder.build_tav_list.assert_not_called()

    def test_builds_tav_list_for_three_values(self):
        """Should build TAV list for animations with >2 values."""
        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=(["<tav1/>", "<tav2/>", "<tav3/>"], False))

        handler = ColorAnimationHandler(Mock(), Mock(), tav_builder, Mock())
        animation = create_test_animation(
            values=["#FF0000", "#00FF00", "#0000FF"],
            duration_ms=1000
        )

        tav_elements, needs_ns = handler._build_color_tav_list(animation)

        assert len(tav_elements) == 3
        assert needs_ns is False
        tav_builder.build_tav_list.assert_called_once()

    def test_builds_tav_list_with_explicit_key_times(self):
        """Should build TAV list when explicit key_times provided."""
        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=(["<tav1/>", "<tav2/>"], True))

        handler = ColorAnimationHandler(Mock(), Mock(), tav_builder, Mock())
        animation = create_test_animation(
            values=["#FF0000", "#00FF00"],
            key_times=[0.0, 1.0]
        )

        tav_elements, needs_ns = handler._build_color_tav_list(animation)

        assert len(tav_elements) == 2
        assert needs_ns is True

    def test_returns_empty_for_no_values(self):
        """Should return empty for animation with no values."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(values=[])

        tav_elements, needs_ns = handler._build_color_tav_list(animation)

        assert tav_elements == []
        assert needs_ns is False

    def test_passes_correct_arguments_to_tav_builder(self):
        """Should pass correct arguments to TAV builder."""
        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = ColorAnimationHandler(Mock(), Mock(), tav_builder, Mock())
        animation = create_test_animation(
            values=["#FF0000", "#00FF00", "#0000FF"],
            key_times=[0.0, 0.5, 1.0],
            key_splines=[[0.42, 0, 0.58, 1], [0.42, 0, 0.58, 1]],
            duration_ms=2000
        )

        handler._build_color_tav_list(animation)

        call_args = tav_builder.build_tav_list.call_args
        assert call_args.kwargs["values"] == ["#FF0000", "#00FF00", "#0000FF"]
        assert call_args.kwargs["key_times"] == [0.0, 0.5, 1.0]
        assert call_args.kwargs["key_splines"] == [[0.42, 0, 0.58, 1], [0.42, 0, 0.58, 1]]
        assert call_args.kwargs["duration_ms"] == 2000


class TestBuild:
    """Test build method."""

    def test_returns_empty_string_for_no_values(self):
        """Should return empty string if no values."""
        handler = ColorAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(values=[])

        result = handler.build(animation, par_id=1, behavior_id=2)

        assert result == ""

    def test_returns_string_for_valid_animation(self):
        """Should return XML string for valid animation."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrNameLst/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(side_effect=lambda x: x.upper().replace("#", ""))

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation()

        result = handler.build(animation, par_id=1, behavior_id=2)

        assert isinstance(result, str)
        assert result == "<p:par/>"

    def test_calls_parse_color_for_from_and_to(self):
        """Should parse both from and to colors."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrNameLst/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(return_value="000000")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["#FF0000", "#00FF00"])

        handler.build(animation, par_id=1, behavior_id=2)

        # Should parse first and last colors
        assert value_processor.parse_color.call_count == 2
        value_processor.parse_color.assert_any_call("#FF0000")
        value_processor.parse_color.assert_any_call("#00FF00")

    def test_calls_build_attribute_list_with_mapped_attribute(self):
        """Should build attribute list with PowerPoint attribute name."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrNameLst/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(return_value="000000")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(attribute_name="stroke")

        handler.build(animation, par_id=1, behavior_id=2)

        # Should map stroke → lnClr
        xml_builder.build_attribute_list.assert_called_once_with(["lnClr"])

    def test_builds_anim_clr_with_from_and_to(self):
        """Should build animClr element with from and to colors."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrNameLst/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(side_effect=["FF0000", "00FF00"])

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation()

        handler.build(animation, par_id=1, behavior_id=2)

        # Check that child_xml contains from/to
        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:animClr>" in child_xml
        assert "<a:from>" in child_xml
        assert '<a:srgbClr val="FF0000"/>' in child_xml
        assert "<a:to>" in child_xml
        assert '<a:srgbClr val="00FF00"/>' in child_xml
        assert "</a:animClr>" in child_xml

    def test_includes_behavior_core_in_anim_clr(self):
        """Should include behavior core inside animClr."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<BEHAVIOR_CORE/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrNameLst/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(return_value="000000")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation()

        handler.build(animation, par_id=1, behavior_id=2)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<BEHAVIOR_CORE/>" in child_xml

    def test_includes_tav_list_when_keyframes_exist(self):
        """Should include TAV list for multi-keyframe animations."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrNameLst/>")
        xml_builder.build_tav_list_container = Mock(return_value="<TAV_CONTAINER/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(return_value="000000")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=(["<tav1/>", "<tav2/>"], False))

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["#FF0000", "#00FF00", "#0000FF"])

        handler.build(animation, par_id=1, behavior_id=2)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:tavLst>" in child_xml
        assert "<TAV_CONTAINER/>" in child_xml
        assert "</a:tavLst>" in child_xml

    def test_adds_custom_namespace_when_needed(self):
        """Should add svg2 namespace to animClr when TAV uses it."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrNameLst/>")
        xml_builder.build_tav_list_container = Mock(return_value="<tavs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(return_value="000000")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=(["<tav/>"], True))  # needs_ns=True

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["#FF0000", "#00FF00", "#0000FF"])

        handler.build(animation, par_id=1, behavior_id=2)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert 'xmlns:svg2="http://svg2ooxml.dev/ns/animation"' in child_xml

    def test_no_namespace_when_not_needed(self):
        """Should not add namespace when TAV doesn't use it."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrNameLst/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(return_value="000000")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))  # needs_ns=False

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation()

        handler.build(animation, par_id=1, behavior_id=2)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "xmlns:svg2" not in child_xml


class TestIntegration:
    """Test integrated workflows."""

    def test_complete_color_animation_workflow(self):
        """Test complete workflow: check can_handle, then build."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par>complete</p:par>")

        value_processor = Mock()
        value_processor.parse_color = Mock(return_value="000000")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(attribute_name="fill")

        # First check if handler can handle
        assert handler.can_handle(animation) is True

        # Then build
        result = handler.build(animation, par_id=1, behavior_id=2)

        assert result == "<p:par>complete</p:par>"

    def test_fill_color_transition(self):
        """Test fill color transition (red → green)."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(side_effect=["FF0000", "00FF00"])

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(
            attribute_name="fill",
            values=["#FF0000", "#00FF00"]
        )

        handler.build(animation, par_id=1, behavior_id=2)

        # Should parse both colors
        value_processor.parse_color.assert_any_call("#FF0000")
        value_processor.parse_color.assert_any_call("#00FF00")

    def test_stroke_color_with_keyframes(self):
        """Test stroke color animation with multiple keyframes."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrs/>")
        xml_builder.build_tav_list_container = Mock(return_value="<tavs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(side_effect=["FF0000", "0000FF"])

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=(["<tav1/>", "<tav2/>", "<tav3/>"], False))

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(
            attribute_name="stroke",
            values=["#FF0000", "#00FF00", "#0000FF"]
        )

        handler.build(animation, par_id=1, behavior_id=2)

        # Should build TAV list
        tav_builder.build_tav_list.assert_called_once()


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_single_value(self):
        """Should handle animation with single value."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(return_value="FF0000")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["#FF0000"])

        result = handler.build(animation, par_id=1, behavior_id=2)

        # Should use same color for from and to
        assert isinstance(result, str)

    def test_handles_missing_element_id(self):
        """Should handle animation without element_id."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(return_value="000000")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation()
        delattr(animation, "element_id")

        # Should not raise
        result = handler.build(animation, par_id=1, behavior_id=2)
        assert isinstance(result, str)

    def test_handles_zero_duration(self):
        """Should handle zero duration animations."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.parse_color = Mock(return_value="000000")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(duration_ms=0)

        # Should not raise
        result = handler.build(animation, par_id=1, behavior_id=2)
        assert isinstance(result, str)
