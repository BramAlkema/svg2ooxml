"""Report rendering helpers for ``tools.visual.corpus_audit``."""

from __future__ import annotations

import json
import platform
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditRunMetadata:
    """Metadata that makes a visual audit report reproducible."""

    command: list[str]
    inputs: list[str]
    output_dir: str
    renderer: str
    browser_threshold: float
    skip_render: bool
    skip_browser: bool
    check_animation: bool
    animation_duration: float
    animation_fps: float
    fidelity_tier: str | None
    python: str
    platform: str
    powerpoint_backend: str | None = None
    soffice_path: str | None = None


def write_audit_report(
    results: Sequence[Any],
    output_dir: Path,
    *,
    top_n: int = 25,
    run_metadata: AuditRunMetadata | Mapping[str, object] | None = None,
) -> tuple[Path, Path]:
    """Write JSON and Markdown audit reports under *output_dir*."""
    json_path = output_dir / "audit.json"
    summary_path = output_dir / "summary.md"
    metadata_payload = _metadata_payload(run_metadata)
    payload = {
        "metadata": metadata_payload,
        "summary": build_summary(results),
        "results": [asdict(result) for result in results],
    }
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    summary_path.write_text(
        render_markdown_summary(
            results,
            top_n=top_n,
            run_metadata=metadata_payload,
        ),
        encoding="utf-8",
    )
    return json_path, summary_path


def build_run_metadata(
    *,
    command: Sequence[str],
    inputs: Sequence[Path],
    output_dir: Path,
    renderer: str,
    browser_threshold: float,
    skip_render: bool,
    skip_browser: bool,
    check_animation: bool,
    animation_duration: float,
    animation_fps: float,
    fidelity_tier: str | None,
    powerpoint_backend: str | None = None,
    soffice_path: str | None = None,
) -> AuditRunMetadata:
    """Build stable run metadata for audit reports."""
    return AuditRunMetadata(
        command=[str(item) for item in command],
        inputs=[item.as_posix() for item in inputs],
        output_dir=output_dir.as_posix(),
        renderer=renderer,
        browser_threshold=browser_threshold,
        skip_render=skip_render,
        skip_browser=skip_browser,
        check_animation=check_animation,
        animation_duration=animation_duration,
        animation_fps=animation_fps,
        fidelity_tier=fidelity_tier,
        python=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform=platform.platform(),
        powerpoint_backend=powerpoint_backend,
        soffice_path=soffice_path,
    )


def build_summary(results: Sequence[Any]) -> dict[str, object]:
    """Build an aggregate summary for a set of audit results."""
    total = len(results)
    animation_reason_totals: dict[str, int] = {}
    fidelity_tiers: Counter[str] = Counter()
    corpus_names: Counter[str] = Counter()
    for item in results:
        for reason, count in (item.animation_reason_counts or {}).items():
            animation_reason_totals[reason] = (
                animation_reason_totals.get(reason, 0) + count
            )
        fidelity_tiers[item.fidelity_tier or "default"] += 1
        corpus_names[item.corpus_name or "unknown"] += 1
    return {
        "total": total,
        "build_errors": sum(1 for item in results if item.build_status == "error"),
        "render_errors": sum(1 for item in results if item.render_status == "error"),
        "browser_errors": sum(1 for item in results if item.browser_status == "error"),
        "browser_unavailable": sum(
            1 for item in results if item.browser_status == "unavailable"
        ),
        "diff_mismatches": sum(1 for item in results if item.diff_status == "mismatch"),
        "animation_errors": sum(
            1 for item in results if item.animation_status == "error"
        ),
        "animation_mismatches": sum(
            1 for item in results if item.animation_status == "mismatch"
        ),
        "animation_fragments_emitted": sum(
            item.animation_emitted_count or 0 for item in results
        ),
        "animation_fragments_skipped": sum(
            item.animation_skipped_count or 0 for item in results
        ),
        "animation_reason_totals": dict(
            sorted(
                animation_reason_totals.items(),
                key=lambda pair: (-pair[1], pair[0]),
            )
        ),
        "fallback_asset_totals": _aggregate_result_counter(
            results, "fallback_asset_counts"
        ),
        "fallback_reason_totals": _aggregate_result_counter(
            results, "fallback_reason_counts"
        ),
        "geometry_totals": _aggregate_result_counter(results, "geometry_totals"),
        "paint_totals": _aggregate_result_counter(results, "paint_totals"),
        "stage_totals": _aggregate_result_counter(results, "stage_totals"),
        "resvg_metrics": _aggregate_result_counter(results, "resvg_metrics"),
        "by_fidelity_tier": _sort_counter(fidelity_tiers),
        "by_corpus": _sort_counter(corpus_names),
        "total_rasterized": sum(item.rasterized_count or 0 for item in results),
        "max_score": max((item.score for item in results), default=0.0),
        "top_offenders": [item.svg_path for item in results[:5]],
    }


def render_markdown_summary(
    results: Sequence[Any],
    *,
    top_n: int = 25,
    run_metadata: AuditRunMetadata | Mapping[str, object] | None = None,
) -> str:
    """Render a compact Markdown summary sorted by descending score."""
    summary = build_summary(results)
    lines = [
        "# Corpus Audit",
        "",
    ]
    metadata_payload = _metadata_payload(run_metadata)
    if metadata_payload:
        lines.extend(
            [
                "## Run Metadata",
                "",
                "| Key | Value |",
                "| --- | --- |",
            ]
        )
        for key, value in metadata_payload.items():
            if value is None:
                continue
            lines.append(
                f"| {_escape_table(key)} | "
                f"{_escape_table(_format_metadata_value(value))} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Summary",
            "",
            f"- Total SVGs: {summary['total']}",
            f"- Build errors: {summary['build_errors']}",
            f"- Render errors: {summary['render_errors']}",
            f"- Browser diff mismatches: {summary['diff_mismatches']}",
            f"- Animation mismatches: {summary['animation_mismatches']}",
            f"- Animation fragments emitted: {summary['animation_fragments_emitted']}",
            f"- Animation fragments skipped: {summary['animation_fragments_skipped']}",
            f"- Total rasterized leaves: {summary['total_rasterized']}",
            "",
        ]
    )
    _append_counter_section(
        lines,
        "Corpus Coverage",
        summary.get("by_corpus"),
        key_label="Corpus",
    )
    _append_counter_section(
        lines,
        "Fidelity Tier Coverage",
        summary.get("by_fidelity_tier"),
        key_label="Tier",
    )
    _append_counter_section(
        lines,
        "Geometry Totals",
        summary.get("geometry_totals"),
        key_label="Decision",
    )
    _append_counter_section(
        lines,
        "Paint Totals",
        summary.get("paint_totals"),
        key_label="Decision",
    )
    _append_counter_section(
        lines,
        "Fallback Asset Totals",
        summary.get("fallback_asset_totals"),
        key_label="Asset",
    )
    _append_counter_section(
        lines,
        "Fallback Reason Codes",
        summary.get("fallback_reason_totals"),
        key_label="Reason",
    )
    _append_counter_section(
        lines,
        "Resvg Metrics",
        summary.get("resvg_metrics"),
        key_label="Metric",
    )
    reason_totals = summary.get("animation_reason_totals", {})
    if isinstance(reason_totals, dict) and reason_totals:
        lines.extend(
            [
                "## Animation Reason Codes",
                "",
                "| Reason | Count |",
                "| --- | ---: |",
            ]
        )
        for reason, count in reason_totals.items():
            lines.append(f"| {reason} | {count} |")
        lines.append("")
    lines.extend(
        [
            "## Top Offenders",
            "",
            "| Score | Corpus | Tier | SVG | Build | Render | Browser | Diff | Anim | Anim Frag | SSIM | Anim SSIM | Bitmaps | Fallbacks | Max Δ |",
            "| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: |",
        ]
    )
    for item in list(results)[: max(top_n, 0)]:
        ssim = f"{item.ssim_score:.4f}" if item.ssim_score is not None else "-"
        animation_ssim = (
            f"{item.animation_min_ssim:.4f}"
            if item.animation_min_ssim is not None
            else "-"
        )
        animation_fragments = "-"
        if (
            item.animation_emitted_count is not None
            or item.animation_skipped_count is not None
        ):
            emitted = item.animation_emitted_count or 0
            skipped = item.animation_skipped_count or 0
            animation_fragments = f"{emitted}/{skipped}"
        bitmaps = (
            str(item.rasterized_count) if item.rasterized_count is not None else "-"
        )
        fallbacks = _format_counter(item.fallback_asset_counts)
        bbox = f"{item.max_bbox_delta:.2f}" if item.max_bbox_delta is not None else "-"
        lines.append(
            "| "
            f"{item.score:.1f} | {item.corpus_name or '-'} | "
            f"{item.fidelity_tier or '-'} | {item.svg_path} | {item.build_status} | "
            f"{item.render_status} | {item.browser_status} | {item.diff_status} | "
            f"{item.animation_status} | {animation_fragments} | {ssim} | "
            f"{animation_ssim} | {bitmaps} | {fallbacks} | {bbox} |"
        )
        if item.notes:
            lines.append(
                "|  |  |  | notes: "
                f"{'; '.join(item.notes)} |  |  |  |  |  |  |  |  |  |  |  |"
            )
        if item.fallback_reason_counts:
            fallback_summary = "; ".join(
                f"{reason}={count}"
                for reason, count in item.fallback_reason_counts.items()
            )
            lines.append(
                "|  |  |  | fallback reasons: "
                f"{fallback_summary} |  |  |  |  |  |  |  |  |  |  |  |"
            )
        if item.animation_reason_counts:
            reason_summary = "; ".join(
                f"{reason}={count}"
                for reason, count in sorted(
                    item.animation_reason_counts.items(),
                    key=lambda pair: (-pair[1], pair[0]),
                )
            )
            lines.append(
                "|  |  |  | animation reasons: "
                f"{reason_summary} |  |  |  |  |  |  |  |  |  |  |  |"
            )
    lines.append("")
    return "\n".join(lines)


def _append_counter_section(
    lines: list[str],
    heading: str,
    values: object,
    *,
    key_label: str,
) -> None:
    if not isinstance(values, Mapping) or not values:
        return
    lines.extend(
        [
            f"## {heading}",
            "",
            f"| {key_label} | Count |",
            "| --- | ---: |",
        ]
    )
    for key, value in values.items():
        lines.append(f"| {_escape_table(str(key))} | {value} |")
    lines.append("")


def _aggregate_result_counter(
    results: Sequence[Any],
    attribute: str,
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for item in results:
        values = getattr(item, attribute, None)
        if not isinstance(values, Mapping):
            continue
        for key, value in values.items():
            if not isinstance(key, str):
                continue
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count:
                counter[key] += count
    return _sort_counter(counter)


def _metadata_payload(
    run_metadata: AuditRunMetadata | Mapping[str, object] | None,
) -> dict[str, object]:
    if run_metadata is None:
        return {}
    if isinstance(run_metadata, AuditRunMetadata):
        return {
            key: value
            for key, value in asdict(run_metadata).items()
            if value not in (None, [], "")
        }
    return {
        str(key): value
        for key, value in run_metadata.items()
        if value not in (None, [], "")
    }


def _format_metadata_value(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value) or "-"
    if isinstance(value, Mapping):
        return json.dumps(dict(value), sort_keys=True)
    return str(value)


def _format_counter(values: Mapping[str, int]) -> str:
    if not values:
        return "-"
    return "; ".join(f"{key}={value}" for key, value in values.items())


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _sort_counter(counter: Mapping[str, int]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda pair: (-pair[1], pair[0])))


__all__ = [
    "AuditRunMetadata",
    "build_run_metadata",
    "build_summary",
    "render_markdown_summary",
    "write_audit_report",
]
