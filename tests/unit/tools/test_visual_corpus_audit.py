from __future__ import annotations

from pathlib import Path

from tools.visual.corpus_audit import (
    _artifact_subdir,
    _default_output_dir,
    _svg_has_animation,
    AuditResult,
    build_summary,
    discover_svg_paths,
    render_markdown_summary,
    resolve_audit_inputs,
    score_audit_result,
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


def test_svg_has_animation_detects_smil_tags() -> None:
    assert _svg_has_animation(
        "<svg xmlns='http://www.w3.org/2000/svg'><rect><animate attributeName='x' from='0' to='10' dur='1s'/></rect></svg>"
    )
    assert not _svg_has_animation(
        "<svg xmlns='http://www.w3.org/2000/svg'><rect x='0' y='0' width='10' height='10'/></svg>"
    )
