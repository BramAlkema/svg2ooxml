from __future__ import annotations

from collections import Counter

import pytest
from lxml import etree
from tools.visual.w3c_animation_suite import SCENARIOS

from svg2ooxml.core.animation import SMILParser
from svg2ooxml.ir.animation import (
    AnimationType,
    BeginTriggerType,
    CalcMode,
    FillMode,
    TransformType,
)

_ANIMATION_TAGS = {"animate", "animateTransform", "animateColor", "animateMotion", "set"}


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


def test_parse_animation_id_is_preserved_for_begin_references() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate id="grow" attributeName="width" values="10;20" dur="1s" begin="0s" />
            <animate attributeName="opacity" values="0;1" begin="grow.end" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 2
    assert animations[0].animation_id == "grow"
    assert animations[1].timing.begin_triggers is not None
    assert animations[1].timing.begin_triggers[0].target_element_id == "grow"


def test_parse_preserves_document_order_across_animation_element_types() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animateTransform id="first" attributeName="transform" type="translate" values="0 0;10 0" dur="1s" />
            <animate id="second" attributeName="opacity" values="0;1" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert [animation.animation_id for animation in animations] == ["first", "second"]


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


def test_parse_begin_click_with_offset_and_spaces() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="opacity" values="0;1" begin="click + 0.5s" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.timing.begin_triggers is not None
    assert len(animation.timing.begin_triggers) == 1
    assert animation.timing.begin_triggers[0].trigger_type is BeginTriggerType.CLICK
    assert animation.timing.begin_triggers[0].delay_seconds == 0.5


def test_parse_element_event_offset_with_spaces() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="opacity" values="0;1" begin="shape.click + 250ms; shape.end - 0.25s" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    animation = animations[0]
    assert animation.timing.begin_triggers is not None
    assert len(animation.timing.begin_triggers) == 2
    assert animation.timing.begin_triggers[0].trigger_type is BeginTriggerType.CLICK
    assert animation.timing.begin_triggers[0].target_element_id == "shape"
    assert animation.timing.begin_triggers[0].delay_seconds == 0.25
    assert animation.timing.begin_triggers[1].trigger_type is BeginTriggerType.ELEMENT_END
    assert animation.timing.begin_triggers[1].target_element_id == "shape"
    assert animation.timing.begin_triggers[1].delay_seconds == -0.25


def test_parse_begin_event_trigger_plumbing_variants() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="opacity" values="0;1"
                     begin="base.repeat(3)+2s; repeatBase.repeat(1/4);
                            accessKey(a)-1s;
                            wallclock(2000-01-01T00:00:00Z);
                            shape.mouseover+250ms"
                     dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    triggers = animations[0].timing.begin_triggers
    assert triggers is not None
    assert len(triggers) == 5
    assert triggers[0].trigger_type is BeginTriggerType.ELEMENT_REPEAT
    assert triggers[0].target_element_id == "base"
    assert triggers[0].event_name == "repeat"
    assert triggers[0].repeat_iteration == 3
    assert triggers[0].delay_seconds == pytest.approx(2.0)
    assert triggers[1].trigger_type is BeginTriggerType.ELEMENT_REPEAT
    assert triggers[1].target_element_id == "repeatBase"
    assert triggers[1].repeat_iteration == "1/4"
    assert triggers[2].trigger_type is BeginTriggerType.ACCESS_KEY
    assert triggers[2].access_key == "a"
    assert triggers[2].delay_seconds == pytest.approx(-1.0)
    assert triggers[3].trigger_type is BeginTriggerType.WALLCLOCK
    assert triggers[3].wallclock_value == "2000-01-01T00:00:00Z"
    assert triggers[4].trigger_type is BeginTriggerType.EVENT
    assert triggers[4].target_element_id == "shape"
    assert triggers[4].event_name == "mouseover"
    assert triggers[4].delay_seconds == pytest.approx(0.25)
    assert parser.get_degradation_reasons() == {}


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
    assert parser.get_degradation_reasons().get("key_times_not_ascending") == 1


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
    assert parser.get_degradation_reasons().get("key_splines_length_mismatch") == 1


def test_reset_summary_clears_degradation_reasons() -> None:
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

    parser.parse_svg_animations(svg)
    assert parser.get_degradation_reasons().get("key_times_not_ascending") == 1

    parser.reset_summary()
    assert parser.get_degradation_reasons() == {}


def test_parse_resets_summary_between_calls() -> None:
    parser = SMILParser()
    invalid_svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="x" values="0;10;20" keyTimes="0;0.7;0.2" dur="1s" />
          </rect>
        </svg>
        """
    )
    valid_svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="opacity" values="0;1" dur="1s" />
          </rect>
        </svg>
        """
    )

    parser.parse_svg_animations(invalid_svg)
    assert parser.get_degradation_reasons()

    animations = parser.parse_svg_animations(valid_svg)

    assert len(animations) == 1
    assert parser.get_degradation_reasons() == {}
    assert parser.get_animation_summary().warnings == []
    assert parser.get_animation_summary().total_animations == 1


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


def test_parse_animate_motion_resolves_unnamespaced_mpath_reference() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg>
          <path id="motionPath" d="M 0 0 L 10 10" />
          <rect id="shape">
            <animateMotion dur="1s">
              <mpath href="#motionPath" />
            </animateMotion>
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].values == ["M 0 0 L 10 10"]


def test_parse_animate_motion_falls_back_to_xlink_href_when_href_empty() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
          <path id="motionPath" d="M 0 0 L 10 10" />
          <rect id="shape">
            <animateMotion dur="1s">
              <mpath href="" xlink:href="#motionPath" />
            </animateMotion>
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].values == ["M 0 0 L 10 10"]


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


def test_parse_animate_motion_defaults_calc_mode_to_paced() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animateMotion values="0,0;100,0;100,100" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)
    assert len(animations) == 1
    assert animations[0].calc_mode == CalcMode.PACED


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


def test_parse_animate_motion_spline_synthesizes_path_key_times() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animateMotion values="0,0;10,0;20,0"
                           calcMode="spline"
                           keySplines="0 0 1 1;0.25 0.1 0.25 1"
                           dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    animation = animations[0]
    assert animation.animation_type is AnimationType.ANIMATE_MOTION
    assert animation.key_times == [0.0, 0.5, 1.0]
    assert animation.key_splines == [[0.0, 0.0, 1.0, 1.0], [0.25, 0.1, 0.25, 1.0]]
    assert parser.get_degradation_reasons() == {}


def test_parse_animate_motion_records_target_motion_space_matrix() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <g transform="matrix(2 0 0 3 50 90)">
            <rect id="shape" width="10" height="10">
              <animateMotion dur="1s" path="M0,0 L10,5" />
            </rect>
          </g>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].motion_space_matrix == (2.0, 0.0, 0.0, 3.0, 50.0, 90.0)


def test_parse_numeric_position_animation_records_target_motion_space_matrix() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <g transform="matrix(2 0 0 3 50 90)">
            <rect id="shape" width="10" height="10">
              <animate attributeName="x" from="0" to="10" dur="1s" />
            </rect>
          </g>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].motion_space_matrix == (2.0, 0.0, 0.0, 3.0, 50.0, 90.0)


def test_parse_translate_transform_records_target_motion_space_matrix() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <g transform="matrix(2 0 0 3 50 90)">
            <rect id="shape" width="10" height="10">
              <animateTransform attributeName="transform" type="translate"
                                from="0 0" to="10 5" dur="1s" />
            </rect>
          </g>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].motion_space_matrix == (2.0, 0.0, 0.0, 3.0, 50.0, 90.0)


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


def test_parse_from_by_values_and_preserves_raw_value_attrs() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="x" attributeType="XML" from="10" by="5" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    animation = animations[0]
    assert animation.values == ["10", "15"]
    assert animation.attribute_type == "XML"
    assert animation.from_value == "10"
    assert animation.by_value == "5"
    assert animation.to_value is None
    assert animation.raw_attributes["by"] == "5"


def test_parse_from_by_compact_signed_numeric_lists() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="points" from="10-20" by="5 6" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].values == ["10-20", "15 -14"]


def test_parse_from_by_unit_values_degrades_without_partial_numeric_math() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="x" from="10px" by="5" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].values == ["10px", "5"]
    assert parser.get_degradation_reasons()["by_value_non_numeric"] == 1


def test_parse_records_target_tag_for_text_animation() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <text id="headline" x="10" y="20">
            Hello
            <animate attributeName="fill" values="#000000;#ff0000;#000000" dur="2s" />
          </text>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].raw_attributes["svg2ooxml_target_tag"] == "text"


def test_parse_to_by_values_derives_start_when_numeric() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="x" to="15" by="5" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].values == ["10", "15"]
    assert animations[0].to_value == "15"
    assert animations[0].by_value == "5"


def test_parse_to_only_values_can_use_underlying_target_attribute() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape" x="-6">
            <animate attributeName="x" to="74" calcMode="discrete"
                     keyTimes="0;0.25" dur="8s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].values == ["-6", "74"]
    assert animations[0].key_times == [0.0, 0.25]
    assert animations[0].to_value == "74"
    assert parser.get_degradation_reasons() == {}


def test_parse_explicit_target_attribute_beats_parent_fallback() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="target" opacity="0.25" />
          <g>
            <animate target="#target" attributeName="opacity" to="1" dur="1s" />
          </g>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].element_id == "target"
    assert animations[0].values == ["0.25", "1"]
    assert animations[0].raw_attributes["svg2ooxml_target_tag"] == "rect"
    assert svg.xpath(".//svg:g", namespaces={"svg": "http://www.w3.org/2000/svg"})[0].get("id") is None


def test_parse_synthetic_target_ids_do_not_collide_with_existing_ids() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="anim-target-0" />
          <rect>
            <animate attributeName="opacity" values="0;1" dur="1s" />
          </rect>
          <circle>
            <animate attributeName="opacity" values="1;0" dur="1s" />
          </circle>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert [animation.element_id for animation in animations] == [
        "anim-target-1",
        "anim-target-2",
    ]


def test_parse_by_only_animation_does_not_drop_definition() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="x" by="5" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].values == ["5"]
    assert animations[0].by_value == "5"


def test_parse_repeat_dur_end_and_key_points_plumbing() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animateMotion path="M0,0 L100,0"
                           keyTimes="0;.25;1"
                           keyPoints="0;.5;1"
                           begin="1s"
                           end="shape.click + 250ms; 5s"
                           dur="2s"
                           repeatCount="indefinite"
                           repeatDur="6s"
                           min="500ms"
                           max="10s"
                           restart="whenNotActive" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    animation = animations[0]
    assert animation.key_times == [0.0, 0.25, 1.0]
    assert animation.key_points == [0.0, 0.5, 1.0]
    assert animation.timing.repeat_count == "indefinite"
    assert animation.timing.repeat_duration == 6.0
    assert animation.repeat_duration_ms == 6000
    assert animation.min_ms == 500
    assert animation.max_ms == 10000
    assert animation.restart == "whenNotActive"
    assert animation.timing.end_triggers is not None
    assert len(animation.timing.end_triggers) == 2
    assert animation.timing.end_triggers[0].trigger_type is BeginTriggerType.CLICK
    assert animation.timing.end_triggers[0].target_element_id == "shape"
    assert animation.timing.end_triggers[0].delay_seconds == pytest.approx(0.25)
    assert animation.timing.end_triggers[1].trigger_type is BeginTriggerType.TIME_OFFSET
    assert animation.timing.end_triggers[1].delay_seconds == pytest.approx(5.0)


def test_parse_fractional_repeat_count_sets_active_duration_cap() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="x" values="0;10" begin="0s" dur="2s" repeatCount="2.5" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    animation = animations[0]
    assert animation.timing.repeat_count == 3
    assert animation.timing.repeat_duration == pytest.approx(5.0)


def test_parse_timing_keywords_are_case_and_space_insensitive() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="x" values="0;10" dur=" Indefinite "
                     repeatCount=" INDEFINITE " repeatDur=" INDEFINITE "
                     fill=" Freeze " />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].timing.duration == float("inf")
    assert animations[0].timing.repeat_count == "indefinite"
    assert animations[0].timing.repeat_duration is None
    assert animations[0].timing.fill_mode is FillMode.FREEZE


def test_parse_invalid_duration_suffix_falls_back_with_warning() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="x" values="0;10" dur="oopsms" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].timing.duration == pytest.approx(1.0)
    assert any("Invalid dur value" in warning for warning in parser.animation_summary.warnings)
    assert parser.get_degradation_reasons().get("duration_invalid") == 1


def test_parse_key_points_on_non_motion_are_ignored_with_warning() -> None:
    parser = SMILParser()
    svg = _parse(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect id="shape">
            <animate attributeName="x" values="0;10" keyPoints="0;1" dur="1s" />
          </rect>
        </svg>
        """
    )

    animations = parser.parse_svg_animations(svg)

    assert len(animations) == 1
    assert animations[0].key_points is None
    assert any("Ignoring keyPoints" in warning for warning in parser.animation_summary.warnings)
    assert parser.get_degradation_reasons().get("key_points_non_motion") == 1


def test_w3c_animation_corpus_parse_plumbing_has_no_drops_or_degradations() -> None:
    total_elements = 0
    parsed_definitions = 0
    degraded: list[tuple[str, dict[str, int], list[str]]] = []
    reasons: Counter[str] = Counter()

    for name, path in SCENARIOS.items():
        root = etree.fromstring(path.read_text(encoding="utf-8").encode("utf-8"))
        elements = [
            element
            for element in root.iter()
            if isinstance(element.tag, str)
            and etree.QName(element).localname in _ANIMATION_TAGS
        ]
        total_elements += len(elements)

        parser = SMILParser()
        animations = parser.parse_svg_animations(root)
        parsed_definitions += len(animations)
        reason_map = parser.get_degradation_reasons()
        reasons.update(reason_map)
        warnings = parser.get_animation_summary().warnings
        if len(animations) != len(elements) or reason_map or warnings:
            degraded.append((name, reason_map, list(warnings)))

    assert total_elements > 0
    assert parsed_definitions == total_elements
    assert dict(reasons) == {}
    assert degraded == []
