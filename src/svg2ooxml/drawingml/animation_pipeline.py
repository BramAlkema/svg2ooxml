"""Animation pipeline that remaps and emits DrawingML timing fragments."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from svg2ooxml.ir.animation import AnimationDefinition

from .animation import DrawingMLAnimationWriter

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.tracing import ConversionTracer


class AnimationPipeline:
    """Track animation mappings and build timing XML."""

    def __init__(
        self,
        *,
        writer: DrawingMLAnimationWriter | None = None,
        trace_writer: Callable[..., None] | None = None,
    ) -> None:
        self._writer = writer or DrawingMLAnimationWriter()
        self._trace_writer = trace_writer
        self._payload: dict[str, Any] | None = None
        self._shape_map: dict[str, str] = {}
        self._policy: dict[str, object] = {}
        self._tracer: ConversionTracer | None = None

    def reset(self, payload: dict[str, Any] | None, *, tracer: ConversionTracer | None = None) -> None:
        self._payload = payload
        self._shape_map = {}
        self._policy = {}
        self._tracer = tracer
        if isinstance(payload, dict):
            payload_policy = payload.get("policy")
            if isinstance(payload_policy, dict):
                self._policy = dict(payload_policy)

    def register_mapping(self, metadata: dict[str, object] | None, shape_id: int) -> None:
        if not isinstance(metadata, dict):
            return
        element_ids = metadata.get("element_ids")
        if not isinstance(element_ids, list):
            return
        for element_id in element_ids:
            if isinstance(element_id, str):
                self._shape_map.setdefault(element_id, str(shape_id))

    def register_element_ids(self, element_ids: list[object], shape_id: int) -> None:
        for element_id in element_ids:
            if isinstance(element_id, str):
                self._shape_map.setdefault(element_id, str(shape_id))

    def build(self, *, max_shape_id: int = 0) -> str:
        if not self._payload:
            return ""

        definitions = self._payload.get("definitions") or []
        timeline = self._payload.get("timeline") or []
        if not definitions:
            return ""

        remapped: list[AnimationDefinition] = []
        animated_shape_ids: set[str] = set()
        for definition in definitions:
            element_id = getattr(definition, "element_id", None)
            if not isinstance(element_id, str):
                self._trace(
                    "invalid_animation_definition",
                    metadata={"reason": "missing_element_id"},
                )
                continue
            shape_id = self._shape_map.get(element_id)
            if not shape_id:
                self._trace(
                    "unmapped_animation",
                    metadata={
                        "element_id": element_id,
                        "animation_type": definition.animation_type.value,
                    },
                )
                continue
            remapped_definition = replace(definition, element_id=shape_id)
            remapped_definition = self._remap_begin_trigger_targets(remapped_definition, shape_id=shape_id)
            remapped.append(remapped_definition)
            animated_shape_ids.add(shape_id)
            self._trace(
                "mapped_animation",
                metadata={
                    "element_id": element_id,
                    "shape_id": shape_id,
                    "animation_type": definition.animation_type.value,
                },
            )

        if not remapped:
            if definitions:
                self._trace(
                    "timing_skipped",
                    metadata={"reason": "no_mapped_definitions", "animation_count": len(definitions)},
                )
            return ""

        # Build complete timing XML, including bldLst
        # Start timing IDs after the last shape ID to avoid collisions
        start_id = max(max_shape_id + 1, 1)
        animation_xml = self._writer.build(
            remapped,
            timeline,
            tracer=self._tracer,
            options=self._policy,
            animated_shape_ids=sorted(list(animated_shape_ids), key=int),
            start_id=start_id,
        )
        if animation_xml:
            self._trace(
                "timing_emitted",
                metadata={
                    "animation_count": len(remapped),
                    "timeline_frames": len(timeline),
                    "fallback_mode": self._policy.get("fallback_mode", "native"),
                },
            )
        else:
            self._trace(
                "timing_skipped",
                metadata={
                    "reason": "writer_returned_empty",
                    "animation_count": len(remapped),
                    "fallback_mode": self._policy.get("fallback_mode", "native"),
                },
            )
        return animation_xml

    def _remap_begin_trigger_targets(
        self,
        definition: AnimationDefinition,
        *,
        shape_id: str,
    ) -> AnimationDefinition:
        """Remap begin trigger target element IDs to slide shape IDs."""
        timing = getattr(definition, "timing", None)
        begin_triggers = getattr(timing, "begin_triggers", None)
        if not begin_triggers:
            return definition

        remapped_triggers = []
        changed = False
        for trigger in begin_triggers:
            target_id = getattr(trigger, "target_element_id", None)
            if not target_id:
                remapped_triggers.append(trigger)
                continue

            mapped = self._shape_map.get(target_id)
            if mapped is None:
                trigger_type = getattr(getattr(trigger, "trigger_type", None), "value", None)
                # Fallback for unresolved explicit click target: click defaults to current shape.
                if trigger_type == "click":
                    mapped = shape_id
                else:
                    mapped = None
                    self._trace(
                        "unmapped_begin_trigger_target",
                        metadata={
                            "element_id": getattr(definition, "element_id", None),
                            "target_element_id": target_id,
                            "trigger_type": trigger_type,
                        },
                    )

            if mapped != target_id:
                changed = True
                remapped_triggers.append(replace(trigger, target_element_id=mapped))
            else:
                remapped_triggers.append(trigger)

        if not changed:
            return definition

        remapped_timing = replace(timing, begin_triggers=remapped_triggers)
        return replace(definition, timing=remapped_timing)

    def _trace(self, action: str, *, metadata: dict[str, object] | None = None) -> None:
        if self._trace_writer is None:
            return
        self._trace_writer(action, stage="animation", metadata=metadata)


__all__ = ["AnimationPipeline"]
