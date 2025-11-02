"""Lightweight tracing utilities for IR conversion decisions."""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List


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


@dataclass(slots=True)
class GeometryTrace:
    tag: str
    decision: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    element_id: str | None = None


@dataclass(slots=True)
class PaintTrace:
    paint_type: str
    decision: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    paint_id: str | None = None


@dataclass(slots=True)
class TraceReport:
    geometry_totals: Dict[str, int]
    paint_totals: Dict[str, int]
    geometry_events: List[GeometryTrace]
    paint_events: List[PaintTrace]
    stage_totals: Dict[str, int]
    stage_events: List["StageTrace"]

    def to_dict(self) -> dict[str, Any]:
        resvg_metrics = _derive_resvg_metrics(self.stage_totals.items())
        return {
            "geometry_totals": dict(self.geometry_totals),
            "paint_totals": dict(self.paint_totals),
            "geometry_events": [
                {
                    "tag": event.tag,
                    "decision": event.decision,
                    "element_id": event.element_id,
                    "metadata": event.metadata,
                }
                for event in self.geometry_events
            ],
            "paint_events": [
                {
                    "paint_type": event.paint_type,
                    "decision": event.decision,
                    "paint_id": event.paint_id,
                    "metadata": event.metadata,
                }
                for event in self.paint_events
            ],
            "stage_totals": dict(self.stage_totals),
            "stage_events": [
                {
                    "stage": event.stage,
                    "action": event.action,
                    "subject": event.subject,
                    "metadata": event.metadata,
                }
                for event in self.stage_events
            ],
            "resvg_metrics": resvg_metrics,
        }


@dataclass(slots=True)
class StageTrace:
    stage: str
    action: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    subject: str | None = None


class ConversionTracer:
    """Collect geometry and paint fallback decisions with optional debug logging."""

    def __init__(self, *, logger: logging.Logger | None = None, collect_events: bool = True) -> None:
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
        metadata: dict[str, Any] | None = None,
        element_id: str | None = None,
    ) -> None:
        sanitized = _sanitize(metadata or {})
        self._geometry_totals[decision] += 1
        if self._collect_events:
            self._geometry_events.append(
                GeometryTrace(tag=tag, decision=decision, metadata=sanitized, element_id=element_id)
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
        metadata: dict[str, Any] | None = None,
        paint_id: str | None = None,
    ) -> None:
        sanitized = _sanitize(metadata or {})
        self._paint_totals[decision] += 1
        if self._collect_events:
            self._paint_events.append(
                PaintTrace(paint_type=paint_type, decision=decision, metadata=sanitized, paint_id=paint_id)
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
        metadata: dict[str, Any] | None = None,
        subject: str | None = None,
    ) -> None:
        sanitized = _sanitize(metadata or {})
        key = f"{stage}:{action}"
        self._stage_totals[key] += 1
        if self._collect_events:
            self._stage_events.append(
                StageTrace(stage=stage, action=action, subject=subject, metadata=sanitized)
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


__all__ = ["ConversionTracer", "TraceReport", "GeometryTrace", "PaintTrace", "StageTrace"]
