from __future__ import annotations

import json
from pathlib import Path

from tools.visual.corpus_audit import (
    AuditResult,
    _apply_trace_metrics,
    _artifact_subdir,
    _classify_corpus,
    _default_output_dir,
    _svg_has_animation,
    audit_svgs,
    build_run_metadata,
    build_summary,
    discover_svg_paths,
    render_markdown_summary,
    resolve_audit_inputs,
    score_audit_result,
    write_audit_report,
)


def test_discover_svg_paths_skips_generated_dirs(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "keep.svg").write_text("<svg/>", encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    (nested / "also_keep.svg").write_text("<svg/>", encoding="utf-8")
    skipped_output = root / "output"
    skipped_output.mkdir()
    (skipped_output / "skip.svg").write_text("<svg/>", encoding="utf-8")
    skipped_baselines = root / "baselines"
    skipped_baselines.mkdir()
    (skipped_baselines / "skip.svg").write_text("<svg/>", encoding="utf-8")

    discovered = discover_svg_paths([root])

    assert discovered == [
        root / "keep.svg",
        nested / "also_keep.svg",
    ]


def test_resolve_audit_inputs_adds_named_corpus_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "resvg-test-suite" / "tests"
    checkout.mkdir(parents=True)
    (checkout / "sample.svg").write_text("<svg/>", encoding="utf-8")

    resolved = resolve_audit_inputs(
        named_corpora=["resvg-test-suite"],
        corpus_root=tmp_path,
    )

    assert resolved == [checkout]


def test_artifact_subdir_keeps_external_paths_unique(tmp_path: Path) -> None:
    external_svg = tmp_path / "resvg-test-suite" / "tests" / "shapes" / "sample.svg"
    external_svg.parent.mkdir(parents=True)
    external_svg.write_text("<svg/>", encoding="utf-8")

    artifact_subdir = _artifact_subdir(external_svg)

    assert artifact_subdir.as_posix().endswith(
        "_external/" + "/".join(external_svg.resolve().parts[1:-1]) + "/sample"
    )


def test_classify_corpus_names_known_inputs() -> None:
    assert _classify_corpus(Path("tests/corpus/w3c/sample.svg")) == "w3c"
    assert (
        _classify_corpus(Path("tests/visual/fixtures/resvg/sample.svg"))
        == "visual-fixtures"
    )
    assert (
        _classify_corpus(Path("/tmp/resvg-test-suite/tests/sample.svg"))
        == "resvg-test-suite"
    )
    assert _classify_corpus(Path("external/sample.svg")) == "external"


def test_default_output_dir_uses_powerpoint_reports_subtree() -> None:
    assert _default_output_dir("powerpoint") == Path("reports/visual/powerpoint/audit")
    assert _default_output_dir("soffice") == Path("reports/visual/audit")


def test_score_audit_result_prioritizes_build_failures() -> None:
    build_failure = AuditResult(
        svg_path="broken.svg",
        artifact_dir="out/broken",
        build_status="error",
    )
    visual_mismatch = AuditResult(
        svg_path="mismatch.svg",
        artifact_dir="out/mismatch",
        build_status="ok",
        render_status="ok",
        browser_status="ok",
        diff_status="mismatch",
        ssim_score=0.91,
        pixel_diff_percentage=6.5,
        rasterized_count=1,
        max_bbox_delta=2.0,
    )

    assert score_audit_result(build_failure) > score_audit_result(visual_mismatch)


def test_score_audit_result_includes_animation_mismatch_penalty() -> None:
    static_only = AuditResult(
        svg_path="static.svg",
        artifact_dir="out/static",
        build_status="ok",
        render_status="ok",
        browser_status="ok",
        diff_status="ok",
        score=0.0,
    )
    animated_mismatch = AuditResult(
        svg_path="animated.svg",
        artifact_dir="out/animated",
        build_status="ok",
        render_status="ok",
        browser_status="ok",
        diff_status="ok",
        animation_status="mismatch",
        animation_min_ssim=0.62,
        animation_max_pixel_diff_percentage=18.5,
    )

    assert score_audit_result(animated_mismatch) > score_audit_result(static_only)


def test_render_markdown_summary_lists_highest_score_first() -> None:
    low = AuditResult(
        svg_path="low.svg",
        artifact_dir="out/low",
        build_status="ok",
        render_status="ok",
        browser_status="ok",
        diff_status="ok",
        score=10.0,
    )
    high = AuditResult(
        svg_path="high.svg",
        artifact_dir="out/high",
        build_status="ok",
        render_status="error",
        browser_status="ok",
        diff_status="skipped",
        score=250.0,
        notes=["PPTX render failed."],
    )

    markdown = render_markdown_summary([high, low], top_n=1)
    summary = build_summary([high, low])

    assert "high.svg" in markdown
    assert "low.svg" not in markdown
    assert summary["render_errors"] == 1


def test_render_markdown_summary_includes_animation_columns() -> None:
    item = AuditResult(
        svg_path="animated.svg",
        artifact_dir="out/animated",
        build_status="ok",
        render_status="ok",
        browser_status="ok",
        diff_status="ok",
        animation_status="mismatch",
        animation_min_ssim=0.8123,
        animation_emitted_count=3,
        animation_skipped_count=1,
        animation_reason_counts={"unsupported_begin_target_missing": 1},
        score=42.0,
    )

    markdown = render_markdown_summary([item], top_n=1)
    summary = build_summary([item])

    assert "| Anim |" in markdown
    assert "| Reason | Count |" in markdown
    assert "unsupported_begin_target_missing" in markdown
    assert "3/1" in markdown
    assert "0.8123" in markdown
    assert summary["animation_mismatches"] == 1
    assert summary["animation_fragments_emitted"] == 3
    assert summary["animation_fragments_skipped"] == 1
    assert summary["animation_reason_totals"] == {"unsupported_begin_target_missing": 1}


def test_build_summary_aggregates_animation_reason_totals() -> None:
    first = AuditResult(
        svg_path="one.svg",
        artifact_dir="out/one",
        animation_reason_counts={
            "unsupported_begin_target_missing": 2,
            "timing_skipped": 1,
        },
        animation_emitted_count=4,
        animation_skipped_count=2,
    )
    second = AuditResult(
        svg_path="two.svg",
        artifact_dir="out/two",
        animation_reason_counts={
            "unsupported_begin_target_missing": 1,
            "begin_expression_invalid": 3,
        },
        animation_emitted_count=1,
        animation_skipped_count=1,
    )

    summary = build_summary([first, second])

    assert summary["animation_fragments_emitted"] == 5
    assert summary["animation_fragments_skipped"] == 3
    assert summary["animation_reason_totals"] == {
        "begin_expression_invalid": 3,
        "unsupported_begin_target_missing": 3,
        "timing_skipped": 1,
    }


def test_apply_trace_metrics_collects_converter_report_fields() -> None:
    item = AuditResult(svg_path="sample.svg", artifact_dir="out/sample")
    trace_report = {
        "geometry_totals": {"emf": 2, "bad": "ignored", 4: 1},
        "paint_totals": {"bitmap": 1},
        "stage_totals": {"filter:resvg_attempt": 2},
        "resvg_metrics": {"attempts": 2, "successes": 1},
        "geometry_events": [
            {
                "decision": "emf",
                "metadata": {
                    "fallback_assets": [
                        {"type": "emf"},
                        {"type": "bitmap"},
                        {"no_type": True},
                    ],
                    "fallback_reason": "complex_path",
                },
            }
        ],
        "paint_events": [
            {
                "decision": "bitmap",
                "metadata": {
                    "fallback_assets": [{"type": "bitmap"}],
                    "fallback": "bitmap",
                },
            }
        ],
        "stage_events": [
            {
                "stage": "animation",
                "action": "fragment_emitted",
                "metadata": {},
            },
            {
                "stage": "animation",
                "action": "fragment_skipped",
                "metadata": {"reason": "unsupported_begin_target_missing"},
            },
            {
                "stage": "filter",
                "action": "descriptor_fallback",
                "metadata": {},
            },
        ],
    }

    _apply_trace_metrics(item, trace_report)

    assert item.geometry_totals == {"emf": 2}
    assert item.paint_totals == {"bitmap": 1}
    assert item.stage_totals == {"filter:resvg_attempt": 2}
    assert item.resvg_metrics == {"attempts": 2, "successes": 1}
    assert item.fallback_asset_counts == {"bitmap": 2, "emf": 1, "unknown": 1}
    assert item.fallback_reason_counts == {
        "action:descriptor_fallback": 1,
        "complex_path": 1,
        "fallback:bitmap": 1,
    }
    assert item.animation_emitted_count == 1
    assert item.animation_skipped_count == 1
    assert item.animation_reason_counts == {"unsupported_begin_target_missing": 1}


def test_build_summary_aggregates_trace_and_report_coverage() -> None:
    first = AuditResult(
        svg_path="one.svg",
        artifact_dir="out/one",
        corpus_name="w3c",
        fidelity_tier="direct",
        geometry_totals={"emf": 2},
        paint_totals={"bitmap": 1},
        stage_totals={"filter:resvg_attempt": 1},
        resvg_metrics={"attempts": 1},
        fallback_asset_counts={"emf": 1},
        fallback_reason_counts={"complex_path": 1},
    )
    second = AuditResult(
        svg_path="two.svg",
        artifact_dir="out/two",
        corpus_name="w3c",
        fidelity_tier="bitmap",
        geometry_totals={"bitmap": 1},
        fallback_asset_counts={"bitmap": 2},
        fallback_reason_counts={"complex_path": 1, "fallback:bitmap": 1},
    )

    summary = build_summary([first, second])

    assert summary["by_corpus"] == {"w3c": 2}
    assert summary["by_fidelity_tier"] == {"bitmap": 1, "direct": 1}
    assert summary["geometry_totals"] == {"emf": 2, "bitmap": 1}
    assert summary["paint_totals"] == {"bitmap": 1}
    assert summary["stage_totals"] == {"filter:resvg_attempt": 1}
    assert summary["resvg_metrics"] == {"attempts": 1}
    assert summary["fallback_asset_totals"] == {"bitmap": 2, "emf": 1}
    assert summary["fallback_reason_totals"] == {
        "complex_path": 2,
        "fallback:bitmap": 1,
    }


def test_write_audit_report_includes_run_metadata_and_trace_sections(
    tmp_path: Path,
) -> None:
    result = AuditResult(
        svg_path="tests/corpus/w3c/sample.svg",
        artifact_dir="out/sample",
        corpus_name="w3c",
        fidelity_tier="emf",
        build_status="ok",
        render_status="ok",
        browser_status="ok",
        diff_status="mismatch",
        fallback_asset_counts={"emf": 1},
        fallback_reason_counts={"complex_path": 1},
        geometry_totals={"emf": 1},
        resvg_metrics={"attempts": 1},
        score=10.0,
    )
    metadata = build_run_metadata(
        command=["python", "-m", "tools.visual.corpus_audit"],
        inputs=[Path("tests/corpus/w3c")],
        output_dir=tmp_path,
        renderer="powerpoint",
        browser_threshold=0.9,
        skip_render=False,
        skip_browser=False,
        check_animation=False,
        animation_duration=4.0,
        animation_fps=4.0,
        fidelity_tier="emf",
        powerpoint_backend="auto",
    )

    json_path, markdown_path = write_audit_report(
        [result],
        tmp_path,
        top_n=1,
        run_metadata=metadata,
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert payload["metadata"]["renderer"] == "powerpoint"
    assert payload["metadata"]["fidelity_tier"] == "emf"
    assert payload["summary"]["fallback_asset_totals"] == {"emf": 1}
    assert "## Run Metadata" in markdown
    assert "## Fallback Asset Totals" in markdown
    assert "## Fallback Reason Codes" in markdown
    assert "tests/corpus/w3c/sample.svg" in markdown


def test_svg_has_animation_detects_smil_tags() -> None:
    assert _svg_has_animation(
        "<svg xmlns='http://www.w3.org/2000/svg'><rect><animate attributeName='x' from='0' to='10' dur='1s'/></rect></svg>"
    )
    assert not _svg_has_animation(
        "<svg xmlns='http://www.w3.org/2000/svg'><rect x='0' y='0' width='10' height='10'/></svg>"
    )


def test_svg_has_animation_recovers_malformed_header() -> None:
    assert _svg_has_animation(
        """<svg xmlns='http://www.w3.org/2000/svg' width='1000' height='1000'>
<
<path d='M0,0 L10,10'>
  <animateMotion dur='1s' path='M0,0 L10,10'/>
</path>
</svg>"""
    )


def test_audit_svgs_passes_fidelity_tier_to_builder(
    monkeypatch, tmp_path: Path
) -> None:
    svg_path = tmp_path / "sample.svg"
    svg_path.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")

    recorded: dict[str, object] = {}

    class StubBuilder:
        def __init__(self, **kwargs) -> None:
            recorded.update(kwargs)

    def fake_audit_svg(*args, **kwargs):
        recorded["audit_fidelity_tier"] = kwargs["fidelity_tier"]
        return AuditResult(
            svg_path=svg_path.as_posix(),
            artifact_dir=(tmp_path / "out").as_posix(),
            build_status="ok",
            render_status="skipped",
            browser_status="skipped",
            diff_status="skipped",
        )

    monkeypatch.setattr("tools.visual.corpus_audit.PptxBuilder", StubBuilder)
    monkeypatch.setattr("tools.visual.corpus_audit.audit_svg", fake_audit_svg)

    results = audit_svgs(
        [svg_path],
        output_dir=tmp_path / "audit",
        skip_render=True,
        skip_browser=True,
        fidelity_tier="bitmap",
    )

    assert len(results) == 1
    assert recorded["fidelity_tier"] == "bitmap"
    assert recorded["audit_fidelity_tier"] == "bitmap"
