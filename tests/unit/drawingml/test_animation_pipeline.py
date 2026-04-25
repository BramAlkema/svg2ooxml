"""Tests for DrawingML animation pipeline mapping."""

from __future__ import annotations

from svg2ooxml.drawingml.animation_pipeline import AnimationPipeline
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    BeginTrigger,
    BeginTriggerType,
)


def test_bookmark_navigation_list_remaps_indefinite_begin_to_click_trigger() -> None:
    pipeline = AnimationPipeline()
    animation = AnimationDefinition(
        element_id="target",
        animation_id="fadein",
        animation_type=AnimationType.ANIMATE,
        target_attribute="fill",
        values=["FFFFFF", "0000FF"],
        timing=AnimationTiming(
            begin=0.0,
            duration=1.0,
            begin_triggers=[BeginTrigger(BeginTriggerType.INDEFINITE)],
        ),
    )
    pipeline.reset({"definitions": [animation]})
    pipeline.register_mapping({"element_ids": ["target"]}, 2)
    pipeline.register_mapping(
        {
            "element_ids": ["button"],
            "navigation": [
                {"kind": "external", "href": "https://example.com"},
                {"kind": "bookmark", "bookmark": {"name": "fadein"}},
            ],
        },
        3,
    )

    xml = pipeline.build(max_shape_id=3)

    assert 'evt="onClick"' in xml
    assert '<p:spTgt spid="3"/>' in xml
