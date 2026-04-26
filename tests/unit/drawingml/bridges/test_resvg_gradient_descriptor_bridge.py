from __future__ import annotations

import pytest
from lxml import etree

from svg2ooxml.drawingml.bridges.resvg_paint_bridge import (
    LinearGradientDescriptor,
    MeshGradientDescriptor,
    describe_gradient_element,
)


def test_describe_gradient_element_resolves_css_stop_colors_and_percent_opacity() -> None:
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
