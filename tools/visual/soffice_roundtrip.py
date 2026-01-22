#!/usr/bin/env python3
"""Batch PPTX generation + LibreOffice rendering to sanity-check fixtures.

This script builds PPTX files from SVG fixtures (or copies existing PPTX files),
renders them through LibreOffice (soffice), and records any failures.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
for entry in (REPO_ROOT, SRC_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from tools.visual.builder import PptxBuilder, VisualBuildError
from tools.visual.diff import ImageDiff, ImageDiffError
from tools.visual.renderer import LibreOfficeRenderer, VisualRendererError, default_renderer

logger = logging.getLogger("soffice_roundtrip")


@dataclass
class RoundTripResult:
    source: str
    pptx: str | None
    status: str
    slides: int | None = None
    error: str | None = None
    roundtrip_pptx: str | None = None
    roundtrip_status: str | None = None
    diff_max_delta: float | None = None
    diff_mean_delta: float | None = None
    diff_error: str | None = None
    xml_diff_status: str | None = None
    xml_changed_count: int | None = None
    xml_added_count: int | None = None
    xml_removed_count: int | None = None
    xml_changed_files: list[str] | None = None
    xml_error: str | None = None


def _collect_suite(suite: str) -> list[Path]:
    if suite == "fixtures":
        return sorted(
            path
            for path in (REPO_ROOT / "tests" / "visual" / "fixtures").glob("*.svg")
            if path.is_file()
        )
    if suite == "resvg":
        return sorted((REPO_ROOT / "tests" / "visual" / "fixtures" / "resvg").glob("*.svg"))
    if suite == "w3c":
        return sorted((REPO_ROOT / "tests" / "svg").rglob("*.svg"))
    if suite == "all":
        paths: set[Path] = set()
        for name in ("fixtures", "resvg", "w3c"):
            paths.update(_collect_suite(name))
        return sorted(paths)
    raise SystemExit(f"Unknown suite {suite!r}.")


def _collect_paths(paths: Sequence[str], suite: str | None) -> list[Path]:
    collected: list[Path] = []
    if suite:
        collected.extend(_collect_suite(suite))
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            collected.extend(sorted(path.rglob("*.svg")))
            collected.extend(sorted(path.rglob("*.pptx")))
        elif path.exists():
            collected.append(path)
        else:
            logger.warning("Skipping missing path: %s", path)
    return collected


def _filter_paths(paths: Iterable[Path], match: str | None) -> list[Path]:
    if not match:
        return list(paths)
    token = match.lower()
    return [path for path in paths if token in str(path).lower()]


def _case_dir(output_root: Path, source: Path) -> Path:
    try:
        relative = source.resolve().relative_to(REPO_ROOT)
        base = relative.with_suffix("")
    except Exception:
        base = Path(source.stem)
    return output_root / base


def _resolve_renderer(
    soffice_path: str | None,
    timeout: float | None,
    user_installation: str | None,
) -> LibreOfficeRenderer:
    if not user_installation:
        user_installation = os.getenv("SVG2OOXML_SOFFICE_USER_INSTALL")
    if soffice_path:
        return LibreOfficeRenderer(
            soffice_path=soffice_path,
            timeout=timeout,
            user_installation=user_installation,
        )
    if timeout is None:
        return default_renderer(user_installation=user_installation)
    return default_renderer(timeout=timeout, user_installation=user_installation)


def _build_or_copy(
    source: Path,
    *,
    output_dir: Path,
    builder: PptxBuilder,
) -> tuple[Path, int | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pptx_path = output_dir / "presentation.pptx"
    if source.suffix.lower() == ".pptx":
        shutil.copy2(source, pptx_path)
        return pptx_path, None
    svg_text = source.read_text(encoding="utf-8")
    build_result = builder.build_from_svg(svg_text, pptx_path, source_path=source)
    return build_result.pptx_path, build_result.slide_count


def _roundtrip_pptx(
    renderer: LibreOfficeRenderer,
    pptx_path: Path,
    output_dir: Path,
    *,
    timeout: float | None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    args = [
        *renderer.base_args(),
        "--convert-to",
        "pptx",
        "--outdir",
        str(output_dir),
        str(pptx_path),
    ]
    cmd = [renderer.command_path or "soffice", *args]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise VisualRendererError(f"LibreOffice timed out after {timeout} seconds.") from exc
    if proc.returncode != 0:
        message_lines = [
            "LibreOffice failed to roundtrip PPTX.",
            f"exit code: {proc.returncode}",
        ]
        if proc.stdout:
            message_lines.append(f"stdout:\n{proc.stdout}")
        if proc.stderr:
            message_lines.append(f"stderr:\n{proc.stderr}")
        raise VisualRendererError("\n".join(message_lines))

    candidates = sorted(output_dir.glob("*.pptx"))
    if not candidates:
        raise VisualRendererError(f"LibreOffice produced no PPTX in {output_dir}.")
    if len(candidates) > 1:
        # Prefer matching base name if multiple files exist.
        stem = pptx_path.stem
        for candidate in candidates:
            if candidate.stem == stem:
                return candidate
    return candidates[0]


def _canonicalize_xml(data: bytes) -> bytes:
    try:
        from lxml import etree
    except ImportError:
        return data.strip()

    try:
        parser = etree.XMLParser(remove_blank_text=True, recover=True)
        root = etree.fromstring(data, parser=parser)
        return etree.tostring(root, method="c14n")
    except Exception:
        return data.strip()


def _load_xml_parts(path: Path) -> dict[str, bytes]:
    parts: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith(".xml") or name.endswith(".rels"):
                data = archive.read(name)
                parts[name] = _canonicalize_xml(data)
    return parts


def _diff_xml_parts(
    original: Path,
    roundtrip: Path,
    *,
    max_files: int,
) -> tuple[int, int, int, list[str]]:
    original_parts = _load_xml_parts(original)
    roundtrip_parts = _load_xml_parts(roundtrip)

    added = sorted(set(roundtrip_parts) - set(original_parts))
    removed = sorted(set(original_parts) - set(roundtrip_parts))
    changed = sorted(
        name
        for name in sorted(set(original_parts) & set(roundtrip_parts))
        if original_parts[name] != roundtrip_parts[name]
    )

    if max_files > 0:
        changed = changed[:max_files]
    return len(changed), len(added), len(removed), changed


def run_roundtrip(
    sources: Sequence[Path],
    *,
    output_root: Path,
    builder: PptxBuilder,
    renderer: LibreOfficeRenderer,
    compare_roundtrip: bool = False,
    diff_tool: ImageDiff | None = None,
    xml_diff: bool = False,
    xml_diff_max_files: int = 20,
    renderer_timeout: float | None = None,
    limit: int | None = None,
    shuffle: bool = False,
    seed: int | None = None,
) -> list[RoundTripResult]:
    if shuffle:
        rng = random.Random(seed)
        sources = list(sources)
        rng.shuffle(sources)
    if limit:
        sources = list(sources)[:limit]

    results: list[RoundTripResult] = []
    total = len(sources)
    for idx, source in enumerate(sources, start=1):
        logger.info("[%d/%d] %s", idx, total, source)
        case_dir = _case_dir(output_root, source)
        render_dir = case_dir / "render"
        try:
            pptx_path, slide_count = _build_or_copy(
                source,
                output_dir=case_dir,
                builder=builder,
            )
        except (VisualBuildError, OSError) as exc:
            results.append(
                RoundTripResult(
                    source=str(source),
                    pptx=None,
                    slides=None,
                    status="build_failed",
                    error=str(exc),
                )
            )
            logger.warning("Build failed for %s: %s", source, exc)
            continue

        try:
            renderer.render(pptx_path, render_dir / "original")
        except VisualRendererError as exc:
            results.append(
                RoundTripResult(
                    source=str(source),
                    pptx=str(pptx_path),
                    slides=slide_count,
                    status="render_failed",
                    error=str(exc),
                )
            )
            logger.warning("Render failed for %s: %s", source, exc)
            continue

        result = RoundTripResult(
            source=str(source),
            pptx=str(pptx_path),
            slides=slide_count,
            status="ok",
        )

        if compare_roundtrip:
            try:
                roundtrip_path = _roundtrip_pptx(
                    renderer,
                    pptx_path,
                    case_dir / "roundtrip",
                    timeout=renderer_timeout,
                )
                result.roundtrip_pptx = str(roundtrip_path)
                renderer.render(roundtrip_path, render_dir / "roundtrip")
                result.roundtrip_status = "ok"
            except VisualRendererError as exc:
                result.roundtrip_status = "roundtrip_failed"
                result.diff_error = str(exc)
                results.append(result)
                logger.warning("Roundtrip failed for %s: %s", source, exc)
                continue

            if diff_tool is not None:
                try:
                    diff_result = diff_tool.compare_directories(
                        render_dir / "roundtrip",
                        render_dir / "original",
                        diff_dir=render_dir / "diff",
                    )
                    result.diff_max_delta = diff_result.max_delta
                    result.diff_mean_delta = diff_result.mean_delta
                except ImageDiffError as exc:
                    result.roundtrip_status = "diff_failed"
                    result.diff_error = str(exc)
                    logger.warning("Diff failed for %s: %s", source, exc)

            if xml_diff:
                try:
                    changed, added, removed, changed_files = _diff_xml_parts(
                        pptx_path,
                        roundtrip_path,
                        max_files=xml_diff_max_files,
                    )
                    result.xml_changed_count = changed
                    result.xml_added_count = added
                    result.xml_removed_count = removed
                    result.xml_changed_files = changed_files
                    if changed or added or removed:
                        result.xml_diff_status = "changed"
                    else:
                        result.xml_diff_status = "ok"
                except Exception as exc:
                    result.xml_diff_status = "error"
                    result.xml_error = str(exc)
                    logger.warning("XML diff failed for %s: %s", source, exc)

        results.append(result)
    return results


def _write_json_report(results: Sequence[RoundTripResult], output_path: Path) -> None:
    payload = [asdict(result) for result in results]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="SVG/PPTX files or directories to include (optional).",
    )
    parser.add_argument(
        "--suite",
        choices=["fixtures", "resvg", "w3c", "all"],
        help="Predefined fixture set to include.",
    )
    parser.add_argument(
        "--match",
        help="Substring filter applied to the input path list (case-insensitive).",
    )
    parser.add_argument(
        "--output",
        default="reports/visual/soffice_roundtrip",
        help="Root directory for generated PPTX and render outputs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of fixtures processed.",
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Shuffle fixture order before applying --limit.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Seed for --shuffle.",
    )
    parser.add_argument(
        "--soffice",
        help="Explicit soffice path (defaults to SVG2OOXML_SOFFICE_PATH or PATH lookup).",
    )
    parser.add_argument(
        "--soffice-profile",
        help=(
            "LibreOffice user profile directory passed via -env:UserInstallation "
            "(defaults to SVG2OOXML_SOFFICE_USER_INSTALL)."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=90.0,
        help="LibreOffice timeout per render (seconds).",
    )
    parser.add_argument(
        "--roundtrip",
        action="store_true",
        help="Convert PPTX to PPTX via LibreOffice and compare rendered output.",
    )
    parser.add_argument(
        "--diff-max",
        type=float,
        default=12.0,
        help="Max per-channel delta for roundtrip image diffs.",
    )
    parser.add_argument(
        "--diff-mean",
        type=float,
        default=1.5,
        help="Mean per-channel delta for roundtrip image diffs.",
    )
    parser.add_argument(
        "--xml-diff",
        action="store_true",
        help="Compare XML parts between the original and roundtripped PPTX.",
    )
    parser.add_argument(
        "--xml-diff-max-files",
        type=int,
        default=20,
        help="Maximum XML file names to include per diff result (0 for none).",
    )
    parser.add_argument(
        "--filter-strategy",
        default=os.getenv("SVG2OOXML_VISUAL_FILTER_STRATEGY", "resvg"),
        help="Filter strategy passed to the SVG pipeline.",
    )
    parser.add_argument(
        "--slide-size-mode",
        default=os.getenv("SVG2OOXML_SLIDE_SIZE_MODE", "same"),
        help="Slide size mode passed to the PPTX builder.",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        help="Write JSON summary report to the given path.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    sources = _collect_paths(args.paths, args.suite)
    sources = _filter_paths(sources, args.match)
    sources = sorted(set(sources))
    if not sources:
        raise SystemExit("No matching SVG/PPTX fixtures found.")

    renderer = _resolve_renderer(args.soffice, args.timeout, args.soffice_profile)
    if not renderer.available:
        raise SystemExit("LibreOffice (soffice) is not available. Install it or set SVG2OOXML_SOFFICE_PATH.")

    output_root = Path(args.output)
    builder = PptxBuilder(
        filter_strategy=args.filter_strategy,
        slide_size_mode=args.slide_size_mode,
    )
    diff_tool = None
    if args.roundtrip:
        diff_tool = ImageDiff(max_delta=args.diff_max, mean_delta=args.diff_mean)

    results = run_roundtrip(
        sources,
        output_root=output_root,
        builder=builder,
        renderer=renderer,
        compare_roundtrip=args.roundtrip,
        diff_tool=diff_tool,
        xml_diff=args.xml_diff,
        xml_diff_max_files=args.xml_diff_max_files,
        renderer_timeout=args.timeout,
        limit=args.limit,
        shuffle=args.shuffle,
        seed=args.seed,
    )

    ok_count = sum(1 for result in results if result.status == "ok")
    fail_count = len(results) - ok_count
    diff_failures = sum(
        1 for result in results if result.roundtrip_status in {"roundtrip_failed", "diff_failed"}
    )
    logger.info("Roundtrip complete: %d ok, %d failed", ok_count, fail_count)
    if args.roundtrip:
        logger.info("Roundtrip compare: %d with failures", diff_failures)

    if args.json_path:
        _write_json_report(results, Path(args.json_path))
        logger.info("Wrote JSON report to %s", args.json_path)

    if fail_count or diff_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
