from __future__ import annotations

from svg2ooxml.core.export.animation_values import (
    animation_length_bounds_or_default,
    animation_length_delta_px,
)
from svg2ooxml.core.export.variant_line_endpoints import (
    _compose_simple_line_endpoint_animations,
)
from svg2ooxml.core.export.variant_position_motions import (
    _coalesce_simple_position_motions,
)
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    CalcMode,
    TransformType,
)
from svg2ooxml.ir.geometry import Point
from svg2ooxml.ir.shapes import Line


def _animation(attribute: str, values: list[str], *, element_id: str = "shape") -> AnimationDefinition:
    return AnimationDefinition(
        element_id=element_id,
        animation_type=AnimationType.ANIMATE,
        target_attribute=attribute,
        values=values,
        timing=AnimationTiming(begin=0.0, duration=1.0),
    )


def test_animation_length_delta_resolves_calc_values() -> None:
    animation = _animation("x", ["calc(10px + 5px)", "calc(40px + 5px)"])

    assert animation_length_delta_px(animation) == 30.0


def test_animation_length_bounds_falls_back_on_invalid_values() -> None:
    animation = _animation("y", ["bad", "calc(10px)"])

    assert animation_length_bounds_or_default(
        animation,
        axis="y",
        default=7.0,
    ) == (7.0, 7.0)


def test_position_motion_composition_resolves_calc_values() -> None:
    scene = IRScene(elements=[])
    animations = [
        _animation("x", ["calc(10px)", "calc(40px)"]),
        _animation("y", ["calc(5px)", "calc(10px)"]),
    ]

    rewritten = _coalesce_simple_position_motions(animations, scene)

    assert len(rewritten) == 1
    assert rewritten[0].animation_type == AnimationType.ANIMATE_MOTION
    assert rewritten[0].values == ["M 0 0 L 30 5 E"]


def test_line_endpoint_composition_resolves_calc_values() -> None:
    scene = IRScene(
        elements=[
            Line(
                start=Point(30.0, 50.0),
                end=Point(10.0, 10.0),
                metadata={"element_ids": ["line"]},
            )
        ]
    )
    animations = [
        _animation("x1", ["calc(30px)", "calc(50px)"], element_id="line"),
        _animation("x", ["calc(10px)", "calc(20px)"], element_id="line"),
    ]

    rewritten = _compose_simple_line_endpoint_animations(animations, scene)

    assert [animation.animation_type for animation in rewritten] == [
        AnimationType.ANIMATE_MOTION,
        AnimationType.ANIMATE_TRANSFORM,
    ]
    assert rewritten[0].values == ["M 0 0 L 20 0 E"]
    assert rewritten[1].transform_type == TransformType.SCALE
    assert rewritten[1].calc_mode == CalcMode.LINEAR
    assert rewritten[1].values == ["1 1", "2 1"]
