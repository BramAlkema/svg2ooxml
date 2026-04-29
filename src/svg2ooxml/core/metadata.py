"""Typed metadata adapters for exporter and orchestration boundaries."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from svg2ooxml.policy.fidelity import PolicyOverrideBucket, PolicyOverrides


class VariantMetadata(TypedDict, total=False):
    """Metadata stored on page variants."""

    type: str


class PageMetadata(TypedDict, total=False):
    """Known page metadata keys accepted by multi-page exporters."""

    variant: VariantMetadata
    policy_overrides: PolicyOverrides
    source: str
    source_path: str | Path
    page_title: str
    page_metadata: dict[str, Any]
    trace_report: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PageRenderMetadata:
    """Normalized metadata needed before rendering one SVG page."""

    policy_overrides: PolicyOverrides | None
    source_path: str | None
    variant_type: str


@dataclass(frozen=True, slots=True)
class TraceStageEvent:
    """Normalized trace-stage event used by fallback variant derivation."""

    stage: str
    action: str
    metadata: Mapping[str, Any]


def coerce_policy_overrides(value: Any) -> PolicyOverrides | None:
    """Return policy overrides when *value* is a mapping of mapping buckets."""

    if not isinstance(value, Mapping):
        return None

    overrides: PolicyOverrides = {}
    for category, bucket in value.items():
        if not isinstance(category, str) or not isinstance(bucket, Mapping):
            continue
        typed_bucket: PolicyOverrideBucket = {
            str(key): item for key, item in bucket.items() if isinstance(key, str)
        }
        if typed_bucket:
            overrides[category] = typed_bucket
    return overrides or None


def merge_policy_overrides(
    metadata: MutableMapping[str, Any],
    overrides: Mapping[str, Mapping[str, object]],
) -> PolicyOverrides:
    """Merge typed policy override buckets into mutable page metadata."""

    existing = coerce_policy_overrides(metadata.get("policy_overrides")) or {}
    for category, bucket in overrides.items():
        if not isinstance(category, str):
            continue
        merged: PolicyOverrideBucket = dict(existing.get(category, {}))
        merged.update(
            {str(key): value for key, value in bucket.items() if isinstance(key, str)}
        )
        existing[category] = merged
    metadata["policy_overrides"] = existing
    return existing


def set_page_variant_type(
    metadata: MutableMapping[str, Any],
    variant_type: object,
) -> VariantMetadata:
    """Set the page variant type in mutable metadata and return the bucket."""

    variant_value = metadata.get("variant")
    variant: VariantMetadata
    if isinstance(variant_value, MutableMapping):
        variant = {"type": str(variant_value.get("type", variant_type))}
        variant.update(
            {
                str(key): str(value)
                for key, value in variant_value.items()
                if isinstance(key, str) and key != "type"
            }
        )
    else:
        variant = {}
    variant["type"] = str(variant_type)
    metadata["variant"] = variant
    return variant


def ensure_scene_variant_type(
    metadata: MutableMapping[str, Any],
    variant_type: object,
) -> VariantMetadata:
    """Set the scene variant type when no existing typed variant is present."""

    variant_value = metadata.get("variant")
    if isinstance(variant_value, MutableMapping):
        variant: VariantMetadata = {
            str(key): str(value)
            for key, value in variant_value.items()
            if isinstance(key, str)
        }
    else:
        variant = {}
    variant.setdefault("type", str(variant_type))
    metadata["variant"] = variant
    return variant


def read_page_render_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    default_variant_type: str = "variant",
) -> PageRenderMetadata:
    """Normalize page metadata before render dispatch."""

    if not isinstance(metadata, Mapping):
        return PageRenderMetadata(
            policy_overrides=None,
            source_path=None,
            variant_type=default_variant_type,
        )

    source_path = _coerce_source_path(metadata.get("source_path"))
    variant_type = default_variant_type
    variant_value = metadata.get("variant")
    if isinstance(variant_value, Mapping):
        raw_variant_type = variant_value.get("type")
        if raw_variant_type is not None:
            variant_type = str(raw_variant_type)

    return PageRenderMetadata(
        policy_overrides=coerce_policy_overrides(metadata.get("policy_overrides")),
        source_path=source_path,
        variant_type=variant_type,
    )


def trace_totals(
    trace_report: Mapping[str, Any] | None,
    key: str,
) -> dict[str, int]:
    """Return typed count totals from a trace report bucket."""

    if not isinstance(trace_report, Mapping):
        return {}

    raw_totals = trace_report.get(key)
    if not isinstance(raw_totals, Mapping):
        return {}

    totals: dict[str, int] = {}
    for name, count in raw_totals.items():
        if isinstance(name, str) and isinstance(count, int):
            totals[name] = count
    return totals


def trace_stage_events(
    trace_report: Mapping[str, Any] | None,
) -> list[TraceStageEvent]:
    """Return typed trace-stage events from a raw trace report."""

    if not isinstance(trace_report, Mapping):
        return []

    raw_events = trace_report.get("stage_events")
    if not isinstance(raw_events, Sequence) or isinstance(raw_events, str | bytes):
        return []

    events: list[TraceStageEvent] = []
    for raw_event in raw_events:
        if not isinstance(raw_event, Mapping):
            continue
        stage = raw_event.get("stage")
        if not isinstance(stage, str):
            continue
        action = raw_event.get("action")
        metadata = raw_event.get("metadata")
        events.append(
            TraceStageEvent(
                stage=stage,
                action=action if isinstance(action, str) else "",
                metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
            )
        )
    return events


def _coerce_source_path(value: Any) -> str | None:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return value
    return None


__all__ = [
    "PageMetadata",
    "PageRenderMetadata",
    "TraceStageEvent",
    "VariantMetadata",
    "coerce_policy_overrides",
    "ensure_scene_variant_type",
    "merge_policy_overrides",
    "read_page_render_metadata",
    "set_page_variant_type",
    "trace_stage_events",
    "trace_totals",
]
