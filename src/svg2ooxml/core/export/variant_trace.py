"""Trace report aggregation for multi-page and variant export."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


def _merge_trace_reports(reports: Iterable[Mapping[str, Any] | None]) -> dict[str, Any]:
    """Merge multiple trace report dictionaries into a single aggregate report."""

    geometry_totals: Counter[str] = Counter()
    paint_totals: Counter[str] = Counter()
    stage_totals: Counter[str] = Counter()
    resvg_metrics: Counter[str] = Counter()
    geometry_events: list[dict[str, Any]] = []
    paint_events: list[dict[str, Any]] = []
    stage_events: list[dict[str, Any]] = []

    for report in reports:
        if not isinstance(report, Mapping):
            continue
        _update_counter(geometry_totals, report.get("geometry_totals"))
        _update_counter(paint_totals, report.get("paint_totals"))
        _update_counter(stage_totals, report.get("stage_totals"))
        _update_counter(resvg_metrics, report.get("resvg_metrics"))
        geometry_events.extend(_event_dicts(report.get("geometry_events")))
        paint_events.extend(_event_dicts(report.get("paint_events")))
        stage_events.extend(_event_dicts(report.get("stage_events")))

    return {
        "geometry_totals": dict(geometry_totals),
        "paint_totals": dict(paint_totals),
        "stage_totals": dict(stage_totals),
        "resvg_metrics": dict(resvg_metrics),
        "geometry_events": geometry_events,
        "paint_events": paint_events,
        "stage_events": stage_events,
    }


def _update_counter(counter: Counter[str], values: object) -> None:
    if not isinstance(values, Mapping):
        return
    for key, count in values.items():
        if isinstance(key, str) and isinstance(count, int):
            counter[key] += count


def _event_dicts(values: object) -> list[dict[str, Any]]:
    if not isinstance(values, Sequence) or isinstance(values, str | bytes):
        return []
    events: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, Mapping):
            events.append(
                {str(key): item for key, item in value.items() if isinstance(key, str)}
            )
    return events


__all__ = ["_merge_trace_reports"]
