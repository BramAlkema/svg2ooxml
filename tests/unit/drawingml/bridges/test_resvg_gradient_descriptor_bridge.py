from __future__ import annotations

import pytest
from lxml import etree

from svg2ooxml.drawingml.bridges.resvg_paint_bridge import (
    LinearGradientDescriptor,
    MeshGradientDescriptor,
    PatternDescriptor,
    RadialGradientDescriptor,
    build_radial_gradient_element,
    describe_gradient_element,
    describe_pattern_element,
)


def test_describe_gradient_element_resolves_css_stop_colors_and_percent_opacity() -> (
    None
):
    element = etree.fromstring(
        """
        <linearGradient id="grad">
          <stop offset="0%" stop-color="red" stop-opacity="50%"/>
          <stop offset="100%" style="stop-color: rgb(0 0 255 / 75%); stop-opacity: 25%"/>
        </linearGradient>
        """
    )

    descriptor = describe_gradient_element(element)

    assert isinstance(descriptor, LinearGradientDescriptor)
    assert [stop.color for stop in descriptor.stops] == ["#FF0000", "#0000FF"]
    assert [stop.opacity for stop in descriptor.stops] == pytest.approx([0.5, 0.1875])


def test_describe_gradient_element_resolves_absolute_coordinate_units() -> None:
    element = etree.fromstring(
        """
        <linearGradient id="grad" gradientUnits="userSpaceOnUse"
                        x1="0.25in" y1="6pt" x2="1in">
          <stop offset="0" stop-color="#000000"/>
          <stop offset="1" stop-color="#ffffff"/>
        </linearGradient>
        """
    )

    descriptor = describe_gradient_element(element)

    assert isinstance(descriptor, LinearGradientDescriptor)
    assert descriptor.units == "userSpaceOnUse"
    assert descriptor.x1 == pytest.approx(24.0)
    assert descriptor.y1 == pytest.approx(8.0)
    assert descriptor.x2 == pytest.approx(96.0)


def test_describe_gradient_element_preserves_contextless_userspace_percentages() -> (
    None
):
    element = etree.fromstring(
        """
        <linearGradient id="grad" gradientUnits="userSpaceOnUse"
                        x1="calc(25% + 25%)" y1="25%" x2="75%" y2="100%">
          <stop offset="0" stop-color="#000000"/>
          <stop offset="1" stop-color="#ffffff"/>
        </linearGradient>
        """
    )

    descriptor = describe_gradient_element(element)

    assert isinstance(descriptor, LinearGradientDescriptor)
    assert descriptor.units == "userSpaceOnUse"
    assert descriptor.x1 == pytest.approx(0.5)
    assert descriptor.y1 == pytest.approx(0.25)
    assert descriptor.x2 == pytest.approx(0.75)
    assert descriptor.y2 == pytest.approx(1.0)


def test_describe_gradient_element_ignores_nonfinite_coordinates() -> None:
    element = etree.fromstring(
        """
        <linearGradient id="grad" x1="nan" y1="inf" x2="nan" y2="-inf">
          <stop offset="0" stop-color="#000000"/>
          <stop offset="1" stop-color="#ffffff"/>
        </linearGradient>
        """
    )

    descriptor = describe_gradient_element(element)

    assert isinstance(descriptor, LinearGradientDescriptor)
    assert descriptor.x1 == 0.0
    assert descriptor.y1 == 0.0
    assert descriptor.x2 == 1.0
    assert descriptor.y2 == 0.0


def test_describe_gradient_element_parses_full_transform_list() -> None:
    element = etree.fromstring(
        """
        <linearGradient id="grad" gradientTransform="translate(10 20) scale(2)">
          <stop offset="0" stop-color="#000000"/>
          <stop offset="1" stop-color="#ffffff"/>
        </linearGradient>
        """
    )

    descriptor = describe_gradient_element(element)

    assert isinstance(descriptor, LinearGradientDescriptor)
    assert descriptor.transform == pytest.approx((2.0, 0.0, 0.0, 2.0, 10.0, 20.0))


def test_describe_radial_gradient_element_preserves_focal_radius() -> None:
    element = etree.fromstring(
        """
        <radialGradient id="grad" r="50%" fr="25%">
          <stop offset="0" stop-color="#000000"/>
          <stop offset="1" stop-color="#ffffff"/>
        </radialGradient>
        """
    )

    descriptor = describe_gradient_element(element)

    assert isinstance(descriptor, RadialGradientDescriptor)
    assert descriptor.fr == pytest.approx(0.25)
    assert "fr" in descriptor.specified
    assert build_radial_gradient_element(descriptor).get("fr") == "25%"


def test_describe_mesh_gradient_collects_css_stop_colors() -> None:
    element = etree.fromstring(
        """
        <meshgradient>
          <meshrow>
            <meshpatch>
              <stop stop-color="red"/>
              <stop style="stop-color: rgb(0 0 255 / 75%)"/>
            </meshpatch>
          </meshrow>
        </meshgradient>
        """
    )

    descriptor = describe_gradient_element(element)

    assert isinstance(descriptor, MeshGradientDescriptor)
    assert descriptor.colors == ("0000FF", "FF0000")


def test_describe_pattern_element_accepts_calc_number_percent_geometry() -> None:
    element = etree.fromstring(
        """
        <pattern id="pat" x="calc(25% + 25%)" y="calc(2 * 3)"
                 width="50%" height="calc(1 / 4)"/>
        """
    )

    descriptor = describe_pattern_element(element)

    assert isinstance(descriptor, PatternDescriptor)
    assert descriptor.x == pytest.approx(0.5)
    assert descriptor.y == pytest.approx(6.0)
    assert descriptor.width == pytest.approx(0.5)
    assert descriptor.height == pytest.approx(0.25)
