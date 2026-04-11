#!/usr/bin/env python3
"""Audit SVG corpora with build, render, browser, and structure checks."""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

from PIL import Image
from lxml import etree as ET

from svg2ooxml.core.tracing import ConversionTracer
from tools.visual.browser_renderer import BrowserRenderError, default_browser_renderer
from tools.visual.builder import PptxBuilder, VisualBuildError
from tools.visual.corpus_sources import (
    default_external_corpus_root,
    list_named_corpora,
    resolve_named_corpus_inputs,
)
from tools.visual.diff import ImageDiffError, VisualDiffer
from tools.visual.renderer import VisualRendererError, resolve_renderer
from tools.visual.structure_compare import compare_substructures

logger = logging.getLogger("corpus_audit")

DEFAULT_INPUTS = (
    Path("tests/visual/fixtures"),
    Path("tests/corpus"),
    Path("tests/svg"),
)
_SKIP_DIR_NAMES = {"__pycache__", "baselines", "output"}


@dataclass
class AuditResult:
    svg_path: str
    artifact_dir: str
    build_status: str = "pending"
    render_status: str = "pending"
    browser_status: str = "pending"
    diff_status: str = "pending"
    source_count: int | None = None
    target_count: int | None = None
    count_delta: int | None = None
    rasterized_count: int | None = None
    max_bbox_delta: float | None = None
    ssim_score: float | None = None
    pixel_diff_percentage: float | None = None
    animation_status: str = "skipped"
    animation_emitted_count: int | None = None
    animation_skipped_count: int | None = None
    animation_reason_counts: dict[str, int] = field(default_factory=dict)
    animation_frame_count: int | None = None
    animation_avg_ssim: float | None = None
    animation_min_ssim: float | None = None
    animation_max_pixel_diff_percentage: float | None = None
    geometry_totals: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    score: float = 0.0


def discover_svg_paths(
    inputs: Sequence[Path | str] | None = None,
    *,
    include_svgz: bool = False,
) -> list[Path]:
    """Discover SVG files under files/directories, skipping obvious artefact trees."""
    candidates = inputs or DEFAULT_INPUTS
    suffixes = {".svg"}
    if include_svgz:
        suffixes.add(".svgz")

    found: set[Path] = set()
    for candidate in candidates:
        path = Path(candidate)
        if not path.exists():
            logger.debug("Skipping missing input path: %s", path)
            continue
        if path.is_file():
            if path.suffix.lower() in suffixes:
                found.add(path)
            continue
        for file_path in path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in suffixes:
                continue
            if any(parent.name in _SKIP_DIR_NAMES for parent in file_path.parents):
                continue
            found.add(file_path)
    return sorted(found, key=lambda item: item.as_posix())


def resolve_audit_inputs(
    path_inputs: Sequence[Path | str] | None = None,
    *,
    named_corpora: Sequence[str] | None = None,
    corpus_root: Path | None = None,
) -> list[Path]:
    """Resolve local paths plus named external corpora into audit inputs."""
    resolved: list[Path] = [Path(item) for item in (path_inputs or [])]
    if named_corpora:
        resolved.extend(
            resolve_named_corpus_inputs(
                list(named_corpora),
                root=corpus_root,
            )
        )
    if not resolved:
        return list(DEFAULT_INPUTS)
    return resolved


def audit_svgs(
    svg_paths: Sequence[Path],
    *,
    output_dir: Path,
    browser_threshold: float = 0.9,
    skip_render: bool = False,
    skip_browser: bool = False,
    renderer_name: str = "soffice",
    soffice_path: str | None = None,
    soffice_profile: str | None = None,
    powerpoint_backend: str = "auto",
    powerpoint_delay: float = 0.5,
    powerpoint_slideshow_delay: float = 0.25,
    powerpoint_open_timeout: float = 30.0,
    powerpoint_capture_timeout: float = 3.0,
    powerpoint_use_keys: bool = False,
    powerpoint_no_reopen: bool = False,
    check_animation: bool = False,
    animation_duration: float = 4.0,
    animation_fps: float = 4.0,
    fidelity_tier: str | None = None,
) -> list[AuditResult]:
    """Audit a collection of SVG paths and return ranked results."""
    output_dir.mkdir(parents=True, exist_ok=True)

    builder = PptxBuilder(
        filter_strategy="resvg",
        geometry_mode="resvg",
        fidelity_tier=fidelity_tier,
    )
    renderer = None
    render_available = False
    if not skip_render:
        renderer = resolve_renderer(
            renderer_name=renderer_name,
            soffice_path=soffice_path,
            user_installation=soffice_profile,
            powerpoint_backend=powerpoint_backend,
            powerpoint_delay=powerpoint_delay,
            powerpoint_slideshow_delay=powerpoint_slideshow_delay,
            powerpoint_open_timeout=powerpoint_open_timeout,
            powerpoint_capture_timeout=powerpoint_capture_timeout,
            powerpoint_use_keys=powerpoint_use_keys,
            powerpoint_no_reopen=powerpoint_no_reopen,
        )
        render_available = bool(getattr(renderer, "available", True))

    browser_renderer = default_browser_renderer()
    browser_available = bool(getattr(browser_renderer, "available", False))
    differ = VisualDiffer(threshold=browser_threshold)

    results = [
        audit_svg(
            svg_path,
            output_dir=output_dir,
            builder=builder,
            renderer=renderer,
            render_available=render_available,
            browser_renderer=browser_renderer,
            browser_available=browser_available,
            differ=differ,
            skip_render=skip_render,
            skip_browser=skip_browser,
            check_animation=check_animation,
            animation_duration=animation_duration,
            animation_fps=animation_fps,
        )
        for svg_path in svg_paths
    ]
    return sorted(results, key=lambda item: item.score, reverse=True)


def audit_svg(
    svg_path: Path,
    *,
    output_dir: Path,
    builder: PptxBuilder,
    renderer: object | None,
    render_available: bool,
    browser_renderer: object,
    browser_available: bool,
    differ: VisualDiffer,
    skip_render: bool,
    skip_browser: bool,
    check_animation: bool,
    animation_duration: float,
    animation_fps: float,
) -> AuditResult:
    """Audit a single SVG and persist its artefacts under *output_dir*."""
    artifact_dir = output_dir / _artifact_subdir(svg_path)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result = AuditResult(
        svg_path=svg_path.as_posix(),
        artifact_dir=artifact_dir.as_posix(),
        render_status="skipped" if skip_render else "pending",
        browser_status="skipped" if skip_browser else "pending",
        diff_status="skipped",
    )
    logger.info("Auditing %s", svg_path)

    try:
        svg_text = svg_path.read_text(encoding="utf-8")
    except OSError as exc:
        result.build_status = "error"
        result.errors["read"] = str(exc)
        result.notes.append("Unable to read SVG source.")
        result.score = score_audit_result(result)
        return result

    pptx_path = artifact_dir / "presentation.pptx"
    tracer = ConversionTracer()
    trace_report: dict[str, object] | None = None
    build_ok = False

    try:
        builder.build_from_svg(svg_text, pptx_path, source_path=svg_path, tracer=tracer)
    except VisualBuildError as exc:
        result.build_status = "error"
        result.errors["build"] = str(exc)
        result.notes.append("PPTX build failed.")
    else:
        build_ok = True
        result.build_status = "ok"
        trace_report = tracer.report().to_dict()
        _apply_animation_trace_metrics(result, trace_report)
        geometry_totals = trace_report.get("geometry_totals", {})
        if isinstance(geometry_totals, dict):
            result.geometry_totals = {
                str(key): int(value) for key, value in geometry_totals.items()
            }

    if build_ok:
        try:
            structure = compare_substructures(
                svg_text,
                pptx_path,
                source_path=svg_path,
                filter_strategy="resvg",
                geometry_mode="resvg",
                trace_report=trace_report,
            )
        except ValueError as exc:
            result.errors["structure"] = str(exc)
            result.notes.append("Structure compare failed.")
        else:
            result.source_count = structure.source_count
            result.target_count = structure.target_count
            result.count_delta = structure.count_delta
            result.rasterized_count = len(structure.rasterized_pairs())
            mismatches = structure.top_bbox_mismatches(limit=1)
            result.max_bbox_delta = mismatches[0].max_abs_delta if mismatches else 0.0

    render_image: Path | None = None
    if build_ok and not skip_render:
        if not render_available or renderer is None:
            result.render_status = "unavailable"
            result.notes.append("PPTX renderer is not available.")
        else:
            render_dir = artifact_dir / "render"
            render_dir.mkdir(exist_ok=True)
            try:
                rendered = renderer.render(pptx_path, render_dir)
            except VisualRendererError as exc:
                result.render_status = "error"
                result.errors["render"] = str(exc)
                result.notes.append("PPTX render failed.")
            else:
                result.render_status = "ok"
                images = [Path(path) for path in rendered.images]
                if images:
                    render_image = images[0]
                else:
                    result.render_status = "error"
                    result.errors["render"] = (
                        "Renderer completed without producing slide images."
                    )

    browser_image: Path | None = None
    if not skip_browser:
        if not browser_available:
            result.browser_status = "unavailable"
            result.notes.append("Browser renderer is not available.")
        else:
            browser_dir = artifact_dir / "browser"
            browser_dir.mkdir(exist_ok=True)
            browser_image = browser_dir / "reference.png"
            try:
                browser_renderer.render_svg(
                    svg_text, browser_image, source_path=svg_path
                )
            except (BrowserRenderError, OSError, RuntimeError, ValueError) as exc:
                result.browser_status = "error"
                result.errors["browser"] = str(exc)
                result.notes.append("Browser render failed.")
                browser_image = None
            else:
                result.browser_status = "ok"

    if render_image is not None and browser_image is not None:
        try:
            comparison = differ.compare(
                Image.open(browser_image),
                Image.open(render_image),
                generate_diff=True,
            )
        except (ImageDiffError, RuntimeError, OSError, ValueError) as exc:
            result.diff_status = "error"
            result.errors["diff"] = str(exc)
            result.notes.append("Browser diff failed.")
        else:
            result.ssim_score = comparison.ssim_score
            result.pixel_diff_percentage = comparison.pixel_diff_percentage
            result.diff_status = "ok" if comparison.passed else "mismatch"
            if comparison.diff_image is not None:
                diff_path = artifact_dir / "browser_diff.png"
                comparison.save_diff(diff_path)
            if not comparison.passed:
                result.notes.append("Browser parity mismatch.")
    elif result.diff_status == "skipped":
        if result.render_status != "ok":
            result.notes.append(
                "Browser diff skipped because PPTX render is unavailable."
            )
        elif result.browser_status != "ok":
            result.notes.append(
                "Browser diff skipped because browser render is unavailable."
            )

    if check_animation and build_ok and _svg_has_animation(svg_text):
        _run_animation_audit(
            result,
            svg_text=svg_text,
            svg_path=svg_path,
            pptx_path=pptx_path,
            artifact_dir=artifact_dir,
            renderer=renderer,
            browser_renderer=browser_renderer,
            browser_available=browser_available,
            differ=differ,
            duration=animation_duration,
            fps=animation_fps,
        )

    result.score = score_audit_result(result)
    return result


def _run_animation_audit(
    result: AuditResult,
    *,
    svg_text: str,
    svg_path: Path,
    pptx_path: Path,
    artifact_dir: Path,
    renderer: object | None,
    browser_renderer: object,
    browser_available: bool,
    differ: VisualDiffer,
    duration: float,
    fps: float,
) -> None:
    capture_animation = getattr(renderer, "capture_animation", None)
    if renderer is None or not callable(capture_animation):
        result.animation_status = "unavailable"
        result.notes.append("Animation audit requires a renderer with live capture.")
        return
    if not browser_available:
        result.animation_status = "unavailable"
        result.notes.append("Animation audit requires a browser renderer.")
        return

    render_frames: list[Path] | None = None
    browser_frames: list[Path] | None = None

    try:
        render_frames = list(
            capture_animation(
                pptx_path,
                artifact_dir / "render_animation",
                duration=duration,
                fps=fps,
            )
        )
        browser_frames = list(
            browser_renderer.capture_animation(
                svg_text,
                artifact_dir / "browser_animation",
                duration=duration,
                fps=fps,
                source_path=svg_path,
            )
        )
    except (
        BrowserRenderError,
        VisualRendererError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        result.animation_status = "error"
        result.errors["animation"] = str(exc)
        result.notes.append("Animation capture failed.")
        return

    frame_count = min(len(render_frames), len(browser_frames))
    result.animation_frame_count = frame_count
    if frame_count <= 0:
        result.animation_status = "error"
        result.errors["animation"] = "Animation capture produced no comparable frames."
        result.notes.append("Animation capture produced no comparable frames.")
        return
    if len(render_frames) != len(browser_frames):
        result.notes.append(
            "Animation frame counts differ between PowerPoint and browser capture."
        )

    ssim_scores: list[float] = []
    pixel_diffs: list[float] = []
    worst_comparison = None
    worst_index = -1

    for index in range(frame_count):
        comparison = differ.compare(
            Image.open(browser_frames[index]),
            Image.open(render_frames[index]),
            generate_diff=True,
        )
        ssim_scores.append(comparison.ssim_score)
        pixel_diffs.append(comparison.pixel_diff_percentage)
        if (
            worst_comparison is None
            or comparison.ssim_score < worst_comparison.ssim_score
        ):
            worst_comparison = comparison
            worst_index = index

    result.animation_avg_ssim = sum(ssim_scores) / len(ssim_scores)
    result.animation_min_ssim = min(ssim_scores)
    result.animation_max_pixel_diff_percentage = max(pixel_diffs)
    result.animation_status = (
        "ok" if all(score >= differ.threshold for score in ssim_scores) else "mismatch"
    )
    if result.animation_status == "mismatch":
        result.notes.append("Animation parity mismatch.")

    if worst_comparison is not None and worst_comparison.diff_image is not None:
        diff_dir = artifact_dir / "animation_diff"
        diff_dir.mkdir(exist_ok=True)
        worst_comparison.save_diff(diff_dir / f"frame_{worst_index:04d}.png")


def _svg_has_animation(svg_text: str) -> bool:
    try:
        parser = ET.XMLParser(recover=True)
        root = ET.fromstring(svg_text.encode("utf-8"), parser)
    except ET.XMLSyntaxError:
        return False
    animation_tags = {
        "animate",
        "animateMotion",
        "animateTransform",
        "animateColor",
        "set",
    }
    for element in root.iter():
        tag = element.tag
        if isinstance(tag, str) and tag.split("}")[-1] in animation_tags:
            return True
    return False


def _apply_animation_trace_metrics(
    result: AuditResult,
    trace_report: dict[str, object] | None,
) -> None:
    if not isinstance(trace_report, dict):
        return
    stage_events = trace_report.get("stage_events")
    if not isinstance(stage_events, list):
        return

    emitted = 0
    skipped = 0
    reason_counts: dict[str, int] = {}

    def _bump(reason: str | None) -> None:
        if not reason:
            return
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    for event in stage_events:
        if not isinstance(event, dict):
            continue
        if event.get("stage") != "animation":
            continue
        action = event.get("action")
        metadata = event.get("metadata")
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        if action == "fragment_emitted":
            emitted += 1
            continue
        if action == "fragment_skipped":
            skipped += 1
            _bump(str(metadata_dict.get("reason")) if metadata_dict.get("reason") else None)
            continue
        if action == "parse_fallback":
            reason = metadata_dict.get("reason")
            count = metadata_dict.get("count")
            try:
                count_value = int(count)
            except (TypeError, ValueError):
                count_value = 1
            if reason:
                reason_counts[str(reason)] = reason_counts.get(str(reason), 0) + count_value
            continue
        if action in {"timing_skipped", "unmapped_begin_trigger_target"}:
            _bump(action)
            reason = metadata_dict.get("reason")
            if reason:
                _bump(str(reason))

    if emitted or skipped or reason_counts:
        result.animation_emitted_count = emitted
        result.animation_skipped_count = skipped
        result.animation_reason_counts = dict(
            sorted(reason_counts.items(), key=lambda pair: (-pair[1], pair[0]))
        )


def score_audit_result(result: AuditResult) -> float:
    """Compute a priority score for a result, higher means more urgent."""
    score = 0.0
    if result.build_status == "error":
        score += 1000.0
    if result.render_status == "error":
        score += 250.0
    elif result.render_status == "unavailable":
        score += 25.0
    if result.browser_status == "error":
        score += 120.0
    elif result.browser_status == "unavailable":
        score += 10.0
    if result.diff_status == "error":
        score += 80.0
    elif result.diff_status == "mismatch":
        score += 40.0
    if result.animation_status == "error":
        score += 180.0
    elif result.animation_status == "unavailable":
        score += 20.0
    elif result.animation_status == "mismatch":
        score += 90.0

    if result.ssim_score is not None:
        score += max(0.0, (1.0 - result.ssim_score) * 200.0)
    if result.pixel_diff_percentage is not None:
        score += result.pixel_diff_percentage
    if result.rasterized_count is not None:
        score += result.rasterized_count * 8.0
    if result.max_bbox_delta is not None:
        score += result.max_bbox_delta * 2.0
    if result.count_delta is not None:
        score += abs(result.count_delta) * 20.0
    if result.animation_min_ssim is not None:
        score += max(0.0, (1.0 - result.animation_min_ssim) * 250.0)
    if result.animation_max_pixel_diff_percentage is not None:
        score += result.animation_max_pixel_diff_percentage * 0.5
    return round(score, 3)


def write_audit_report(
    results: Sequence[AuditResult],
    output_dir: Path,
    *,
    top_n: int = 25,
) -> tuple[Path, Path]:
    """Write JSON and Markdown audit reports under *output_dir*."""
    json_path = output_dir / "audit.json"
    summary_path = output_dir / "summary.md"
    payload = {
        "summary": build_summary(results),
        "results": [asdict(result) for result in results],
    }
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    summary_path.write_text(
        render_markdown_summary(results, top_n=top_n), encoding="utf-8"
    )
    return json_path, summary_path


def build_summary(results: Sequence[AuditResult]) -> dict[str, object]:
    """Build an aggregate summary for a set of audit results."""
    total = len(results)
    animation_reason_totals: dict[str, int] = {}
    for item in results:
        for reason, count in (item.animation_reason_counts or {}).items():
            animation_reason_totals[reason] = (
                animation_reason_totals.get(reason, 0) + count
            )
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
        "total_rasterized": sum(item.rasterized_count or 0 for item in results),
        "max_score": max((item.score for item in results), default=0.0),
        "top_offenders": [item.svg_path for item in results[:5]],
    }


def render_markdown_summary(
    results: Sequence[AuditResult],
    *,
    top_n: int = 25,
) -> str:
    """Render a compact Markdown summary sorted by descending score."""
    summary = build_summary(results)
    lines = [
        "# Corpus Audit",
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
        "| Score | SVG | Build | Render | Browser | Diff | Anim | Anim Frag | SSIM | Anim SSIM | Bitmaps | Max Δ |",
        "| ---: | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for item in list(results)[: max(top_n, 0)]:
        ssim = f"{item.ssim_score:.4f}" if item.ssim_score is not None else "-"
        animation_ssim = (
            f"{item.animation_min_ssim:.4f}"
            if item.animation_min_ssim is not None
            else "-"
        )
        animation_fragments = "-"
        if item.animation_emitted_count is not None or item.animation_skipped_count is not None:
            emitted = item.animation_emitted_count or 0
            skipped = item.animation_skipped_count or 0
            animation_fragments = f"{emitted}/{skipped}"
        bitmaps = (
            str(item.rasterized_count) if item.rasterized_count is not None else "-"
        )
        bbox = f"{item.max_bbox_delta:.2f}" if item.max_bbox_delta is not None else "-"
        lines.append(
            "| "
            f"{item.score:.1f} | {item.svg_path} | {item.build_status} | "
            f"{item.render_status} | {item.browser_status} | {item.diff_status} | "
            f"{item.animation_status} | {animation_fragments} | {ssim} | {animation_ssim} | {bitmaps} | {bbox} |"
        )
        if item.notes:
            lines.append(
                "|  | notes: " f"{'; '.join(item.notes)} |  |  |  |  |  |  |  |  |  |  |"
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
                "|  | animation reasons: "
                f"{reason_summary} |  |  |  |  |  |  |  |  |  |  |"
            )
    lines.append("")
    return "\n".join(lines)


def _artifact_subdir(svg_path: Path) -> Path:
    try:
        rel = svg_path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        absolute = svg_path.resolve()
        parts = [
            part for part in absolute.parts if part not in {"", os.sep, absolute.anchor}
        ]
        if not parts:
            return Path(svg_path.stem)
        return Path("_external").joinpath(*parts).with_suffix("")
    return rel.with_suffix("")


def _default_output_dir(renderer_name: str) -> Path:
    if renderer_name == "powerpoint":
        return Path("reports/visual/powerpoint/audit")
    return Path("reports/visual/audit")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs",
        nargs="*",
        help="SVG files or directories to audit. Defaults to the main local corpora.",
    )
    parser.add_argument(
        "--corpus",
        action="append",
        dest="named_corpora",
        choices=list_named_corpora(),
        default=[],
        help="Named external corpus to include in the audit.",
    )
    parser.add_argument(
        "--corpus-root",
        default=str(default_external_corpus_root()),
        help="Root directory containing named external corpus checkouts.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Directory to write audit artefacts and reports "
            "(default: reports/visual/audit for soffice, "
            "reports/visual/powerpoint/audit for PowerPoint)."
        ),
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Optional cap on the number of discovered SVGs to audit.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="How many top offenders to include in the Markdown summary.",
    )
    parser.add_argument(
        "--include-svgz",
        action="store_true",
        help="Also discover .svgz inputs.",
    )
    parser.add_argument(
        "--skip-render",
        action="store_true",
        help="Skip PPTX bitmap rendering and only build/structure-check.",
    )
    parser.add_argument(
        "--skip-browser",
        action="store_true",
        help="Skip Playwright browser rendering and SSIM diffing.",
    )
    parser.add_argument(
        "--browser-threshold",
        type=float,
        default=0.90,
        help="SSIM threshold for browser parity scoring.",
    )
    parser.add_argument(
        "--renderer",
        choices=("soffice", "powerpoint"),
        default="soffice",
        help="PPTX renderer to use when render checks are enabled.",
    )
    parser.add_argument(
        "--soffice",
        help="Explicit path to the soffice binary.",
    )
    parser.add_argument(
        "--soffice-profile",
        help="LibreOffice user profile directory passed via -env:UserInstallation.",
    )
    parser.add_argument(
        "--powerpoint-backend",
        choices=("auto", "screencapture", "sckit"),
        default="auto",
        help="PowerPoint capture backend when --renderer=powerpoint.",
    )
    parser.add_argument(
        "--powerpoint-delay",
        type=float,
        default=0.5,
        help="Seconds to wait after opening a presentation before slideshow startup.",
    )
    parser.add_argument(
        "--powerpoint-slideshow-delay",
        type=float,
        default=0.25,
        help="Seconds to wait after slideshow startup before capture.",
    )
    parser.add_argument(
        "--powerpoint-open-timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for PowerPoint to open/repair a presentation.",
    )
    parser.add_argument(
        "--powerpoint-capture-timeout",
        type=float,
        default=3.0,
        help="Seconds to wait for ScreenCaptureKit frame capture.",
    )
    parser.add_argument(
        "--powerpoint-use-keys",
        action="store_true",
        help="Allow focused keystroke fallback if PowerPoint object-model slideshow start fails.",
    )
    parser.add_argument(
        "--powerpoint-no-reopen",
        action="store_true",
        help="Disable periodic reopen attempts while waiting for slides.",
    )
    parser.add_argument(
        "--fidelity-tier",
        choices=("direct", "mimic", "emf", "bitmap"),
        help="Audit a specific fidelity tier so fallback paths can be exercised explicitly.",
    )
    parser.add_argument(
        "--check-animation",
        action="store_true",
        help="Capture live PowerPoint/browser animation frames for animated SVGs.",
    )
    parser.add_argument(
        "--animation-duration",
        type=float,
        default=4.0,
        help="Seconds of animation playback to capture when --check-animation is enabled.",
    )
    parser.add_argument(
        "--animation-fps",
        type=float,
        default=4.0,
        help="Frames per second for animation capture when --check-animation is enabled.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    inputs = resolve_audit_inputs(
        [Path(item) for item in args.inputs] if args.inputs else None,
        named_corpora=args.named_corpora,
        corpus_root=Path(args.corpus_root),
    )
    svg_paths = discover_svg_paths(inputs, include_svgz=args.include_svgz)
    if args.max_files is not None:
        svg_paths = svg_paths[: max(args.max_files, 0)]
    if not svg_paths:
        raise SystemExit("No SVG files found for audit.")

    output_dir = (
        Path(args.output) if args.output else _default_output_dir(args.renderer)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    results = audit_svgs(
        svg_paths,
        output_dir=output_dir,
        browser_threshold=args.browser_threshold,
        skip_render=args.skip_render,
        skip_browser=args.skip_browser,
        renderer_name=args.renderer,
        soffice_path=args.soffice,
        soffice_profile=args.soffice_profile,
        powerpoint_backend=args.powerpoint_backend,
        powerpoint_delay=args.powerpoint_delay,
        powerpoint_slideshow_delay=args.powerpoint_slideshow_delay,
        powerpoint_open_timeout=args.powerpoint_open_timeout,
        powerpoint_capture_timeout=args.powerpoint_capture_timeout,
        powerpoint_use_keys=args.powerpoint_use_keys,
        powerpoint_no_reopen=args.powerpoint_no_reopen,
        fidelity_tier=args.fidelity_tier,
        check_animation=args.check_animation,
        animation_duration=args.animation_duration,
        animation_fps=args.animation_fps,
    )
    json_path, summary_path = write_audit_report(results, output_dir, top_n=args.top)

    logger.info("Audit complete: %d SVGs", len(results))
    logger.info("JSON report: %s", json_path)
    logger.info("Markdown summary: %s", summary_path)
    for item in results[: min(10, len(results))]:
        logger.info(
            "score=%6.1f build=%s render=%s browser=%s diff=%s bitmaps=%s bbox=%s %s",
            item.score,
            item.build_status,
            item.render_status,
            item.browser_status,
            item.diff_status,
            item.rasterized_count if item.rasterized_count is not None else "-",
            f"{item.max_bbox_delta:.2f}" if item.max_bbox_delta is not None else "-",
            item.svg_path,
        )


__all__ = [
    "AuditResult",
    "audit_svgs",
    "build_summary",
    "discover_svg_paths",
    "render_markdown_summary",
    "score_audit_result",
    "write_audit_report",
]


if __name__ == "__main__":
    main()
