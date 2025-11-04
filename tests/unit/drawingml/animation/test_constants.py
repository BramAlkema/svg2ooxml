"""Tests for animation constants module."""

import pytest

from svg2ooxml.drawingml.animation.constants import (
    FADE_ATTRIBUTES,
    COLOR_ATTRIBUTES,
    ANGLE_ATTRIBUTES,
    ATTRIBUTE_NAME_MAP,
    COLOR_ATTRIBUTE_NAME_MAP,
    AXIS_MAP,
    SVG2_ANIMATION_NS,
)


class TestFadeAttributes:
    """Test FADE_ATTRIBUTES constant."""

    def test_is_frozenset(self):
        assert isinstance(FADE_ATTRIBUTES, frozenset)

    def test_contains_opacity(self):
        assert "opacity" in FADE_ATTRIBUTES

    def test_contains_fill_opacity(self):
        assert "fill-opacity" in FADE_ATTRIBUTES

    def test_contains_stroke_opacity(self):
        assert "stroke-opacity" in FADE_ATTRIBUTES

    def test_count(self):
        assert len(FADE_ATTRIBUTES) == 3


class TestColorAttributes:
    """Test COLOR_ATTRIBUTES constant."""

    def test_is_frozenset(self):
        assert isinstance(COLOR_ATTRIBUTES, frozenset)

    def test_contains_fill(self):
        assert "fill" in COLOR_ATTRIBUTES

    def test_contains_stroke(self):
        assert "stroke" in COLOR_ATTRIBUTES

    def test_contains_stop_color(self):
        assert "stop-color" in COLOR_ATTRIBUTES
        assert "stopcolor" in COLOR_ATTRIBUTES

    def test_contains_flood_color(self):
        assert "flood-color" in COLOR_ATTRIBUTES

    def test_contains_lighting_color(self):
        assert "lighting-color" in COLOR_ATTRIBUTES

    def test_count(self):
        assert len(COLOR_ATTRIBUTES) == 6


class TestAngleAttributes:
    """Test ANGLE_ATTRIBUTES constant."""

    def test_is_frozenset(self):
        assert isinstance(ANGLE_ATTRIBUTES, frozenset)

    def test_contains_angle(self):
        assert "angle" in ANGLE_ATTRIBUTES

    def test_contains_rotation(self):
        assert "rotation" in ANGLE_ATTRIBUTES

    def test_contains_rotate(self):
        assert "rotate" in ANGLE_ATTRIBUTES

    def test_contains_ppt_angle(self):
        assert "ppt_angle" in ANGLE_ATTRIBUTES

    def test_count(self):
        assert len(ANGLE_ATTRIBUTES) == 4


class TestAttributeNameMap:
    """Test ATTRIBUTE_NAME_MAP constant."""

    def test_is_dict(self):
        assert isinstance(ATTRIBUTE_NAME_MAP, dict)

    def test_x_coordinates_map_to_ppt_x(self):
        x_attrs = ["x", "x1", "x2", "cx", "dx", "fx", "left", "right"]
        for attr in x_attrs:
            assert ATTRIBUTE_NAME_MAP[attr] == "ppt_x", f"{attr} should map to ppt_x"

    def test_y_coordinates_map_to_ppt_y(self):
        y_attrs = ["y", "y1", "y2", "cy", "dy", "fy", "top", "bottom"]
        for attr in y_attrs:
            assert ATTRIBUTE_NAME_MAP[attr] == "ppt_y", f"{attr} should map to ppt_y"

    def test_width_attributes_map_to_ppt_w(self):
        w_attrs = ["width", "w", "rx"]
        for attr in w_attrs:
            assert ATTRIBUTE_NAME_MAP[attr] == "ppt_w", f"{attr} should map to ppt_w"

    def test_height_attributes_map_to_ppt_h(self):
        h_attrs = ["height", "h", "ry"]
        for attr in h_attrs:
            assert ATTRIBUTE_NAME_MAP[attr] == "ppt_h", f"{attr} should map to ppt_h"

    def test_angle_attributes_map_to_ppt_angle(self):
        angle_attrs = ["rotate", "rotation", "angle"]
        for attr in angle_attrs:
            assert ATTRIBUTE_NAME_MAP[attr] == "ppt_angle", f"{attr} should map to ppt_angle"

    def test_stroke_width_maps_to_ln_w(self):
        assert ATTRIBUTE_NAME_MAP["stroke-width"] == "ln_w"

    def test_all_values_are_strings(self):
        for key, value in ATTRIBUTE_NAME_MAP.items():
            assert isinstance(key, str), f"Key {key} should be string"
            assert isinstance(value, str), f"Value {value} should be string"


class TestColorAttributeNameMap:
    """Test COLOR_ATTRIBUTE_NAME_MAP constant."""

    def test_is_dict(self):
        assert isinstance(COLOR_ATTRIBUTE_NAME_MAP, dict)

    def test_fill_maps_to_fillClr(self):
        assert COLOR_ATTRIBUTE_NAME_MAP["fill"] == "fillClr"

    def test_stroke_maps_to_lnClr(self):
        assert COLOR_ATTRIBUTE_NAME_MAP["stroke"] == "lnClr"

    def test_stop_color_maps_to_fillClr(self):
        assert COLOR_ATTRIBUTE_NAME_MAP["stop-color"] == "fillClr"
        assert COLOR_ATTRIBUTE_NAME_MAP["stopcolor"] == "fillClr"

    def test_flood_color_maps_to_fillClr(self):
        assert COLOR_ATTRIBUTE_NAME_MAP["flood-color"] == "fillClr"

    def test_lighting_color_maps_to_fillClr(self):
        assert COLOR_ATTRIBUTE_NAME_MAP["lighting-color"] == "fillClr"

    def test_all_values_are_strings(self):
        for key, value in COLOR_ATTRIBUTE_NAME_MAP.items():
            assert isinstance(key, str), f"Key {key} should be string"
            assert isinstance(value, str), f"Value {value} should be string"


class TestAxisMap:
    """Test AXIS_MAP constant."""

    def test_is_dict(self):
        assert isinstance(AXIS_MAP, dict)

    def test_ppt_x_maps_to_x(self):
        assert AXIS_MAP["ppt_x"] == "x"

    def test_ppt_y_maps_to_y(self):
        assert AXIS_MAP["ppt_y"] == "y"

    def test_ppt_w_maps_to_width(self):
        assert AXIS_MAP["ppt_w"] == "width"

    def test_ppt_h_maps_to_height(self):
        assert AXIS_MAP["ppt_h"] == "height"

    def test_ln_w_maps_to_width(self):
        assert AXIS_MAP["ln_w"] == "width"

    def test_all_values_are_strings(self):
        for key, value in AXIS_MAP.items():
            assert isinstance(key, str), f"Key {key} should be string"
            assert isinstance(value, str), f"Value {value} should be string"


class TestSVG2AnimationNS:
    """Test SVG2_ANIMATION_NS constant."""

    def test_is_string(self):
        assert isinstance(SVG2_ANIMATION_NS, str)

    def test_is_valid_namespace(self):
        assert SVG2_ANIMATION_NS.startswith("http://")
        assert "svg2ooxml" in SVG2_ANIMATION_NS

    def test_exact_value(self):
        assert SVG2_ANIMATION_NS == "http://svg2ooxml.dev/ns/animation"


class TestCategoryDisjoint:
    """Test that attribute categories are disjoint (no overlap)."""

    def test_fade_and_color_disjoint(self):
        overlap = FADE_ATTRIBUTES & COLOR_ATTRIBUTES
        assert len(overlap) == 0, f"FADE and COLOR should not overlap: {overlap}"

    def test_fade_and_angle_disjoint(self):
        overlap = FADE_ATTRIBUTES & ANGLE_ATTRIBUTES
        assert len(overlap) == 0, f"FADE and ANGLE should not overlap: {overlap}"

    def test_color_and_angle_disjoint(self):
        overlap = COLOR_ATTRIBUTES & ANGLE_ATTRIBUTES
        assert len(overlap) == 0, f"COLOR and ANGLE should not overlap: {overlap}"


class TestMappingConsistency:
    """Test consistency between different mappings."""

    def test_axis_map_keys_in_attribute_name_map_values(self):
        """AXIS_MAP keys should be values in ATTRIBUTE_NAME_MAP."""
        ppt_attrs = set(AXIS_MAP.keys()) - {"ln_w"}  # ln_w is special
        mapped_attrs = set(ATTRIBUTE_NAME_MAP.values())
        assert ppt_attrs.issubset(mapped_attrs), \
            f"AXIS_MAP keys not in ATTRIBUTE_NAME_MAP values: {ppt_attrs - mapped_attrs}"

    def test_color_map_keys_subset_of_color_attributes(self):
        """COLOR_ATTRIBUTE_NAME_MAP keys should be in COLOR_ATTRIBUTES."""
        color_map_keys = set(COLOR_ATTRIBUTE_NAME_MAP.keys())
        assert color_map_keys.issubset(COLOR_ATTRIBUTES), \
            f"Keys not in COLOR_ATTRIBUTES: {color_map_keys - COLOR_ATTRIBUTES}"
