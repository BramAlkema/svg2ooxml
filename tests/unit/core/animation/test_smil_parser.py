from __future__ import annotations

from lxml import etree

from svg2ooxml.core.animation import SMILParser
from svg2ooxml.ir.animation import AnimationType, BeginTriggerType, CalcMode, TransformType


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


def test_parse_begin_event_triggers() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="opacity" values="0;1" begin="shape.end+0.5s;click" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.timing.begin == 0.0
    assert animation.timing.begin_triggers is not None
    assert len(animation.timing.begin_triggers) == 2
    assert animation.timing.begin_triggers[0].trigger_type is BeginTriggerType.ELEMENT_END
    assert animation.timing.begin_triggers[0].target_element_id == "shape"
    assert animation.timing.begin_triggers[0].delay_seconds == 0.5
    assert animation.timing.begin_triggers[1].trigger_type is BeginTriggerType.CLICK
    assert animation.timing.begin_triggers[1].target_element_id is None


def test_parse_invalid_begin_expression_adds_warning_and_falls_back() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="opacity" values="0;1" begin="shape.end+oops" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.timing.begin == 0.0
    assert animation.timing.begin_triggers is not None
    assert len(animation.timing.begin_triggers) == 1
    assert animation.timing.begin_triggers[0].trigger_type is BeginTriggerType.TIME_OFFSET
    assert parser.animation_summary.warnings
    assert any("Invalid begin expression" in warning for warning in parser.animation_summary.warnings)


def test_parse_begin_click_with_offset() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="opacity" values="0;1" begin="click+0.5s" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.timing.begin == 0.0
    assert animation.timing.begin_triggers is not None
    assert len(animation.timing.begin_triggers) == 1
    assert animation.timing.begin_triggers[0].trigger_type is BeginTriggerType.CLICK
    assert animation.timing.begin_triggers[0].delay_seconds == 0.5


def test_parse_descending_key_times_falls_back_with_warning() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="x" values="0;10;20" keyTimes="0;0.7;0.2" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.key_times is None
    assert parser.animation_summary.warnings
    assert any("keyTimes must be in ascending order" in warning for warning in parser.animation_summary.warnings)


def test_parse_key_splines_without_spline_mode_are_ignored() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="x" values="0;10" keySplines="0.25 0.1 0.25 1" calcMode="linear" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.calc_mode == CalcMode.LINEAR
    assert animation.key_splines is None
    assert parser.animation_summary.warnings
    assert any("Ignoring keySplines because calcMode is not spline" in warning for warning in parser.animation_summary.warnings)


def test_parse_invalid_key_splines_count_falls_back() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="x" values="0;10;20" keyTimes="0;0.5;1" keySplines="0.25 0.1 0.25 1" calcMode="spline" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.calc_mode == CalcMode.SPLINE
    assert animation.key_splines is None
    assert parser.animation_summary.warnings
    assert any("keySplines length mismatch" in warning for warning in parser.animation_summary.warnings)


def test_parse_animate_motion_resolves_mpath_reference() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
          <path id="motionPath" d="M 0 0 L 10 10" />
          <rect id="shape">
            <animateMotion dur="1s">
              <mpath xlink:href="#motionPath" />
            </animateMotion>
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.animation_type is AnimationType.ANIMATE_MOTION
    assert animation.values == ["M 0 0 L 10 10"]


def test_parse_animate_motion_rotate_mode() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animateMotion dur="1s" path="M0,0 L10,0" rotate="auto-reverse" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.animation_type is AnimationType.ANIMATE_MOTION
    assert animation.motion_rotate == "auto-reverse"


def test_parse_animate_motion_keeps_key_times_for_path() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animateMotion dur="1s" path="M0,0 L100,0" keyTimes="0;0.5;1" calcMode="discrete" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.animation_type is AnimationType.ANIMATE_MOTION
    assert animation.calc_mode == CalcMode.DISCRETE
    assert animation.key_times == [0.0, 0.5, 1.0]


def test_parse_animate_motion_unresolved_mpath_adds_warning() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
          <rect id="shape">
            <animateMotion dur="1s">
              <mpath xlink:href="#missingPath" />
            </animateMotion>
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.values == ["M 0,0"]
    assert parser.animation_summary.warnings
    assert any("mpath reference unresolved" in warning for warning in parser.animation_summary.warnings)
