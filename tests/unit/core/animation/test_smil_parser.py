from __future__ import annotations

from lxml import etree

from svg2ooxml.core.animation import SMILParser, SMILParsingError
from svg2ooxml.ir.animation import AnimationType, TransformType


def _parse(svg: str):
    return etree.fromstring(svg.encode("utf-8"))


def test_parse_simple_animate() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="opacity" values="0;1" begin="1s" dur="2s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.element_id == "shape"
    assert animation.animation_type is AnimationType.ANIMATE
    assert animation.timing.begin == 1.0
    assert animation.timing.duration == 2.0
    assert animation.values == ["0", "1"]


def test_parse_transform_animation() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <g id="shape">
            <animateTransform attributeName="transform" type="rotate" from="0" to="90" dur="3s" />
          </g>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.animation_type is AnimationType.ANIMATE_TRANSFORM
    assert animation.transform_type is TransformType.ROTATE
    assert animation.values == ["0", "90"]


def test_summary_tracks_features() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="opacity" values="0;1" dur="2s" begin="0.5s" />
            <animateColor attributeName="fill" values="#000000;#ffffff" dur="1s" />
          </rect>
        </svg>
        """
    )

    parser.parse_svg_animations(svg)
    summary = parser.get_animation_summary()
    assert summary.total_animations == 2
    assert summary.has_color_animations
    assert summary.has_sequences
    assert summary.duration == 2.5


def test_invalid_animation_value_adds_warning() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="opacity" />
          </rect>
        </svg>
        """
    )

    parser.parse_svg_animations(svg)
    assert parser.animation_summary.warnings
