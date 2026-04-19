"""Color change (emph) animation sample.

Builds a two-slide deck where slide 2 holds a red rectangle that transitions
to blue on click. Exercises :class:`ColorAnimationHandler` and the
``emph/color`` oracle template.
"""

from __future__ import annotations

from pathlib import Path

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.animation.handlers.color import ColorAnimationHandler
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

NAME = "color_change"
DURATION_S = 2.5
PRE_ADVANCES = 1


def build(output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    presentation, _slide, shape_id = new_presentation_with_hero_shape(
        fill=(220, 40, 40),
        label="Color",
    )
    presentation.save(output_path)

    animation = AnimationDefinition(
        element_id=str(shape_id),
        animation_type=AnimationType.ANIMATE,
        target_attribute="fill",
        values=["#DC2828", "#2240DC"],
        timing=AnimationTiming(
            begin=0.0,
            duration=2.0,
            fill_mode=FillMode.FREEZE,
        ),
    )

    def _par_factory(xml_builder: AnimationXMLBuilder, par_id: int, behavior_id: int):
        handler = ColorAnimationHandler(
            xml_builder,
            ValueProcessor(),
            TAVBuilder(xml_builder),
            UnitConverter(),
        )
        par = handler.build(animation, par_id, behavior_id)
        if par is None:
            raise RuntimeError("ColorAnimationHandler declined to build color tween")
        return par

    timing_xml = build_timing_xml(
        _par_factory,
        animated_shape_ids=[str(shape_id)],
        start_id=shape_id + 1,
    )
    inject_timing_into_pptx(output_path, timing_xml)
    return output_path


__all__ = ["NAME", "DURATION_S", "PRE_ADVANCES", "build"]
