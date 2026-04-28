"""Descriptor payload extraction for filter planner fallbacks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from svg2ooxml.filters import planner_common as _common
from svg2ooxml.filters.planner_numeric import PlannerNumericMixin


class DescriptorPayloadMixin(PlannerNumericMixin):
    """Build serialisable descriptor payloads and sanitized bounds."""

    def descriptor_payload(
        self,
        context: Any,
        descriptor: Any | None,
    ) -> tuple[dict[str, Any] | None, dict[str, float | Any] | None]:
        payload: dict[str, Any] | None = None
        bounds: dict[str, float | Any] | None = None

        options = (
            context.options
            if isinstance(getattr(context, "options", None), dict)
            else {}
        )
        candidate = options.get("resvg_descriptor")
        if isinstance(candidate, dict):
            payload = dict(candidate)
        bbox_candidate = options.get("ir_bbox")
        if isinstance(bbox_candidate, dict):
            bounds = _common.finite_bounds(bbox_candidate)

        if payload is None and descriptor is not None:
            payload = self.serialize_descriptor(descriptor)

        if bounds is None and payload is not None:
            bounds = _common.numeric_region(payload.get("filter_region"))

        return payload, bounds

    def infer_descriptor_strategy(
        self,
        descriptor: Mapping[str, Any],
        *,
        strategy_hint: str,
    ) -> str | None:
        return _common.infer_descriptor_strategy(
            descriptor,
            strategy_hint=strategy_hint,
        )

    @staticmethod
    def serialize_descriptor(descriptor: Any) -> dict[str, Any]:
        return _common.serialize_descriptor(descriptor)


__all__ = ["DescriptorPayloadMixin"]
