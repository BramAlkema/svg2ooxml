"""Tests for SetAnimationHandler."""

from unittest.mock import Mock
import pytest

from svg2ooxml.drawingml.animation.handlers.set import SetAnimationHandler
from svg2ooxml.drawingml.animation.constants import COLOR_ATTRIBUTES


@pytest.fixture
def xml_builder():
    """Mock XML builder."""
    builder = Mock()
    builder.build_attribute_list.return_value = (
        '                                            <a:attrNameLst>\n'
        '                                                <a:attrName>ppt_x</a:attrName>\n'
        '                                            </a:attrNameLst>\n'
    )
    builder.build_behavior_core.return_value = (
        '                                        <a:cBhvr>\n'
        '                                            <a:cTn id="2" dur="1" fill="hold"/>\n'
        '                                            <a:tgtEl>\n'
        '                                                <a:spTgt spid="shape1"/>\n'
        '                                            </a:tgtEl>\n'
        '                                            <a:attrNameLst>\n'
        '                                                <a:attrName>ppt_x</a:attrName>\n'
        '                                            </a:attrNameLst>\n'
        '                                        </a:cBhvr>\n'
    )
    builder.build_par_container.return_value = (
        '<p:par>\n'
        '    <p:cTn id="1" dur="1" fill="hold">\n'
        '        <p:stCondLst>\n'
        '            <p:cond delay="0"/>\n'
        '        </p:stCondLst>\n'
        '        <p:childTnLst>\n'
        '            <CHILD_XML/>\n'
        '        </p:childTnLst>\n'
        '    </p:cTn>\n'
        '</p:par>'
    )
    return builder


@pytest.fixture
def value_processor():
    """Mock value processor."""
    processor = Mock()
    processor.parse_color.return_value = "ff0000"
    processor.normalize_numeric_value.return_value = "914400"
    return processor


@pytest.fixture
def tav_builder():
    """Mock TAV builder (not used for set animations)."""
    return Mock()


@pytest.fixture
def unit_converter():
    """Mock unit converter."""
    converter = Mock()
    converter.to_emu.return_value = 914400
    return converter


@pytest.fixture
def handler(xml_builder, value_processor, tav_builder, unit_converter):
    """Create SetAnimationHandler instance."""
    return SetAnimationHandler(
        xml_builder=xml_builder,
        value_processor=value_processor,
        tav_builder=tav_builder,
        unit_converter=unit_converter,
    )


class TestInit:
    """Tests for __init__ method."""

    def test_init_with_dependencies(
        self, xml_builder, value_processor, tav_builder, unit_converter
    ):
        """Should initialize with all dependencies."""
        handler = SetAnimationHandler(
            xml_builder=xml_builder,
            value_processor=value_processor,
            tav_builder=tav_builder,
            unit_converter=unit_converter,
        )

        assert handler._xml is xml_builder
        assert handler._processor is value_processor
        assert handler._tav is tav_builder
        assert handler._units is unit_converter


class TestCanHandle:
    """Tests for can_handle method."""

    def test_handles_set_animation_type_uppercase(self, handler):
        """Should handle animation with animation_type='SET'."""
        animation = Mock(animation_type="SET")
        assert handler.can_handle(animation) is True

    def test_handles_set_animation_type_lowercase(self, handler):
        """Should handle animation with animation_type='set'."""
        animation = Mock(animation_type="set")
        assert handler.can_handle(animation) is True

    def test_handles_set_animation_type_mixed_case(self, handler):
        """Should handle animation with animation_type='Set'."""
        animation = Mock(animation_type="Set")
        assert handler.can_handle(animation) is True

    def test_handles_enum_with_set(self, handler):
        """Should handle animation_type enum containing SET."""
        animation = Mock(animation_type=Mock(__str__=lambda self: "AnimationType.SET"))
        assert handler.can_handle(animation) is True

    def test_rejects_non_set_animation(self, handler):
        """Should reject non-set animations."""
        animation = Mock(animation_type="ANIMATE")
        assert handler.can_handle(animation) is False

    def test_rejects_animation_without_animation_type(self, handler):
        """Should reject animations without animation_type attribute."""
        animation = Mock(spec=["attribute_name", "values"])
        assert handler.can_handle(animation) is False


class TestMapAttributeName:
    """Tests for _map_attribute_name method."""

    def test_maps_x_to_ppt_x(self, handler):
        """Should map 'x' to 'ppt_x'."""
        result = handler._map_attribute_name("x")
        assert result == "ppt_x"

    def test_maps_y_to_ppt_y(self, handler):
        """Should map 'y' to 'ppt_y'."""
        result = handler._map_attribute_name("y")
        assert result == "ppt_y"

    def test_maps_width_to_ppt_w(self, handler):
        """Should map 'width' to 'ppt_w'."""
        result = handler._map_attribute_name("width")
        assert result == "ppt_w"

    def test_returns_unmapped_attribute_as_is(self, handler):
        """Should return unmapped attributes unchanged."""
        result = handler._map_attribute_name("visibility")
        assert result == "visibility"


class TestBuildColorValueBlock:
    """Tests for _build_color_value_block method."""

    def test_builds_to_element_with_srgb_color(self, handler, value_processor):
        """Should build <a:to> with <a:srgbClr>."""
        value_processor.parse_color.return_value = "ff0000"

        result = handler._build_color_value_block("#ff0000")

        assert "<a:to>" in result
        assert "</a:to>" in result
        assert '<a:srgbClr val="ff0000"/>' in result
        value_processor.parse_color.assert_called_once_with("#ff0000")

    def test_parses_color_value(self, handler, value_processor):
        """Should parse color through value processor."""
        value_processor.parse_color.return_value = "00ff00"

        handler._build_color_value_block("green")

        value_processor.parse_color.assert_called_once_with("green")


class TestBuildNumericValueBlock:
    """Tests for _build_numeric_value_block method."""

    def test_builds_to_element_with_val(self, handler, value_processor):
        """Should build <a:to> with <a:val>."""
        value_processor.normalize_numeric_value.return_value = "914400"

        result = handler._build_numeric_value_block("ppt_x", "100")

        assert "<a:to>" in result
        assert "</a:to>" in result
        assert '<a:val val="914400"/>' in result

    def test_normalizes_numeric_value(self, handler, value_processor):
        """Should normalize value through value processor."""
        value_processor.normalize_numeric_value.return_value = "2700000"

        handler._build_numeric_value_block("ppt_angle", "45")

        value_processor.normalize_numeric_value.assert_called_once()
        args = value_processor.normalize_numeric_value.call_args
        assert args[0][0] == "ppt_angle"
        assert args[0][1] == "45"

    def test_escapes_quotes_in_value(self, handler, value_processor):
        """Should escape quotes in normalized value."""
        value_processor.normalize_numeric_value.return_value = '100"200'

        result = handler._build_numeric_value_block("ppt_x", "test")

        assert '100&quot;200' in result
        assert '100"200' not in result


class TestNormalizeValue:
    """Tests for _normalize_value method."""

    def test_normalizes_via_value_processor(self, handler, value_processor):
        """Should normalize through value processor."""
        value_processor.normalize_numeric_value.return_value = "1828800"

        result = handler._normalize_value("ppt_x", "200")

        assert result == "1828800"
        value_processor.normalize_numeric_value.assert_called_once()


class TestEscapeValue:
    """Tests for _escape_value method."""

    def test_escapes_quotes(self, handler):
        """Should escape double quotes."""
        result = handler._escape_value('test"value')
        assert result == 'test&quot;value'

    def test_handles_no_quotes(self, handler):
        """Should return unchanged when no quotes."""
        result = handler._escape_value('testvalue')
        assert result == 'testvalue'

    def test_handles_empty_string(self, handler):
        """Should handle empty string."""
        result = handler._escape_value('')
        assert result == ''


class TestBuild:
    """Tests for build method."""

    def test_returns_empty_string_when_no_values(self, handler):
        """Should return empty string when animation has no values."""
        animation = Mock(
            animation_type="SET",
            attribute_name="x",
            values=[],
            duration_ms=1,
            begin_ms=0,
        )

        result = handler.build(animation, par_id=1, behavior_id=2)

        assert result == ""

    def test_builds_set_animation_for_numeric_attribute(
        self, handler, xml_builder, value_processor
    ):
        """Should build set animation for numeric attribute."""
        animation = Mock(
            animation_type="SET",
            attribute_name="x",
            values=["100"],
            duration_ms=1,
            begin_ms=0,
            element_id="shape1",
        )

        result = handler.build(animation, par_id=1, behavior_id=2)

        # Should build attribute list
        xml_builder.build_attribute_list.assert_called_once_with(["ppt_x"])

        # Should build behavior core
        xml_builder.build_behavior_core.assert_called_once()
        call_args = xml_builder.build_behavior_core.call_args
        assert call_args[1]["behavior_id"] == 2
        assert call_args[1]["duration_ms"] == 1
        assert call_args[1]["target_shape"] == "shape1"

        # Should build par container
        xml_builder.build_par_container.assert_called_once()
        par_args = xml_builder.build_par_container.call_args
        assert par_args[1]["par_id"] == 1
        assert par_args[1]["duration_ms"] == 1
        assert par_args[1]["delay_ms"] == 0

        # Should contain set element
        child_xml = par_args[1].get("child_content") or par_args[1]["child_xml"]
        assert "<a:set>" in child_xml
        assert "</a:set>" in child_xml

    def test_builds_set_animation_for_color_attribute(self, handler, xml_builder):
        """Should build set animation for color attribute."""
        animation = Mock(
            animation_type="SET",
            attribute_name="fill",
            values=["#ff0000"],
            duration_ms=1,
            begin_ms=0,
            element_id="shape1",
        )

        handler.build(animation, par_id=1, behavior_id=2)

        # Should build attribute list (fill maps to fillClr)
        xml_builder.build_attribute_list.assert_called_once_with(["fillClr"])

        # Should build par container with color value
        child_xml = (
            xml_builder.build_par_container.call_args[1].get("child_content")
            or xml_builder.build_par_container.call_args[1]["child_xml"]
        )
        assert "<a:srgbClr" in child_xml

    def test_uses_last_value_from_values_list(self, handler, value_processor):
        """Should use the last value in the values list."""
        animation = Mock(
            animation_type="SET",
            attribute_name="x",
            values=["10", "20", "100"],
            duration_ms=1,
            begin_ms=0,
            element_id="shape1",
        )

        handler.build(animation, par_id=1, behavior_id=2)

        # Should normalize the last value (100)
        value_processor.normalize_numeric_value.assert_called_once()
        call_args = value_processor.normalize_numeric_value.call_args
        assert call_args[0][1] == "100"

    def test_handles_begin_delay(self, handler, xml_builder):
        """Should pass begin_ms as delay to par container."""
        animation = Mock(
            animation_type="SET",
            attribute_name="x",
            values=["100"],
            duration_ms=1,
            begin_ms=500,
            element_id="shape1",
        )

        handler.build(animation, par_id=1, behavior_id=2)

        call_args = xml_builder.build_par_container.call_args
        assert call_args[1]["delay_ms"] == 500

    def test_handles_missing_element_id(self, handler, xml_builder):
        """Should handle missing element_id gracefully."""
        animation = Mock(
            animation_type="SET",
            attribute_name="x",
            values=["100"],
            duration_ms=1,
            begin_ms=0,
            spec=["animation_type", "attribute_name", "values", "duration_ms", "begin_ms"],
        )

        result = handler.build(animation, par_id=1, behavior_id=2)

        # Should still build (with empty target)
        xml_builder.build_behavior_core.assert_called_once()
        assert xml_builder.build_behavior_core.call_args[1]["target_shape"] == ""

    def test_maps_attribute_name(self, handler, xml_builder):
        """Should map SVG attribute to PowerPoint attribute."""
        animation = Mock(
            animation_type="SET",
            attribute_name="width",
            values=["200"],
            duration_ms=1,
            begin_ms=0,
            element_id="shape1",
        )

        handler.build(animation, par_id=1, behavior_id=2)

        # Should use mapped attribute name (ppt_w)
        xml_builder.build_attribute_list.assert_called_once_with(["ppt_w"])


class TestIntegration:
    """Integration tests combining multiple methods."""

    def test_complete_numeric_set_workflow(self, handler, xml_builder, value_processor):
        """Test complete workflow for numeric set animation."""
        animation = Mock(
            animation_type="SET",
            attribute_name="x",
            values=["100"],
            duration_ms=1,
            begin_ms=0,
            element_id="test_shape",
        )

        # Handler should accept this animation
        assert handler.can_handle(animation) is True

        # Build XML
        result = handler.build(animation, par_id=10, behavior_id=20)

        # Verify calls
        assert result != ""
        xml_builder.build_attribute_list.assert_called_once_with(["ppt_x"])
        xml_builder.build_behavior_core.assert_called_once()
        xml_builder.build_par_container.assert_called_once()

        # Verify structure
        child_xml = (
            xml_builder.build_par_container.call_args[1].get("child_content")
            or xml_builder.build_par_container.call_args[1]["child_xml"]
        )
        assert "<a:set>" in child_xml
        assert "<a:to>" in child_xml
        assert "<a:val" in child_xml

    def test_complete_color_set_workflow(self, handler, xml_builder, value_processor):
        """Test complete workflow for color set animation."""
        animation = Mock(
            animation_type="SET",
            attribute_name="fill",
            values=["#0000ff"],
            duration_ms=1,
            begin_ms=100,
            element_id="color_shape",
        )

        # Handler should accept this animation
        assert handler.can_handle(animation) is True

        # Build XML
        result = handler.build(animation, par_id=5, behavior_id=15)

        # Verify calls
        assert result != ""
        value_processor.parse_color.assert_called_once_with("#0000ff")

        # Verify structure
        child_xml = (
            xml_builder.build_par_container.call_args[1].get("child_content")
            or xml_builder.build_par_container.call_args[1]["child_xml"]
        )
        assert "<a:set>" in child_xml
        assert "<a:to>" in child_xml
        assert "<a:srgbClr" in child_xml

    def test_rejects_and_returns_empty_for_non_set(self, handler):
        """Test rejection of non-set animations."""
        animation = Mock(
            animation_type="ANIMATE",
            attribute_name="x",
            values=["0", "100"],
            duration_ms=1000,
        )

        assert handler.can_handle(animation) is False


class TestEdgeCases:
    """Edge case tests."""

    def test_handles_single_value(self, handler, xml_builder):
        """Should handle single value in values list."""
        animation = Mock(
            animation_type="SET",
            attribute_name="x",
            values=["100"],
            duration_ms=1,
            begin_ms=0,
            element_id="shape1",
        )

        result = handler.build(animation, par_id=1, behavior_id=2)

        assert result != ""
        xml_builder.build_par_container.assert_called_once()

    def test_handles_unmapped_attribute(self, handler, xml_builder):
        """Should handle unmapped attributes."""
        animation = Mock(
            animation_type="SET",
            attribute_name="custom_attr",
            values=["value"],
            duration_ms=1,
            begin_ms=0,
            element_id="shape1",
        )

        handler.build(animation, par_id=1, behavior_id=2)

        # Should use attribute name as-is
        xml_builder.build_attribute_list.assert_called_once_with(["custom_attr"])

    def test_handles_zero_duration(self, handler, xml_builder):
        """Should handle zero duration."""
        animation = Mock(
            animation_type="SET",
            attribute_name="x",
            values=["100"],
            duration_ms=0,
            begin_ms=0,
            element_id="shape1",
        )

        result = handler.build(animation, par_id=1, behavior_id=2)

        # Should still build (PowerPoint will handle 0 duration)
        assert result != ""
        assert xml_builder.build_behavior_core.call_args[1]["duration_ms"] == 0

    def test_handles_large_ids(self, handler, xml_builder):
        """Should handle large par and behavior IDs."""
        animation = Mock(
            animation_type="SET",
            attribute_name="x",
            values=["100"],
            duration_ms=1,
            begin_ms=0,
            element_id="shape1",
        )

        handler.build(animation, par_id=999999, behavior_id=888888)

        behavior_args = xml_builder.build_behavior_core.call_args
        par_args = xml_builder.build_par_container.call_args

        assert behavior_args[1]["behavior_id"] == 888888
        assert par_args[1]["par_id"] == 999999
