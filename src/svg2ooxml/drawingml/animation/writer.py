"""New DrawingML animation writer using handler architecture.

This module orchestrates all animation handlers to convert SVG animations
into PowerPoint timing XML.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Sequence

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.ir.animation import AnimationDefinition, AnimationScene

from .handlers import (
    AnimationHandler,
    OpacityAnimationHandler,
    ColorAnimationHandler,
    NumericAnimationHandler,
    TransformAnimationHandler,
    MotionAnimationHandler,
    SetAnimationHandler,
)
from .xml_builders import AnimationXMLBuilder
from .value_processors import ValueProcessor
from .tav_builder import TAVBuilder
from .policy import AnimationPolicy

if TYPE_CHECKING:
    from svg2ooxml.core.tracing import ConversionTracer

__all__ = ["DrawingMLAnimationWriter"]


class DrawingMLAnimationWriter:
    """Render animation definitions as DrawingML timing XML."""

    def __init__(self) -> None:
        """Initialize the animation writer with all components and handlers."""
        self._id_counter = 1  # Reset to 1 to match professional templates

        # Initialize core components
        self._unit_converter = UnitConverter()
        self._xml_builder = AnimationXMLBuilder()
        self._value_processor = ValueProcessor()
        self._tav_builder = TAVBuilder(self._xml_builder)
        # Policy will be initialized per-build with options
        self._policy: AnimationPolicy | None = None

        # Initialize all handlers in priority order
        self._handlers: list[AnimationHandler] = [
            OpacityAnimationHandler(
                self._xml_builder,
                self._value_processor,
                self._tav_builder,
                self._unit_converter,
            ),
            ColorAnimationHandler(
                self._xml_builder,
                self._value_processor,
                self._tav_builder,
                self._unit_converter,
            ),
            SetAnimationHandler(
                self._xml_builder,
                self._value_processor,
                self._tav_builder,
                self._unit_converter,
            ),
            MotionAnimationHandler(
                self._xml_builder,
                self._value_processor,
                self._tav_builder,
                self._unit_converter,
            ),
            TransformAnimationHandler(
                self._xml_builder,
                self._value_processor,
                self._tav_builder,
                self._unit_converter,
            ),
            NumericAnimationHandler(
                self._xml_builder,
                self._value_processor,
                self._tav_builder,
                self._unit_converter,
            ),
        ]

    def build(
        self,
        animations: Sequence[AnimationDefinition],
        timeline: Sequence[AnimationScene],
        *,
        tracer: "ConversionTracer | None" = None,
        options: Mapping[str, Any] | None = None,
        animated_shape_ids: list[str] | None = None,
    ) -> str:
        """Build PowerPoint timing XML for a sequence of animations."""
        options = dict(options or {})

        # Initialize policy with build options
        self._policy = AnimationPolicy(options)

        fragments: list[str] = []
        last_skip_reason: str | None = None

        import logging
        debug_logger = logging.getLogger("drawingml.animation_writer")
        
        # Process each animation
        for animation in animations:
            fragment, fragment_meta = self._build_animation(animation, options)
            debug_logger.debug("Animation fragment for %s (%s): %s", animation.element_id, animation.target_attribute, "SUCCESS" if fragment else f"SKIPPED ({fragment_meta.get('reason') if fragment_meta else 'unknown'})")

            if fragment:
                # Animation was successfully converted
                fragments.append(fragment)
                if tracer is not None:
                    event_meta = {
                        "element_id": animation.element_id,
                        "animation_type": (
                            animation.animation_type.value
                            if hasattr(animation.animation_type, "value")
                            else str(animation.animation_type)
                        ),
                        "attribute": animation.target_attribute,
                        "fallback_mode": options.get("fallback_mode", "native"),
                    }
                    tracer.record_stage_event(
                        stage="animation",
                        action="fragment_emitted",
                        metadata=event_meta,
                    )
            elif tracer is not None:
                # Animation was skipped
                metadata = {
                    "element_id": animation.element_id,
                    "animation_type": (
                        animation.animation_type.value
                        if hasattr(animation.animation_type, "value")
                        else str(animation.animation_type)
                    ),
                    "attribute": animation.target_attribute,
                    "fallback_mode": options.get("fallback_mode", "native"),
                }
                if fragment_meta:
                    metadata.update(fragment_meta)
                    if fragment_meta.get("reason"):
                        last_skip_reason = fragment_meta["reason"]
                tracer.record_stage_event(
                    stage="animation",
                    action="fragment_skipped",
                    metadata=metadata,
                )

        # If no animations converted successfully, return empty
        if not fragments:
            return ""

        # Build complete timing XML using the builder to get mainSeq wrapping
        return self._xml_builder.build_timing_container(
            timing_id=self._next_id(),
            fragments=fragments,
            animated_shape_ids=animated_shape_ids or []
        )

    def _build_animation(
        self,
        animation: AnimationDefinition,
        options: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        """Build XML for a single animation."""
        if self._policy is None:
            self._policy = AnimationPolicy(options)

        # Check if animation should be skipped
        max_error = self._policy.estimate_spline_error(animation)
        should_skip, skip_reason = self._policy.should_skip(animation, max_error)

        if should_skip:
            return "", {"reason": skip_reason}

        # Find appropriate handler
        handler = self._find_handler(animation)
        if handler is None:
            return "", {"reason": "no_handler_found"}

        # Allocate IDs for this animation
        par_id, behavior_id = self._allocate_ids()

        # Build XML using handler
        try:
            xml = handler.build(animation, par_id, behavior_id)
            if not xml:
                return "", {"reason": "handler_returned_empty"}
            return xml, None
        except Exception as e:
            return "", {"reason": f"handler_error: {str(e)}"}

    def _find_handler(self, animation: AnimationDefinition) -> AnimationHandler | None:
        """Find the first handler that can process this animation."""
        for handler in self._handlers:
            if handler.can_handle(animation):
                return handler
        return None

    def _next_id(self) -> int:
        """Generate next unique ID for timing elements."""
        current_id = self._id_counter
        self._id_counter += 1
        return current_id

    def _allocate_ids(self) -> tuple[int, int]:
        """Allocate pair of IDs (par_id, behavior_id) for an animation."""
        par_id = self._next_id()
        behavior_id = self._next_id()
        return par_id, behavior_id