"""Tests for visibility animation compilation."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.drawingml.animation.visibility_compiler import (
    assign_missing_visibility_source_ids,
    compile_visibility_plans,
    rewrite_visibility_animations,
)
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    FillMode,
)
from svg2ooxml.ir.geometry import Point
from svg2ooxml.ir.scene import Scene
from svg2ooxml.ir.shapes import Circle

_NS = {"svg": "http://www.w3.org/2000/svg"}


def _make_scene(svg_text: str) -> tuple[etree._Element, Scene, str]:
    svg_root = etree.fromstring(svg_text.encode("utf-8"))
    assign_missing_visibility_source_ids(svg_root)
    circle_element = svg_root.xpath(".//svg:circle", namespaces=_NS)[0]
    target_id = circle_element.get("id") or circle_element.get("data-svg2ooxml-source-id")
    assert isinstance(target_id, str) and target_id
    scene = Scene(
        elements=[
            Circle(
                center=Point(10, 10),
                radius=5,
                metadata={"element_ids": [target_id]},
            )
        ]
    )
    return svg_root, scene, target_id


def test_assign_missing_visibility_source_ids_skips_animation_nodes() -> None:
    svg_root = etree.fromstring(
        b"""
        <svg xmlns="http://www.w3.org/2000/svg">
          <g>
            <circle cx="5" cy="5" r="3"/>
            <animate attributeName="display" from="none" to="inline" dur="1s"/>
          </g>
        </svg>
        """
    )

    assigned = assign_missing_visibility_source_ids(svg_root)

    group = svg_root.xpath(".//svg:g", namespaces=_NS)[0]
    circle = svg_root.xpath(".//svg:circle", namespaces=_NS)[0]
    animate = svg_root.xpath(".//svg:animate", namespaces=_NS)[0]
    assert assigned == 3  # svg, g, circle
    assert group.get("data-svg2ooxml-source-id")
    assert circle.get("data-svg2ooxml-source-id")
    assert animate.get("data-svg2ooxml-source-id") is None


def test_compile_visibility_plans_projects_group_display_to_leaf_target() -> None:
    svg_root, scene, target_id = _make_scene(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <g id="gate" display="none">
            <circle cx="10" cy="10" r="5"/>
          </g>
        </svg>
        """
    )
    animations = [
        AnimationDefinition(
            element_id="gate",
            animation_type=AnimationType.ANIMATE,
            target_attribute="display",
            values=["none", "inline"],
            timing=AnimationTiming(begin=0.0, duration=2.0, fill_mode=FillMode.FREEZE),
        )
    ]

    plans = compile_visibility_plans(animations, scene, svg_root)

    assert len(plans) == 1
    assert plans[0].target_id == target_id
    assert plans[0].intervals[0].visible is False
    assert plans[0].intervals[0].start == 0.0
    assert plans[0].intervals[0].end == 1.0
    assert plans[0].intervals[1].visible is True
    assert plans[0].intervals[1].start == 1.0
    assert plans[0].intervals[1].end is None


def test_compile_visibility_plans_respects_set_remove_fill() -> None:
    svg_root, scene, target_id = _make_scene(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <circle id="dot" display="none" cx="10" cy="10" r="5"/>
        </svg>
        """
    )
    animations = [
        AnimationDefinition(
            element_id="dot",
            animation_type=AnimationType.SET,
            target_attribute="display",
            values=["inline"],
            timing=AnimationTiming(begin=2.0, duration=1.0, fill_mode=FillMode.REMOVE),
        )
    ]

    plans = compile_visibility_plans(animations, scene, svg_root)

    assert len(plans) == 1
    intervals = plans[0].intervals
    assert [interval.visible for interval in intervals] == [False, True, False]
    assert intervals[0].start == 0.0 and intervals[0].end == 2.0
    assert intervals[1].start == 2.0 and intervals[1].end == 3.0
    assert intervals[2].start == 3.0 and intervals[2].end is None


def test_rewrite_visibility_animations_preserves_unrelated_effects() -> None:
    svg_root, scene, target_id = _make_scene(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <circle id="dot" display="none" cx="10" cy="10" r="5"/>
        </svg>
        """
    )
    animations = [
        AnimationDefinition(
            element_id=target_id,
            animation_type=AnimationType.ANIMATE,
            target_attribute="display",
            values=["none", "inline"],
            timing=AnimationTiming(begin=0.0, duration=2.0, fill_mode=FillMode.FREEZE),
        ),
        AnimationDefinition(
            element_id=target_id,
            animation_type=AnimationType.ANIMATE,
            target_attribute="opacity",
            values=["0", "1"],
            timing=AnimationTiming(begin=0.0, duration=2.0, fill_mode=FillMode.FREEZE),
        ),
    ]

    rewritten = rewrite_visibility_animations(animations, scene, svg_root)

    assert [animation.target_attribute for animation in rewritten].count("opacity") == 1
    assert all(animation.target_attribute != "display" for animation in rewritten)
    visibility_events = [
        animation for animation in rewritten if animation.target_attribute == "style.visibility"
    ]
    assert len(visibility_events) == 1
    assert visibility_events[0].values == ["visible"]
