"""Tests for TAV builder."""

from lxml import etree

from svg2ooxml.drawingml.animation.tav_builder import TAVBuilder
from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder


# Simple value formatter for testing
def simple_numeric_formatter(value: str) -> etree._Element:
    """Simple formatter that creates <a:val val="..."/>."""
    from svg2ooxml.drawingml.xml_builder import a_elem
    return a_elem("val", val=value)


class TestInit:
    """Test TAVBuilder initialization."""

    def test_init_with_xml_builder(self):
        xml_builder = AnimationXMLBuilder()
        builder = TAVBuilder(xml_builder)
        assert builder._xml is xml_builder


class TestResolveKeyTimes:
    """Test resolve_key_times method."""

    def test_empty_values(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        result = builder.resolve_key_times([], None)
        assert result == []

    def test_auto_distribute_two_values(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        result = builder.resolve_key_times(["0", "100"], None)
        assert result == [0.0, 1.0]

    def test_auto_distribute_three_values(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        result = builder.resolve_key_times(["0", "50", "100"], None)
        assert result == [0.0, 0.5, 1.0]

    def test_auto_distribute_four_values(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        result = builder.resolve_key_times(["0", "33", "66", "100"], None)
        expected = [0.0, 1/3, 2/3, 1.0]
        for r, e in zip(result, expected, strict=True):
            assert abs(r - e) < 0.0001

    def test_single_value(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        result = builder.resolve_key_times(["100"], None)
        assert result == [0.0]

    def test_explicit_key_times_valid(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        key_times = [0.0, 0.3, 0.7, 1.0]
        result = builder.resolve_key_times(["0", "30", "70", "100"], key_times)
        assert result == key_times

    def test_explicit_key_times_wrong_length_auto_distributes(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        # Wrong length: 3 times for 2 values
        key_times = [0.0, 0.5, 1.0]
        result = builder.resolve_key_times(["0", "100"], key_times)
        # Should auto-distribute instead
        assert result == [0.0, 1.0]

    def test_preserves_explicit_times(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        key_times = [0.0, 0.2, 0.8, 1.0]
        result = builder.resolve_key_times(["a", "b", "c", "d"], key_times)
        assert result == list(key_times)


class TestClampPercentage:
    """Test _clamp_percentage helper."""

    def test_normal_values(self):
        assert TAVBuilder._clamp_percentage(0.0) == 0
        assert TAVBuilder._clamp_percentage(0.5) == 50000
        assert TAVBuilder._clamp_percentage(1.0) == 100000

    def test_clamping_above_one(self):
        assert TAVBuilder._clamp_percentage(1.5) == 100000
        assert TAVBuilder._clamp_percentage(2.0) == 100000

    def test_clamping_below_zero(self):
        assert TAVBuilder._clamp_percentage(-0.5) == 0
        assert TAVBuilder._clamp_percentage(-1.0) == 0

    def test_fractional_values(self):
        assert TAVBuilder._clamp_percentage(0.25) == 25000
        assert TAVBuilder._clamp_percentage(0.75) == 75000


class TestFormatSpline:
    """Test _format_spline method."""

    def test_format_basic_spline(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        result = builder._format_spline([0.42, 0, 0.58, 1])
        assert result == "0.4200,0.0000,0.5800,1.0000"

    def test_format_with_clamping(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        # Values outside 0-1 should be clamped
        result = builder._format_spline([-0.1, 0.5, 0.8, 1.5])
        assert result == "0.0000,0.5000,0.8000,1.0000"

    def test_format_decimal_precision(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        result = builder._format_spline([0.1234567, 0.2, 0.3, 0.4])
        # Should format to 4 decimals
        assert result == "0.1235,0.2000,0.3000,0.4000"


class TestSegmentAccelDecel:
    """Test _segment_accel_decel method."""

    def test_linear_spline(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        # Linear: y1=0, y2=1 → no accel/decel
        accel, decel = builder._segment_accel_decel([0, 0, 1, 1])
        assert accel == 0
        assert decel == 0

    def test_ease_in_spline(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        # Ease-in: y1=0, y2=0.8 → decel > 0
        accel, decel = builder._segment_accel_decel([0.42, 0, 0.8, 0.8])
        assert accel == 0
        assert decel > 0

    def test_ease_out_spline(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        # Ease-out: y1=0.2, y2=1 → accel > 0
        accel, decel = builder._segment_accel_decel([0.2, 0.2, 0.58, 1])
        assert accel > 0
        assert decel == 0

    def test_invalid_spline_length(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        # Wrong length → (0, 0)
        assert builder._segment_accel_decel([]) == (0, 0)
        assert builder._segment_accel_decel([0.5]) == (0, 0)
        assert builder._segment_accel_decel([0.5, 0.5, 0.5]) == (0, 0)


class TestComputeTAVMetadata:
    """Test compute_tav_metadata method."""

    def test_first_keyframe_no_metadata(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        # First keyframe (index=0) should have no metadata
        metadata = builder.compute_tav_metadata(0, [0.0, 1.0], 1000, [[0.42, 0, 0.58, 1]])
        assert metadata == {}

    def test_no_splines_no_metadata(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        # No splines → no metadata
        metadata = builder.compute_tav_metadata(1, [0.0, 1.0], 1000, [])
        assert metadata == {}

    def test_second_keyframe_with_spline(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        metadata = builder.compute_tav_metadata(
            1,
            [0.0, 1.0],
            1000,
            [[0.42, 0, 0.58, 1]]
        )

        # Should have spline metadata
        assert "svg2:spline" in metadata
        assert "svg2:segDur" in metadata
        assert metadata["svg2:spline"] == "0.4200,0.0000,0.5800,1.0000"
        assert metadata["svg2:segDur"] == "1000"

    def test_accel_decel_in_metadata(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        # Spline with y1=0.5 → accel > 0
        metadata = builder.compute_tav_metadata(
            1,
            [0.0, 1.0],
            1000,
            [[0.2, 0.5, 0.8, 0.5]]
        )

        assert "svg2:accel" in metadata
        assert "svg2:decel" in metadata

    def test_segment_duration_calculation(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        # Key times: 0.0, 0.3, 1.0 → segment 0→0.3 = 300ms
        metadata = builder.compute_tav_metadata(
            1,
            [0.0, 0.3, 1.0],
            1000,
            [[0.42, 0, 0.58, 1], [0.42, 0, 0.58, 1]]
        )

        assert metadata["svg2:segDur"] == "300"

    def test_out_of_bounds_index(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        # Index too large
        metadata = builder.compute_tav_metadata(
            10,
            [0.0, 1.0],
            1000,
            [[0.42, 0, 0.58, 1]]
        )
        assert metadata == {}


class TestBuildTAVList:
    """Test build_tav_list method (integration)."""

    def test_empty_values(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        tav_list, needs_ns = builder.build_tav_list(
            values=[],
            key_times=None,
            key_splines=None,
            duration_ms=1000,
            value_formatter=simple_numeric_formatter
        )

        assert tav_list == []
        assert needs_ns is False

    def test_two_values_no_splines(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        tav_list, needs_ns = builder.build_tav_list(
            values=["0", "100"],
            key_times=None,
            key_splines=None,
            duration_ms=1000,
            value_formatter=simple_numeric_formatter
        )

        assert len(tav_list) == 2
        assert needs_ns is False  # No splines → no custom namespace

        # Check timing
        assert tav_list[0].get("tm") == "0"
        assert tav_list[1].get("tm") == "1000"

    def test_three_values_with_splines(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        tav_list, needs_ns = builder.build_tav_list(
            values=["0", "50", "100"],
            key_times=None,
            key_splines=[[0.42, 0, 0.58, 1], [0.42, 0, 0.58, 1]],
            duration_ms=1000,
            value_formatter=simple_numeric_formatter
        )

        assert len(tav_list) == 3
        assert needs_ns is True  # Has splines → uses custom namespace

        # Check timing (auto-distributed)
        assert tav_list[0].get("tm") == "0"
        assert tav_list[1].get("tm") == "500"
        assert tav_list[2].get("tm") == "1000"

    def test_explicit_key_times(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        tav_list, needs_ns = builder.build_tav_list(
            values=["0", "30", "100"],
            key_times=[0.0, 0.3, 1.0],
            key_splines=None,
            duration_ms=1000,
            value_formatter=simple_numeric_formatter
        )

        assert len(tav_list) == 3
        # Check explicit timing
        assert tav_list[0].get("tm") == "0"
        assert tav_list[1].get("tm") == "300"
        assert tav_list[2].get("tm") == "1000"

    def test_value_formatter_called(self):
        builder = TAVBuilder(AnimationXMLBuilder())

        # Track calls to formatter
        calls = []

        def tracking_formatter(value: str) -> etree._Element:
            calls.append(value)
            return simple_numeric_formatter(value)

        tav_list, _ = builder.build_tav_list(
            values=["0", "100"],
            key_times=None,
            key_splines=None,
            duration_ms=1000,
            value_formatter=tracking_formatter
        )

        # Formatter should be called for each value
        assert calls == ["0", "100"]

    def test_tav_elements_have_value_children(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        tav_list, _ = builder.build_tav_list(
            values=["0", "100"],
            key_times=None,
            key_splines=None,
            duration_ms=1000,
            value_formatter=simple_numeric_formatter
        )

        # Each TAV should have a <a:val> child
        for tav in tav_list:
            val_elem = tav.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}val")
            assert val_elem is not None

    def test_spline_metadata_attached(self):
        builder = TAVBuilder(AnimationXMLBuilder())
        tav_list, needs_ns = builder.build_tav_list(
            values=["0", "100"],
            key_times=None,
            key_splines=[[0.42, 0, 0.58, 1]],
            duration_ms=1000,
            value_formatter=simple_numeric_formatter
        )

        # Second TAV should have spline metadata
        from svg2ooxml.drawingml.animation.constants import SVG2_ANIMATION_NS
        spline_attr = tav_list[1].get(f"{{{SVG2_ANIMATION_NS}}}spline")
        assert spline_attr is not None
        assert "0.4200" in spline_attr


class TestIntegration:
    """Test integrated TAV building workflows."""

    def test_complete_keyframe_animation(self):
        """Test building complete keyframe animation."""
        builder = TAVBuilder(AnimationXMLBuilder())

        tav_list, needs_ns = builder.build_tav_list(
            values=["0", "25", "75", "100"],
            key_times=[0.0, 0.2, 0.8, 1.0],
            key_splines=[
                [0.42, 0, 0.58, 1],  # 0→25
                [0.42, 0, 0.58, 1],  # 25→75
                [0.42, 0, 0.58, 1],  # 75→100
            ],
            duration_ms=2000,
            value_formatter=simple_numeric_formatter
        )

        # Should have 4 keyframes
        assert len(tav_list) == 4

        # Should use custom namespace for splines
        assert needs_ns is True

        # Check timings
        assert tav_list[0].get("tm") == "0"
        assert tav_list[1].get("tm") == "400"   # 0.2 * 2000
        assert tav_list[2].get("tm") == "1600"  # 0.8 * 2000
        assert tav_list[3].get("tm") == "2000"

    def test_time_clamping(self):
        """Test that times are clamped to 0-duration."""
        builder = TAVBuilder(AnimationXMLBuilder())

        # Explicit times outside 0-1 range
        tav_list, _ = builder.build_tav_list(
            values=["0", "100"],
            key_times=[-0.5, 1.5],  # Out of range
            key_splines=None,
            duration_ms=1000,
            value_formatter=simple_numeric_formatter
        )

        # Should clamp to 0 and 1000
        assert tav_list[0].get("tm") == "0"
        assert tav_list[1].get("tm") == "1000"
