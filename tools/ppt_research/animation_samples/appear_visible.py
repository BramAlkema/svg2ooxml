"""Appear (set visibility=visible) animation sample.

Slide 2 holds a rectangle that SMIL ``<set attributeName="visibility"
to="visible">`` makes visible on click. Exercises
:class:`SetAnimationHandler`'s visibility-visible path and the
``entr/appear`` oracle template (preset 1 Appear — single ``<p:set>``
child, no animEffect fade wrapper).
"""

from __future__ import annotations

from pathlib import Path

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.animation.handlers.set import SetAnimationHandler
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

NAME = "appear_visible"
DURATION_S = 2.5
PRE_ADVANCES = 1
# PPT auto-fires the clickEffect during the pre-advance slide transition, so
# a second advance would push past slide 2 and end the slideshow.
TRIGGER_ADVANCE = False


def build(output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    presentation, _slide, shape_id = new_presentation_with_hero_shape(
        fill=(140, 60, 200),
        label="Appear",
    )
    presentation.save(output_path)

    animation = AnimationDefinition(
        element_id=str(shape_id),
        animation_type=AnimationType.SET,
        target_attribute="visibility",
        values=["visible"],
        # Authored SMIL <set> is instantaneous, but PowerPoint collapses the
        # effect container once the outer par's duration elapses, which causes
        # the visibility set to revert. Hold the outer par open for 500 ms —
        # matches the oracle shape for preset 1 (Appear).
        timing=AnimationTiming(
            begin=0.0,
            duration=0.5,
            fill_mode=FillMode.FREEZE,
        ),
    )

    def _par_factory(xml_builder: AnimationXMLBuilder, par_id: int, behavior_id: int):
        handler = SetAnimationHandler(
            xml_builder,
            ValueProcessor(),
            TAVBuilder(xml_builder),
            UnitConverter(),
        )
        par = handler.build(animation, par_id, behavior_id)
        if par is None:
            raise RuntimeError("SetAnimationHandler declined to build visibility set")
        return par

    timing_xml = build_timing_xml(
        _par_factory,
        animated_shape_ids=[str(shape_id)],
        start_id=shape_id + 1,
    )
    inject_timing_into_pptx(output_path, timing_xml)
    return output_path


__all__ = ["NAME", "DURATION_S", "PRE_ADVANCES", "build"]
