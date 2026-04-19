"""Fade-in animation sample.

Emits a single rectangle with a 1.5s opacity 0 → 1 entrance effect. The
underlying timing XML is generated through ``OpacityAnimationHandler`` so
edits to that handler are reflected end-to-end on rebuild.
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

NAME = "fade_in"
DURATION_S = 2.0  # 1.5s fade + 0.5s settle for capture tail
# Blank slide 1 → animated slide 2 advance before the click-group trigger.
PRE_ADVANCES = 1


def build(output_path: Path) -> Path:
    """Write the sample PPTX to *output_path* and return it."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    presentation, _slide, shape_id = new_presentation_with_hero_shape(
        label="Fade In",
    )
    presentation.save(output_path)

    animation = AnimationDefinition(
        element_id=str(shape_id),
        animation_type=AnimationType.ANIMATE,
        target_attribute="opacity",
        values=["0", "1"],
        timing=AnimationTiming(
            begin=0.0,
            duration=1.5,
            fill_mode=FillMode.FREEZE,
        ),
    )

    def _par_factory(
        xml_builder: AnimationXMLBuilder, par_id: int, behavior_id: int
    ):
        handler = OpacityAnimationHandler(
            xml_builder,
            ValueProcessor(),
            TAVBuilder(xml_builder),
            UnitConverter(),
        )
        par = handler.build(animation, par_id, behavior_id)
        if par is None:
            raise RuntimeError("OpacityAnimationHandler declined to build fade-in")
        return par

    timing_xml = build_timing_xml(
        _par_factory,
        animated_shape_ids=[str(shape_id)],
        start_id=shape_id + 1,
    )
    inject_timing_into_pptx(output_path, timing_xml)
    return output_path


__all__ = ["NAME", "DURATION_S", "build"]
