"""DrawingML animation writer using handler architecture.

Orchestrates all animation handlers to convert SVG animations into
PowerPoint timing XML.  All handlers return ``etree._Element`` and the
writer calls ``to_string()`` exactly once at the end.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.xml_builder import to_string
from svg2ooxml.ir.animation import AnimationDefinition, AnimationScene

from .handlers import (
    AnimationHandler,
    ColorAnimationHandler,
    MotionAnimationHandler,
    NumericAnimationHandler,
    OpacityAnimationHandler,
    SetAnimationHandler,
    TransformAnimationHandler,
)
from .id_allocator import TimingIDAllocator
from .policy import AnimationPolicy
from .tav_builder import TAVBuilder
from .value_processors import ValueProcessor
from .xml_builders import AnimationXMLBuilder

if TYPE_CHECKING:
    from svg2ooxml.core.tracing import ConversionTracer

__all__ = ["DrawingMLAnimationWriter"]

_logger = logging.getLogger(__name__)


class DrawingMLAnimationWriter:
    """Render animation definitions as DrawingML timing XML."""

    def __init__(self) -> None:
        self._unit_converter = UnitConverter()
        self._xml_builder = AnimationXMLBuilder()
        self._value_processor = ValueProcessor()
        self._tav_builder = TAVBuilder(self._xml_builder)
        self._id_allocator = TimingIDAllocator()
        self._policy: AnimationPolicy | None = None

        # Handlers in priority order (most specific first, catch-all last)
        self._handlers: list[AnimationHandler] = [
            OpacityAnimationHandler(
                self._xml_builder, self._value_processor,
                self._tav_builder, self._unit_converter,
            ),
            ColorAnimationHandler(
                self._xml_builder, self._value_processor,
                self._tav_builder, self._unit_converter,
            ),
            SetAnimationHandler(
                self._xml_builder, self._value_processor,
                self._tav_builder, self._unit_converter,
            ),
            MotionAnimationHandler(
                self._xml_builder, self._value_processor,
                self._tav_builder, self._unit_converter,
            ),
            TransformAnimationHandler(
                self._xml_builder, self._value_processor,
                self._tav_builder, self._unit_converter,
            ),
            NumericAnimationHandler(
                self._xml_builder, self._value_processor,
                self._tav_builder, self._unit_converter,
            ),
        ]

    def build(
        self,
        animations: Sequence[AnimationDefinition],
        timeline: Sequence[AnimationScene],
        *,
        tracer: ConversionTracer | None = None,
        options: Mapping[str, Any] | None = None,
        animated_shape_ids: list[str] | None = None,
    ) -> str:
        """Build PowerPoint timing XML for a sequence of animations."""
        options = dict(options or {})
        self._policy = AnimationPolicy(options)

        # Pre-allocate IDs for the complete timing tree
        ids = self._id_allocator.allocate(n_animations=len(animations))

        animation_elements: list[etree._Element] = []
        id_index = 0

        for animation in animations:
            anim_ids = ids.animations[id_index]
            id_index += 1

            elem, meta = self._build_animation(
                animation, options, anim_ids.par, anim_ids.behavior
            )

            _logger.debug(
                "Animation fragment for %s (%s): %s",
                animation.element_id,
                animation.target_attribute,
                "SUCCESS" if elem is not None else f"SKIPPED ({meta.get('reason') if meta else 'unknown'})",
            )

            if elem is not None:
                animation_elements.append(elem)
                if tracer is not None:
                    tracer.record_stage_event(
                        stage="animation",
                        action="fragment_emitted",
                        metadata={
                            "element_id": animation.element_id,
                            "animation_type": (
                                animation.animation_type.value
                                if hasattr(animation.animation_type, "value")
                                else str(animation.animation_type)
                            ),
                            "attribute": animation.target_attribute,
                            "fallback_mode": options.get("fallback_mode", "native"),
                        },
                    )
            elif tracer is not None:
                metadata: dict[str, Any] = {
                    "element_id": animation.element_id,
                    "animation_type": (
                        animation.animation_type.value
                        if hasattr(animation.animation_type, "value")
                        else str(animation.animation_type)
                    ),
                    "attribute": animation.target_attribute,
                    "fallback_mode": options.get("fallback_mode", "native"),
                }
                if meta:
                    metadata.update(meta)
                tracer.record_stage_event(
                    stage="animation",
                    action="fragment_skipped",
                    metadata=metadata,
                )

        if not animation_elements:
            return ""

        # Build the complete timing tree as a single element, then serialize once
        timing_tree = self._xml_builder.build_timing_tree(
            ids=ids,
            animation_elements=animation_elements,
            animated_shape_ids=animated_shape_ids or [],
        )
        return to_string(timing_tree)

    def _build_animation(
        self,
        animation: AnimationDefinition,
        options: Mapping[str, Any],
        par_id: int,
        behavior_id: int,
    ) -> tuple[etree._Element | None, dict[str, Any] | None]:
        """Build element for a single animation."""
        if self._policy is None:
            self._policy = AnimationPolicy(options)

        max_error = self._policy.estimate_spline_error(animation)
        should_skip, skip_reason = self._policy.should_skip(animation, max_error)
        if should_skip:
            return None, {"reason": skip_reason}

        handler = self._find_handler(animation)
        if handler is None:
            return None, {"reason": "no_handler_found"}

        try:
            result = handler.build(animation, par_id, behavior_id)
            if result is None:
                return None, {"reason": "handler_returned_empty"}
            return result, None
        except Exception as e:
            return None, {"reason": f"handler_error: {str(e)}"}

    def _find_handler(self, animation: AnimationDefinition) -> AnimationHandler | None:
        for handler in self._handlers:
            if handler.can_handle(animation):
                return handler
        return None
