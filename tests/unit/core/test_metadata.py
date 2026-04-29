from __future__ import annotations

from pathlib import Path

from svg2ooxml.core.metadata import (
    merge_policy_overrides,
    read_page_render_metadata,
    set_page_variant_type,
    trace_stage_events,
    trace_totals,
)


def test_read_page_render_metadata_normalizes_known_fields() -> None:
    metadata = {
        "source_path": Path("fixtures/icon.svg"),
        "variant": {"type": "emf"},
        "policy_overrides": {
            "filter": {"strategy": "emf", 1: "ignored"},
            "bad": "ignored",
        },
    }

    typed = read_page_render_metadata(metadata, default_variant_type="base")

    assert typed.source_path == "fixtures/icon.svg"
    assert typed.variant_type == "emf"
    assert typed.policy_overrides == {"filter": {"strategy": "emf"}}


def test_merge_policy_overrides_preserves_existing_typed_buckets() -> None:
    metadata = {
        "policy_overrides": {
            "filter": {"enable_effect_dag": True},
            "bad": "ignored",
        }
    }

    merged = merge_policy_overrides(
        metadata,
        {
            "filter": {"strategy": "native"},
            "geometry": {"force_emf": True},
        },
    )

    assert merged == {
        "filter": {"enable_effect_dag": True, "strategy": "native"},
        "geometry": {"force_emf": True},
    }
    assert metadata["policy_overrides"] == merged


def test_set_page_variant_type_replaces_bad_variant_metadata() -> None:
    metadata = {"variant": "bad"}

    variant = set_page_variant_type(metadata, "bitmap")

    assert variant == {"type": "bitmap"}
    assert metadata["variant"] == {"type": "bitmap"}


def test_trace_helpers_filter_to_typed_events_and_totals() -> None:
    report = {
        "geometry_totals": {"emf": 1, "bad": "ignored", 2: 3},
        "stage_events": [
            {"stage": "filter", "action": "effect", "metadata": {"fallback": "bitmap"}},
            {"stage": 10, "metadata": {"fallback": "ignored"}},
            "bad",
        ],
    }

    assert trace_totals(report, "geometry_totals") == {"emf": 1}
    events = trace_stage_events(report)
    assert len(events) == 1
    assert events[0].stage == "filter"
    assert events[0].action == "effect"
    assert events[0].metadata == {"fallback": "bitmap"}
