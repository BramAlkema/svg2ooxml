from __future__ import annotations

from svg2ooxml.core.export.variant_trace import _merge_trace_reports


def test_merge_trace_reports_filters_malformed_totals_and_events() -> None:
    aggregate = _merge_trace_reports(
        [
            {
                "geometry_totals": {"emf": 1, "bad": "ignored", 2: 3},
                "paint_totals": {"native": 2},
                "stage_totals": ["not", "a", "mapping"],
                "resvg_metrics": {"attempts": 1},
                "geometry_events": [{"tag": "path", "decision": "emf"}, "ignored"],
                "paint_events": "ignored",
                "stage_events": [
                    {"stage": "filter", "action": "resvg_attempt"},
                    ["ignored"],
                ],
            },
            None,
            {
                "geometry_totals": {"emf": 2},
                "stage_totals": {"filter:resvg_attempt": 1},
                "stage_events": [{"stage": "filter", "action": "resvg_success"}],
            },
        ]
    )

    assert aggregate["geometry_totals"] == {"emf": 3}
    assert aggregate["paint_totals"] == {"native": 2}
    assert aggregate["stage_totals"] == {"filter:resvg_attempt": 1}
    assert aggregate["resvg_metrics"] == {"attempts": 1}
    assert aggregate["geometry_events"] == [{"tag": "path", "decision": "emf"}]
    assert aggregate["paint_events"] == []
    assert aggregate["stage_events"] == [
        {"stage": "filter", "action": "resvg_attempt"},
        {"stage": "filter", "action": "resvg_success"},
    ]
