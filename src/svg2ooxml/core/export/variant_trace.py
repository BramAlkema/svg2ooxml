"""Trace report aggregation for multi-page and variant export."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any


def _merge_trace_reports(reports: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple trace report dictionaries into a single aggregate report."""

    geometry_totals: Counter[str] = Counter()
    paint_totals: Counter[str] = Counter()
    stage_totals: Counter[str] = Counter()
    resvg_metrics: Counter[str] = Counter()
    geometry_events: list[Any] = []
    paint_events: list[Any] = []
    stage_events: list[Any] = []

    for report in reports:
        if not report:
            continue
        geometry_totals.update(report.get("geometry_totals", {}))
        paint_totals.update(report.get("paint_totals", {}))
        stage_totals.update(report.get("stage_totals", {}))
        resvg_metrics.update(report.get("resvg_metrics", {}))
        geometry_events.extend(report.get("geometry_events", []))
        paint_events.extend(report.get("paint_events", []))
        stage_events.extend(report.get("stage_events", []))

    return {
        "geometry_totals": dict(geometry_totals),
        "paint_totals": dict(paint_totals),
        "stage_totals": dict(stage_totals),
        "resvg_metrics": dict(resvg_metrics),
        "geometry_events": geometry_events,
        "paint_events": paint_events,
        "stage_events": stage_events,
    }


__all__ = ["_merge_trace_reports"]
