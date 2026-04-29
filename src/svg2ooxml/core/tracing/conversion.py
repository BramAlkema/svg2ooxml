"""Lightweight tracing utilities for IR conversion decisions."""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypedDict


def _stringify(value: Any) -> str:
    return str(value)


def _sanitize(payload: Any) -> Any:
    if payload is None:
        return None
    try:
        return json.loads(json.dumps(payload, default=_stringify))
    except Exception:
        if isinstance(payload, dict):
            return {str(key): _stringify(value) for key, value in payload.items()}
        if isinstance(payload, (list, tuple)):
            return [_stringify(item) for item in payload]
        return _stringify(payload)


def _sanitize_metadata(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return JSON-safe trace metadata as a plain dictionary."""

    sanitized = _sanitize(dict(payload or {}))
    return sanitized if isinstance(sanitized, dict) else {}


def _derive_resvg_metrics(stage_totals: Iterable[tuple[str, int]]) -> dict[str, int]:
    metrics: dict[str, int] = {
        "attempts": 0,
        "plan_characterised": 0,
        "promotions": 0,
        "policy_blocks": 0,
        "lighting_candidates": 0,
        "lighting_promotions": 0,
        "successes": 0,
        "failures": 0,
    }
    failure_actions = {
        "resvg_build_failed",
        "resvg_plan_unsupported",
        "resvg_viewport_failed",
        "resvg_unsupported_primitive",
        "resvg_execution_failed",
    }
    for key, count in stage_totals:
        if not key.startswith("filter:"):
            continue
        _, action = key.split(":", 1)
        if action == "resvg_attempt":
            metrics["attempts"] += count
        elif action == "resvg_plan_characterised":
            metrics["plan_characterised"] += count
        elif action == "resvg_promoted_emf":
            metrics["promotions"] += count
        elif action == "resvg_promotion_policy_blocked":
            metrics["policy_blocks"] += count
        elif action == "resvg_lighting_candidate":
            metrics["lighting_candidates"] += count
        elif action == "resvg_lighting_promoted":
            metrics["lighting_promotions"] += count
        elif action == "resvg_success":
            metrics["successes"] += count
        elif action in failure_actions:
            metrics["failures"] += count
    return {key: value for key, value in metrics.items() if value}


# Geometry decision keys (produced by IR converters, consumed by corpus metrics)
GEOM_NATIVE = "native"
GEOM_EMF = "emf"
GEOM_BITMAP = "bitmap"
GEOM_RASTER = "raster"
GEOM_RESVG = "resvg"
GEOM_WORDART = "wordart"
GEOM_POLICY_EMF = "policy_emf"
GEOM_POLICY_RASTER = "policy_raster"

# Paint decision keys
PAINT_NATIVE = "native"
PAINT_EMF = "emf"
PAINT_BITMAP = "bitmap"


@dataclass(slots=True)
class GeometryTrace:
    tag: str
    decision: str
    metadata: dict[str, Any] = field(default_factory=dict)
    element_id: str | None = None

    def to_dict(self) -> GeometryTracePayload:
        return {
            "tag": self.tag,
            "decision": self.decision,
            "element_id": self.element_id,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class PaintTrace:
    paint_type: str
    decision: str
    metadata: dict[str, Any] = field(default_factory=dict)
    paint_id: str | None = None

    def to_dict(self) -> PaintTracePayload:
        return {
            "paint_type": self.paint_type,
            "decision": self.decision,
            "paint_id": self.paint_id,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class StageTrace:
    stage: str
    action: str
    metadata: dict[str, Any] = field(default_factory=dict)
    subject: str | None = None

    def to_dict(self) -> StageTracePayload:
        return {
            "stage": self.stage,
            "action": self.action,
            "subject": self.subject,
            "metadata": self.metadata,
        }


class GeometryTracePayload(TypedDict):
    tag: str
    decision: str
    element_id: str | None
    metadata: dict[str, Any]


class PaintTracePayload(TypedDict):
    paint_type: str
    decision: str
    paint_id: str | None
    metadata: dict[str, Any]


class StageTracePayload(TypedDict):
    stage: str
    action: str
    subject: str | None
    metadata: dict[str, Any]


class TraceReportPayload(TypedDict):
    geometry_totals: dict[str, int]
    paint_totals: dict[str, int]
    geometry_events: list[GeometryTracePayload]
    paint_events: list[PaintTracePayload]
    stage_totals: dict[str, int]
    stage_events: list[StageTracePayload]
    resvg_metrics: dict[str, int]


@dataclass(slots=True)
class TraceReport:
    geometry_totals: dict[str, int]
    paint_totals: dict[str, int]
    geometry_events: list[GeometryTrace]
    paint_events: list[PaintTrace]
    stage_totals: dict[str, int]
    stage_events: list[StageTrace]

    def to_dict(self) -> TraceReportPayload:
        resvg_metrics = _derive_resvg_metrics(self.stage_totals.items())
        return {
            "geometry_totals": dict(self.geometry_totals),
            "paint_totals": dict(self.paint_totals),
            "geometry_events": [event.to_dict() for event in self.geometry_events],
            "paint_events": [event.to_dict() for event in self.paint_events],
            "stage_totals": dict(self.stage_totals),
            "stage_events": [event.to_dict() for event in self.stage_events],
            "resvg_metrics": resvg_metrics,
        }


class ConversionTracer:
    """Collect geometry and paint fallback decisions with optional debug logging."""

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        collect_events: bool = True,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._collect_events = collect_events
        self._geometry_totals: Counter[str] = Counter()
        self._paint_totals: Counter[str] = Counter()
        self._geometry_events: list[GeometryTrace] = []
        self._paint_events: list[PaintTrace] = []
        self._stage_totals: Counter[str] = Counter()
        self._stage_events: list[StageTrace] = []

    def reset(self) -> None:
        self._geometry_totals.clear()
        self._paint_totals.clear()
        self._geometry_events.clear()
        self._paint_events.clear()
        self._stage_totals.clear()
        self._stage_events.clear()

    def record_geometry_decision(
        self,
        *,
        tag: str,
        decision: str,
        metadata: Mapping[str, Any] | None = None,
        element_id: str | None = None,
    ) -> None:
        sanitized = _sanitize_metadata(metadata)
        self._geometry_totals[decision] += 1
        if self._collect_events:
            self._geometry_events.append(
                GeometryTrace(
                    tag=tag,
                    decision=decision,
                    metadata=sanitized,
                    element_id=element_id,
                )
            )
        self._logger.debug(
            "geometry decision: tag=%s id=%s decision=%s metadata=%s",
            tag,
            element_id,
            decision,
            sanitized,
        )

    def record_paint_decision(
        self,
        *,
        paint_type: str,
        decision: str,
        metadata: Mapping[str, Any] | None = None,
        paint_id: str | None = None,
    ) -> None:
        sanitized = _sanitize_metadata(metadata)
        self._paint_totals[decision] += 1
        if self._collect_events:
            self._paint_events.append(
                PaintTrace(
                    paint_type=paint_type,
                    decision=decision,
                    metadata=sanitized,
                    paint_id=paint_id,
                )
            )
        self._logger.debug(
            "paint decision: type=%s id=%s decision=%s metadata=%s",
            paint_type,
            paint_id,
            decision,
            sanitized,
        )

    def record_stage_event(
        self,
        *,
        stage: str,
        action: str,
        metadata: Mapping[str, Any] | None = None,
        subject: str | None = None,
    ) -> None:
        sanitized = _sanitize_metadata(metadata)
        key = f"{stage}:{action}"
        self._stage_totals[key] += 1
        if self._collect_events:
            self._stage_events.append(
                StageTrace(
                    stage=stage,
                    action=action,
                    subject=subject,
                    metadata=sanitized,
                )
            )
        self._logger.debug(
            "stage event: stage=%s action=%s subject=%s metadata=%s",
            stage,
            action,
            subject,
            sanitized,
        )

    def report(self) -> TraceReport:
        return TraceReport(
            geometry_totals=dict(self._geometry_totals),
            paint_totals=dict(self._paint_totals),
            geometry_events=list(self._geometry_events),
            paint_events=list(self._paint_events),
            stage_totals=dict(self._stage_totals),
            stage_events=list(self._stage_events),
        )


__all__ = [
    "ConversionTracer",
    "GeometryTrace",
    "GeometryTracePayload",
    "PaintTrace",
    "PaintTracePayload",
    "StageTrace",
    "StageTracePayload",
    "TraceReport",
    "TraceReportPayload",
]
