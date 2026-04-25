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
