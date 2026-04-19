"""Exit fade (opacity 1 -> 0) animation sample.

Slide 2 holds a rectangle that fades out on click. Exercises
:class:`OpacityAnimationHandler`'s authored-fade path with ``transition="out"``
and the ``exit/fade`` oracle template. Verification of this slot is
especially important because the oracle corpus contains no preset 9 exit
fade — our template is a mirror of ``entr/fade``, and PowerPoint may
reject the preset ID for an exit entry.
"""

from __future__ import annotations

from pathlib import Path

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.animation.handlers.opacity import OpacityAnimationHandler
from svg2ooxml.drawingml.animation.tav_builder import TAVBuilder
from svg2ooxml.drawingml.animation.value_processors import ValueProcessor
from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    FillMode,
)
from tools.ppt_research.animation_samples._common import (
    build_timing_xml,
    inject_timing_into_pptx,
    new_presentation_with_hero_shape,
)

NAME = "exit_fade"
DURATION_S = 2.5
PRE_ADVANCES = 1


def build(output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    presentation, _slide, shape_id = new_presentation_with_hero_shape(
        fill=(200, 60, 60),
        label="Fade Out",
    )
    presentation.save(output_path)

    animation = AnimationDefinition(
        element_id=str(shape_id),
        animation_type=AnimationType.ANIMATE,
        target_attribute="opacity",
        values=["1", "0"],
        timing=AnimationTiming(
            begin=0.0,
            duration=1.5,
            fill_mode=FillMode.FREEZE,
        ),
    )

    def _par_factory(xml_builder: AnimationXMLBuilder, par_id: int, behavior_id: int):
        handler = OpacityAnimationHandler(
            xml_builder,
            ValueProcessor(),
            TAVBuilder(xml_builder),
            UnitConverter(),
        )
        par = handler.build(animation, par_id, behavior_id)
        if par is None:
            raise RuntimeError("OpacityAnimationHandler declined to build fade-out")
        return par

    timing_xml = build_timing_xml(
        _par_factory,
        animated_shape_ids=[str(shape_id)],
        start_id=shape_id + 1,
    )
    inject_timing_into_pptx(output_path, timing_xml)
    return output_path


__all__ = ["NAME", "DURATION_S", "PRE_ADVANCES", "build"]
