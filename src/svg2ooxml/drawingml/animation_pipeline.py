"""Animation pipeline that remaps and emits DrawingML timing fragments."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, TYPE_CHECKING

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
        self._tracer: "ConversionTracer | None" = None

    def reset(self, payload: dict[str, Any] | None, *, tracer: "ConversionTracer | None" = None) -> None:
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

    def build(self) -> str:
        if not self._payload:
            return ""

        definitions = self._payload.get("definitions") or []
        timeline = self._payload.get("timeline") or []
        if not definitions:
            return ""

        remapped: list[AnimationDefinition] = []
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
            remapped.append(replace(definition, element_id=shape_id))
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

        animation_xml = self._writer.build(remapped, timeline, tracer=self._tracer, options=self._policy)
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

    def _trace(self, action: str, *, metadata: dict[str, object] | None = None) -> None:
        if self._trace_writer is None:
            return
        self._trace_writer(action, stage="animation", metadata=metadata)


__all__ = ["AnimationPipeline"]
