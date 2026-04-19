"""Motion-path translate sample.

Slide 2 holds a rectangle that travels along a short horizontal path on
click. Exercises :class:`MotionAnimationHandler` and the ``path/motion``
oracle template (simple, non-rotating case).
"""

from __future__ import annotations

from pathlib import Path

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.animation.handlers.motion import MotionAnimationHandler
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

NAME = "motion_translate"
DURATION_S = 2.5
PRE_ADVANCES = 1


def build(output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    presentation, _slide, shape_id = new_presentation_with_hero_shape(
        fill=(230, 150, 30),
        label="Move",
    )
    presentation.save(output_path)

    # Motion path roughly 2 inches right, 0.5 inch down in slide-relative
    # coordinates. SMIL path values are projected through
    # ``MotionAnimationHandler._project_motion_points`` before emission.
    animation = AnimationDefinition(
        element_id=str(shape_id),
        animation_type=AnimationType.ANIMATE_MOTION,
        target_attribute="motion",
        values=["M 0 0 L 200 50"],
        timing=AnimationTiming(
            begin=0.0,
            duration=1.8,
            fill_mode=FillMode.FREEZE,
        ),
        motion_viewport_px=(914.0, 686.0),
    )

    def _par_factory(xml_builder: AnimationXMLBuilder, par_id: int, behavior_id: int):
        handler = MotionAnimationHandler(
            xml_builder,
            ValueProcessor(),
            TAVBuilder(xml_builder),
            UnitConverter(),
        )
        par = handler.build(animation, par_id, behavior_id)
        if par is None:
            raise RuntimeError("MotionAnimationHandler declined to build motion path")
        return par

    timing_xml = build_timing_xml(
        _par_factory,
        animated_shape_ids=[str(shape_id)],
        start_id=shape_id + 1,
    )
    inject_timing_into_pptx(output_path, timing_xml)
    return output_path


__all__ = ["NAME", "DURATION_S", "PRE_ADVANCES", "build"]
