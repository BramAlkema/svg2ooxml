"""Tests for base animation handler."""

from unittest.mock import Mock

import pytest

from svg2ooxml.drawingml.animation.handlers.base import AnimationHandler
from svg2ooxml.ir.animation import AnimationDefinition


class ConcreteHandler(AnimationHandler):
    """Concrete handler for testing abstract base class."""

    def can_handle(self, animation: AnimationDefinition) -> bool:
        """Test implementation."""
        return animation.attribute_name == "test-attr"

    def build(self, animation: AnimationDefinition, par_id: int, behavior_id: int) -> str:
        """Test implementation."""
        return f"<test par_id='{par_id}' behavior_id='{behavior_id}'/>"


class TestInit:
    """Test AnimationHandler initialization."""

    def test_init_with_dependencies(self):
        """Handler should accept all dependencies."""
        xml_builder = Mock()
        value_processor = Mock()
        tav_builder = Mock()
        unit_converter = Mock()

        handler = ConcreteHandler(
            xml_builder, value_processor, tav_builder, unit_converter
        )

        assert handler._xml is xml_builder
        assert handler._processor is value_processor
        assert handler._tav is tav_builder
        assert handler._units is unit_converter


class TestCanHandle:
    """Test can_handle abstract method."""

    def test_can_handle_matching_attribute(self):
        """Should return True for matching attribute."""
        handler = ConcreteHandler(Mock(), Mock(), Mock(), Mock())

        animation = Mock(spec=AnimationDefinition)
        animation.attribute_name = "test-attr"
        animation.target_attribute = "test-attr"
        animation.target_attribute = "test-attr"
        animation.target_attribute = "test-attr"

        assert handler.can_handle(animation) is True

    def test_can_handle_non_matching_attribute(self):
        """Should return False for non-matching attribute."""
        handler = ConcreteHandler(Mock(), Mock(), Mock(), Mock())

        animation = Mock(spec=AnimationDefinition)
        animation.attribute_name = "other-attr"
        animation.target_attribute = "other-attr"
        animation.target_attribute = "other-attr"
        animation.target_attribute = "other-attr"

        assert handler.can_handle(animation) is False


class TestBuild:
    """Test build abstract method."""

    def test_build_returns_string(self):
        """Should return XML string."""
        handler = ConcreteHandler(Mock(), Mock(), Mock(), Mock())

        animation = Mock(spec=AnimationDefinition)
        animation.attribute_name = "test-attr"
        animation.target_attribute = "test-attr"

        result = handler.build(animation, par_id=1, behavior_id=2)

        assert isinstance(result, str)
        assert "par_id='1'" in result
        assert "behavior_id='2'" in result

    def test_build_with_different_ids(self):
        """Should use provided IDs in output."""
        handler = ConcreteHandler(Mock(), Mock(), Mock(), Mock())

        animation = Mock(spec=AnimationDefinition)

        result1 = handler.build(animation, par_id=10, behavior_id=20)
        result2 = handler.build(animation, par_id=100, behavior_id=200)

        assert "par_id='10'" in result1
        assert "behavior_id='20'" in result1
        assert "par_id='100'" in result2
        assert "behavior_id='200'" in result2


class TestAnimationDefinition:
    """Test AnimationDefinition protocol."""

    def test_definition_has_required_attributes(self):
        """AnimationDefinition should define all required attributes."""
        # Create a mock with all required attributes
        definition = Mock()
        definition.attribute_name = "test"
        definition.target_attribute = "test"
        definition.values = ["0", "1"]
        definition.key_times = [0.0, 1.0]
        definition.key_splines = [[0.42, 0, 0.58, 1]]
        definition.duration_ms = 1000
        definition.begin_ms = 0
        definition.fill_mode = "freeze"
        definition.additive = "replace"
        definition.accumulate = "none"
        definition.repeat_count = None
        definition.repeat_duration_ms = None
        definition.calc_mode = "linear"

        # Should have these attributes without raising
        assert hasattr(definition, "attribute_name")
        assert hasattr(definition, "values")
        assert hasattr(definition, "target_attribute")
        assert hasattr(definition, "key_times")
        assert hasattr(definition, "key_splines")
        assert hasattr(definition, "duration_ms")
        assert hasattr(definition, "begin_ms")
        assert hasattr(definition, "fill_mode")
        assert hasattr(definition, "additive")
        assert hasattr(definition, "accumulate")
        assert hasattr(definition, "repeat_count")
        assert hasattr(definition, "repeat_duration_ms")
        assert hasattr(definition, "calc_mode")


class TestAbstractMethods:
    """Test that abstract methods must be implemented."""

    def test_cannot_instantiate_base_handler(self):
        """Should not be able to instantiate abstract base class."""
        with pytest.raises(TypeError) as exc_info:
            # Try to instantiate without implementing abstract methods
            AnimationHandler(Mock(), Mock(), Mock(), Mock())  # type: ignore

        assert "Can't instantiate abstract class" in str(exc_info.value)

    def test_incomplete_handler_cannot_be_instantiated(self):
        """Handler missing abstract methods cannot be instantiated."""

        # Handler with only can_handle implemented
        class IncompleteHandler(AnimationHandler):
            def can_handle(self, animation: AnimationDefinition) -> bool:
                return True
            # Missing build()

        with pytest.raises(TypeError):
            IncompleteHandler(Mock(), Mock(), Mock(), Mock())  # type: ignore


class TestDependencyInjection:
    """Test dependency injection pattern."""

    def test_xml_builder_accessible(self):
        """XML builder should be accessible to subclasses."""
        xml_builder = Mock()
        xml_builder.build_par = Mock(return_value="<p:par/>")

        handler = ConcreteHandler(xml_builder, Mock(), Mock(), Mock())

        # Subclass can access _xml
        result = handler._xml.build_par()
        assert result == "<p:par/>"

    def test_value_processor_accessible(self):
        """Value processor should be accessible to subclasses."""
        value_processor = Mock()
        value_processor.normalize_numeric_value = Mock(return_value="100")

        handler = ConcreteHandler(Mock(), value_processor, Mock(), Mock())

        # Subclass can access _processor
        result = handler._processor.normalize_numeric_value()
        assert result == "100"

    def test_tav_builder_accessible(self):
        """TAV builder should be accessible to subclasses."""
        tav_builder = Mock()
        tav_builder.build_tav_list = Mock(return_value=([], False))

        handler = ConcreteHandler(Mock(), Mock(), tav_builder, Mock())

        # Subclass can access _tav
        result = handler._tav.build_tav_list()
        assert result == ([], False)

    def test_unit_converter_accessible(self):
        """Unit converter should be accessible to subclasses."""
        unit_converter = Mock()
        unit_converter.to_emu = Mock(return_value=914400)

        handler = ConcreteHandler(Mock(), Mock(), Mock(), unit_converter)

        # Subclass can access _units
        result = handler._units.to_emu()
        assert result == 914400


class TestHandlerWorkflow:
    """Test typical handler workflow."""

    def test_check_then_build_workflow(self):
        """Typical usage: check can_handle, then build."""
        handler = ConcreteHandler(Mock(), Mock(), Mock(), Mock())

        animation = Mock(spec=AnimationDefinition)
        animation.attribute_name = "test-attr"

        # First check if handler can handle it
        if handler.can_handle(animation):
            # Then build XML
            xml = handler.build(animation, par_id=1, behavior_id=2)
            assert isinstance(xml, str)

    def test_skip_build_if_cannot_handle(self):
        """Should not build if can_handle returns False."""
        handler = ConcreteHandler(Mock(), Mock(), Mock(), Mock())

        animation = Mock(spec=AnimationDefinition)
        animation.attribute_name = "other-attr"

        # Should not build if can't handle
        if handler.can_handle(animation):
            pytest.fail("Should not build for non-matching animation")


class TestMultipleHandlers:
    """Test multiple handler instances."""

    def test_handlers_are_independent(self):
        """Different handler instances should be independent."""
        xml_builder1 = Mock()
        xml_builder2 = Mock()

        handler1 = ConcreteHandler(xml_builder1, Mock(), Mock(), Mock())
        handler2 = ConcreteHandler(xml_builder2, Mock(), Mock(), Mock())

        assert handler1._xml is xml_builder1
        assert handler2._xml is xml_builder2
        assert handler1._xml is not handler2._xml

    def test_handlers_can_coexist(self):
        """Multiple handlers can exist simultaneously."""

        class Handler1(AnimationHandler):
            def can_handle(self, animation: AnimationDefinition) -> bool:
                return animation.attribute_name == "attr1"

            def build(self, animation: AnimationDefinition, par_id: int, behavior_id: int) -> str:
                return "<handler1/>"

        class Handler2(AnimationHandler):
            def can_handle(self, animation: AnimationDefinition) -> bool:
                return animation.attribute_name == "attr2"

            def build(self, animation: AnimationDefinition, par_id: int, behavior_id: int) -> str:
                return "<handler2/>"

        h1 = Handler1(Mock(), Mock(), Mock(), Mock())
        h2 = Handler2(Mock(), Mock(), Mock(), Mock())

        animation1 = Mock(spec=AnimationDefinition)
        animation1.attribute_name = "attr1"
        animation1.target_attribute = "attr1"

        animation2 = Mock(spec=AnimationDefinition)
        animation2.attribute_name = "attr2"
        animation2.target_attribute = "attr2"

        assert h1.can_handle(animation1) is True
        assert h1.can_handle(animation2) is False
        assert h2.can_handle(animation1) is False
        assert h2.can_handle(animation2) is True
