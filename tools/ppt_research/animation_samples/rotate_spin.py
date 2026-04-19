"""Rotate (emph/spin) animation sample.

Slide 2 holds a rectangle that spins 360 degrees around its center. Drives
:class:`TransformAnimationHandler`'s SCALE/ROTATE/TRANSLATE dispatch and the
``emph/rotate`` oracle template.
"""

from __future__ import annotations

from pathlib import Path

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.animation.handlers.transform import (
    TransformAnimationHandler,
)
from svg2ooxml.drawingml.animation.tav_builder import TAVBuilder
from svg2ooxml.drawingml.animation.value_processors import ValueProcessor
from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    FillMode,
    TransformType,
)
from tools.ppt_research.animation_samples._common import (
    build_timing_xml,
    inject_timing_into_pptx,
    new_presentation_with_hero_shape,
)

NAME = "rotate_spin"
DURATION_S = 2.5
PRE_ADVANCES = 1


def build(output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    presentation, _slide, shape_id = new_presentation_with_hero_shape(
        fill=(70, 140, 220),
        label="Spin",
    )
    presentation.save(output_path)

    animation = AnimationDefinition(
        element_id=str(shape_id),
        animation_type=AnimationType.ANIMATE_TRANSFORM,
        target_attribute="transform",
        # 90 degrees so the end orientation is visibly different from the
        # start. A full 360 spin ends at the same pose, which makes the
        # pixel-delta metric blind once the animation settles.
        values=["0", "90"],
        timing=AnimationTiming(
            begin=0.0,
            duration=1.8,
            fill_mode=FillMode.FREEZE,
        ),
        transform_type=TransformType.ROTATE,
    )

    def _par_factory(xml_builder: AnimationXMLBuilder, par_id: int, behavior_id: int):
        handler = TransformAnimationHandler(
            xml_builder,
            ValueProcessor(),
            TAVBuilder(xml_builder),
            UnitConverter(),
        )
        par = handler.build(animation, par_id, behavior_id)
        if par is None:
            raise RuntimeError(
                "TransformAnimationHandler declined to build rotate spin"
            )
        return par

    timing_xml = build_timing_xml(
        _par_factory,
        animated_shape_ids=[str(shape_id)],
        start_id=shape_id + 1,
    )
    inject_timing_into_pptx(output_path, timing_xml)
    return output_path


__all__ = ["NAME", "DURATION_S", "PRE_ADVANCES", "build"]
