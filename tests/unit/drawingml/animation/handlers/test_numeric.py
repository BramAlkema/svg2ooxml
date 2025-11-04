"""Tests for numeric animation handler."""

import pytest
from unittest.mock import Mock
from lxml import etree

from svg2ooxml.drawingml.animation.handlers.numeric import NumericAnimationHandler
from svg2ooxml.drawingml.animation.handlers.base import AnimationDefinition


def create_test_animation(**kwargs):
    """Helper to create mock animation with defaults."""
    animation = Mock(spec=AnimationDefinition)
    attribute_name = kwargs.get("attribute_name", "x")
    target_attribute = kwargs.get("target_attribute", attribute_name)
    animation.attribute_name = attribute_name
    animation.target_attribute = target_attribute
    animation.animation_type = kwargs.get("animation_type", None)
    animation.values = kwargs.get("values", ["0", "100"])
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
    """Test NumericAnimationHandler initialization."""

    def test_init_with_dependencies(self):
        """Handler should accept all dependencies."""
        xml_builder = Mock()
        value_processor = Mock()
        tav_builder = Mock()
        unit_converter = Mock()

        handler = NumericAnimationHandler(
            xml_builder, value_processor, tav_builder, unit_converter
        )

        assert handler._xml is xml_builder
        assert handler._processor is value_processor
        assert handler._tav is tav_builder
        assert handler._units is unit_converter


class TestCanHandle:
    """Test can_handle method."""

    def test_handles_x_attribute(self):
        """Should handle 'x' attribute."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="x")

        assert handler.can_handle(animation) is True

    def test_handles_y_attribute(self):
        """Should handle 'y' attribute."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="y")

        assert handler.can_handle(animation) is True

    def test_handles_width_attribute(self):
        """Should handle 'width' attribute."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="width")

        assert handler.can_handle(animation) is True

    def test_handles_height_attribute(self):
        """Should handle 'height' attribute."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="height")

        assert handler.can_handle(animation) is True

    def test_handles_stroke_width_attribute(self):
        """Should handle 'stroke-width' attribute."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="stroke-width")

        assert handler.can_handle(animation) is True

    def test_handles_rotate_attribute(self):
        """Should handle 'rotate' attribute."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="rotate")

        assert handler.can_handle(animation) is True

    def test_does_not_handle_opacity_attribute(self):
        """Should not handle opacity attributes (fade handler)."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="opacity")

        assert handler.can_handle(animation) is False

    def test_does_not_handle_fill_opacity_attribute(self):
        """Should not handle fill-opacity (fade handler)."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="fill-opacity")

        assert handler.can_handle(animation) is False

    def test_does_not_handle_fill_attribute(self):
        """Should not handle fill (color handler)."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="fill")

        assert handler.can_handle(animation) is False

    def test_does_not_handle_stroke_attribute(self):
        """Should not handle stroke (color handler)."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        animation = create_test_animation(attribute_name="stroke")

        assert handler.can_handle(animation) is False


class TestMapAttributeName:
    """Test _map_attribute_name helper."""

    def test_maps_x_to_ppt_x(self):
        """Should map 'x' to 'ppt_x'."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._map_attribute_name("x")
        assert result == "ppt_x"

    def test_maps_y_to_ppt_y(self):
        """Should map 'y' to 'ppt_y'."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._map_attribute_name("y")
        assert result == "ppt_y"

    def test_maps_width_to_ppt_w(self):
        """Should map 'width' to 'ppt_w'."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._map_attribute_name("width")
        assert result == "ppt_w"

    def test_maps_height_to_ppt_h(self):
        """Should map 'height' to 'ppt_h'."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._map_attribute_name("height")
        assert result == "ppt_h"

    def test_maps_rotate_to_ppt_angle(self):
        """Should map 'rotate' to 'ppt_angle'."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._map_attribute_name("rotate")
        assert result == "ppt_angle"

    def test_maps_stroke_width_to_ln_w(self):
        """Should map 'stroke-width' to 'ln_w'."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._map_attribute_name("stroke-width")
        assert result == "ln_w"

    def test_returns_unmapped_attribute_as_is(self):
        """Should return unmapped attributes as-is."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._map_attribute_name("custom-attr")
        assert result == "custom-attr"


class TestNormalizeValue:
    """Test _normalize_value helper."""

    def test_normalizes_via_value_processor(self):
        """Should delegate to ValueProcessor.normalize_numeric_value."""
        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(return_value="914400")

        unit_converter = Mock()

        handler = NumericAnimationHandler(Mock(), value_processor, Mock(), unit_converter)
        result = handler._normalize_value("ppt_x", "100")

        assert result == "914400"
        value_processor.normalize_numeric_value.assert_called_once_with(
            "ppt_x", "100", unit_converter=unit_converter
        )


class TestEscapeValue:
    """Test _escape_value helper."""

    def test_escapes_quotes(self):
        """Should escape double quotes."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._escape_value('100"200')
        assert result == '100&quot;200'

    def test_handles_no_quotes(self):
        """Should handle values without quotes."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._escape_value("914400")
        assert result == "914400"

    def test_handles_empty_string(self):
        """Should handle empty string."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
        result = handler._escape_value("")
        assert result == ""


class TestBuildNumericTAVList:
    """Test _build_numeric_tav_list helper."""

    def test_returns_empty_for_two_values_no_key_times(self):
        """Should return empty list for simple two-value animation."""
        tav_builder = Mock()
        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(side_effect=lambda a, v, **kw: v)

        handler = NumericAnimationHandler(Mock(), value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["0", "100"], key_times=None)

        tav_elements, needs_ns = handler._build_numeric_tav_list(animation, "ppt_x")

        assert tav_elements == []
        assert needs_ns is False
        # Should not call tav_builder
        tav_builder.build_tav_list.assert_not_called()

    def test_builds_tav_list_for_three_values(self):
        """Should build TAV list for animations with >2 values."""
        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=(["<tav1/>", "<tav2/>", "<tav3/>"], False))

        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(side_effect=lambda a, v, **kw: v)

        handler = NumericAnimationHandler(Mock(), value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["0", "50", "100"], duration_ms=1000)

        tav_elements, needs_ns = handler._build_numeric_tav_list(animation, "ppt_x")

        assert len(tav_elements) == 3
        assert needs_ns is False
        tav_builder.build_tav_list.assert_called_once()

    def test_normalizes_all_values(self):
        """Should normalize all values before building TAV list."""
        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(side_effect=lambda a, v, **kw: f"norm_{v}")

        handler = NumericAnimationHandler(Mock(), value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["0", "50", "100"])

        handler._build_numeric_tav_list(animation, "ppt_x")

        # Should normalize all 3 values
        assert value_processor.normalize_numeric_value.call_count == 3

        # Check that normalized values are passed to tav_builder
        call_args = tav_builder.build_tav_list.call_args
        assert call_args.kwargs["values"] == ["norm_0", "norm_50", "norm_100"]


class TestBuild:
    """Test build method."""

    def test_returns_empty_string_for_no_values(self):
        """Should return empty string if no values."""
        handler = NumericAnimationHandler(Mock(), Mock(), Mock(), Mock())
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
        value_processor.normalize_numeric_value = Mock(return_value="914400")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = NumericAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation()

        result = handler.build(animation, par_id=1, behavior_id=2)

        assert isinstance(result, str)
        assert result == "<p:par/>"

    def test_normalizes_from_and_to_values(self):
        """Should normalize both from and to values."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrNameLst/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(side_effect=["0", "914400"])

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = NumericAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["0", "100"])

        handler.build(animation, par_id=1, behavior_id=2)

        # Should normalize first and last values
        assert value_processor.normalize_numeric_value.call_count == 2

    def test_builds_anim_with_from_and_to(self):
        """Should build anim element with from and to values."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrNameLst/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(side_effect=["0", "914400"])

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = NumericAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation()

        handler.build(animation, par_id=1, behavior_id=2)

        # Check that child_xml contains from/to
        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:anim>" in child_xml
        assert "<a:from>" in child_xml
        assert '<a:val val="0"/>' in child_xml
        assert "<a:to>" in child_xml
        assert '<a:val val="914400"/>' in child_xml
        assert "</a:anim>" in child_xml

    def test_includes_behavior_core_in_anim(self):
        """Should include behavior core inside anim."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<BEHAVIOR_CORE/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrNameLst/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(return_value="0")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = NumericAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
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
        value_processor.normalize_numeric_value = Mock(side_effect=["0", "100", "0", "50", "100"])

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=(["<tav1/>", "<tav2/>"], False))

        handler = NumericAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["0", "50", "100"])

        handler.build(animation, par_id=1, behavior_id=2)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert "<a:tavLst>" in child_xml
        assert "<TAV_CONTAINER/>" in child_xml
        assert "</a:tavLst>" in child_xml

    def test_adds_custom_namespace_when_needed(self):
        """Should add svg2 namespace to anim when TAV uses it."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrNameLst/>")
        xml_builder.build_tav_list_container = Mock(return_value="<tavs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(side_effect=["0", "100", "0", "50", "100"])

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=(["<tav/>"], True))  # needs_ns=True

        handler = NumericAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["0", "50", "100"])

        handler.build(animation, par_id=1, behavior_id=2)

        call_args = xml_builder.build_par_container.call_args
        child_xml = call_args.kwargs.get("child_content") or call_args.kwargs["child_xml"]

        assert 'xmlns:svg2="http://svg2ooxml.dev/ns/animation"' in child_xml


class TestIntegration:
    """Test integrated workflows."""

    def test_complete_numeric_animation_workflow(self):
        """Test complete workflow: check can_handle, then build."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par>complete</p:par>")

        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(return_value="914400")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = NumericAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(attribute_name="x")

        # First check if handler can handle
        assert handler.can_handle(animation) is True

        # Then build
        result = handler.build(animation, par_id=1, behavior_id=2)

        assert result == "<p:par>complete</p:par>"

    def test_position_animation(self):
        """Test position animation (x: 0 → 100)."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(side_effect=["0", "914400"])

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = NumericAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(attribute_name="x", values=["0", "100"])

        handler.build(animation, par_id=1, behavior_id=2)

        # Should map x → ppt_x
        xml_builder.build_attribute_list.assert_called_with(["ppt_x"])

    def test_angle_animation(self):
        """Test angle animation (rotate: 0 → 360)."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        # 0 degrees = 0, 360 degrees = 21600000 (360 * 60000)
        value_processor.normalize_numeric_value = Mock(side_effect=["0", "21600000"])

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = NumericAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(attribute_name="rotate", values=["0", "360"])

        handler.build(animation, par_id=1, behavior_id=2)

        # Should map rotate → ppt_angle
        xml_builder.build_attribute_list.assert_called_with(["ppt_angle"])


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_single_value(self):
        """Should handle animation with single value."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(return_value="914400")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = NumericAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation(values=["100"])

        result = handler.build(animation, par_id=1, behavior_id=2)

        # Should use same value for from and to
        assert isinstance(result, str)

    def test_handles_missing_element_id(self):
        """Should handle animation without element_id."""
        xml_builder = Mock()
        xml_builder.build_behavior_core = Mock(return_value="<behavior/>")
        xml_builder.build_attribute_list = Mock(return_value="<attrs/>")
        xml_builder.build_par_container = Mock(return_value="<p:par/>")

        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(return_value="0")

        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = NumericAnimationHandler(xml_builder, value_processor, tav_builder, Mock())
        animation = create_test_animation()
        delattr(animation, "element_id")

        # Should not raise
        result = handler.build(animation, par_id=1, behavior_id=2)
        assert isinstance(result, str)
