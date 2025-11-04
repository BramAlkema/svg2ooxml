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
    """Render animation definitions as DrawingML timing XML.

    This class orchestrates multiple specialized handlers to convert
    SVG animation definitions into PowerPoint timing XML. Each handler
    is responsible for a specific animation type (opacity, color, transforms, etc.).

    The writer:
    1. Checks if animations should be skipped (via policy)
    2. Selects appropriate handler for each animation
    3. Delegates XML generation to handlers
    4. Wraps results in PowerPoint timing structure
    5. Integrates with conversion tracer for diagnostics

    Example:
        >>> writer = DrawingMLAnimationWriter()
        >>> xml = writer.build(animations, timeline, tracer=tracer)
    """

    def __init__(self) -> None:
        """Initialize the animation writer with all components and handlers."""
        self._id_counter = 1000  # Offset to avoid collisions with shape IDs

        # Initialize core components
        self._unit_converter = UnitConverter()
        self._xml_builder = AnimationXMLBuilder()
        self._value_processor = ValueProcessor()
        self._tav_builder = TAVBuilder(self._xml_builder)
        # Policy will be initialized per-build with options
        self._policy: AnimationPolicy | None = None

        # Initialize all handlers in priority order
        # Order matters: more specific handlers should come first
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
            # NumericAnimationHandler is the catch-all (must be last)
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
    ) -> str:
        """Build PowerPoint timing XML for a sequence of animations.

        Args:
            animations: Animation definitions to convert
            timeline: Animation timeline/scenes (currently unused in new architecture)
            tracer: Optional conversion tracer for diagnostics
            options: Optional configuration (e.g., max_spline_error, fallback_mode)

        Returns:
            PowerPoint <p:timing> XML fragment, or empty string if no animations

        Example:
            >>> xml = writer.build([animation1, animation2], timeline, tracer=tracer)
        """
        options = dict(options or {})

        # Initialize policy with build options
        self._policy = AnimationPolicy(options)

        fragments: list[str] = []
        last_skip_reason: str | None = None

        # Process each animation
        for animation in animations:
            fragment, fragment_meta = self._build_animation(animation, options)

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
                    if fragment_meta and "max_spline_error" in fragment_meta:
                        event_meta["max_spline_error"] = fragment_meta[
                            "max_spline_error"
                        ]
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
            if tracer is not None and animations:
                metadata = {
                    "reason": "no_supported_animations",
                    "animation_count": len(animations),
                    "fallback_mode": options.get("fallback_mode", "native"),
                }
                if last_skip_reason:
                    metadata["skip_reason"] = last_skip_reason
                tracer.record_stage_event(
                    stage="animation",
                    action="fragment_bundle_skipped",
                    metadata=metadata,
                )
            return ""

        # Build complete timing XML
        child_nodes = "\n".join(fragments)
        timing_id = self._next_id()

        if tracer is not None:
            tracer.record_stage_event(
                stage="animation",
                action="fragment_bundle_emitted",
                metadata={
                    "animation_count": len(fragments),
                    "timeline_frames": len(timeline),
                    "fallback_mode": options.get("fallback_mode", "native"),
                },
            )

        return (
            "    <p:timing>\n"
            "        <p:tnLst>\n"
            f'            <p:par>\n'
            f'                <p:cTn id="{timing_id}" dur="indefinite" restart="always">\n'
            "                    <p:childTnLst>\n"
            f"{child_nodes}\n"
            "                    </p:childTnLst>\n"
            "                </p:cTn>\n"
            "            </p:par>\n"
            "        </p:tnLst>\n"
            "    </p:timing>"
        )

    def _build_animation(
        self,
        animation: AnimationDefinition,
        options: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        """Build XML for a single animation.

        Args:
            animation: Animation definition to convert
            options: Build options (e.g., max_spline_error)

        Returns:
            Tuple of (xml_fragment, metadata)
            - xml_fragment: PowerPoint XML string (empty if skipped)
            - metadata: Optional dict with skip reason, error estimates, etc.
        """
        # Initialize policy if not already done (for direct calls)
        if self._policy is None:
            self._policy = AnimationPolicy(options)

        # Check if animation should be skipped
        max_error = self._policy.estimate_spline_error(animation)
        should_skip, skip_reason = self._policy.should_skip(animation, max_error)

        if should_skip:
            metadata: dict[str, Any] = {"reason": skip_reason}
            if max_error > 0:
                metadata["max_spline_error"] = round(max_error, 6)
            return "", metadata

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

            # Include spline error metadata if applicable
            metadata = None
            if max_error > 0:
                metadata = {"max_spline_error": round(max_error, 6)}

            return xml, metadata

        except Exception as e:
            # If handler fails, return empty with error reason
            return "", {"reason": f"handler_error: {str(e)}"}

    def _find_handler(self, animation: AnimationDefinition) -> AnimationHandler | None:
        """Find the first handler that can process this animation.

        Handlers are checked in priority order (specific to general).

        Args:
            animation: Animation definition to match

        Returns:
            First matching handler, or None if no handler matches
        """
        for handler in self._handlers:
            if handler.can_handle(animation):
                return handler
        return None

    def _next_id(self) -> int:
        """Generate next unique ID for timing elements.

        Returns:
            Unique integer ID
        """
        current_id = self._id_counter
        self._id_counter += 1
        return current_id

    def _allocate_ids(self) -> tuple[int, int]:
        """Allocate pair of IDs (par_id, behavior_id) for an animation.

        Returns:
            Tuple of (par_id, behavior_id)
        """
        par_id = self._next_id()
        behavior_id = self._next_id()
        return par_id, behavior_id
