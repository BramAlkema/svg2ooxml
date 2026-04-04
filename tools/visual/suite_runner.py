#!/usr/bin/env python3
"""Shared runner for curated visual comparison suites."""

from __future__ import annotations

import argparse
import json
import logging
import os
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Iterable, TypedDict

from tools.visual.browser_renderer import BrowserRenderError
from tools.visual.diff import ImageDiffError, VisualDiffer
from tools.visual.renderer import (
    LibreOfficeRenderer,
    PowerPointRenderer,
    VisualRendererError,
    default_renderer,
)
from tools.visual.stack import default_visual_stack

logger = logging.getLogger("visual_suite")


class ExportOptions(TypedDict):
    service_url: str
    auth_token: str | None
    output_format: str


def resolve_scenarios(
    scenarios: Mapping[str, Path],
    names: Iterable[str] | None,
) -> list[tuple[str, Path]]:
    """Resolve suite scenario names to SVG paths in declaration order."""
    if not names:
        return [(name, path) for name, path in scenarios.items()]
    resolved: list[tuple[str, Path]] = []
    for name in names:
        svg = scenarios.get(name)
        if svg is None:
            raise SystemExit(
                f"Unknown scenario '{name}'. Available: {', '.join(scenarios)}"
            )
        resolved.append((name, svg))
    return resolved


def run_suite(
    scenarios: Mapping[str, Path],
    *,
    golden_namespace: str,
    names: Iterable[str] | None,
    output_dir: Path,
    export: ExportOptions | None = None,
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
) -> None:
    if renderer_name == "powerpoint":
        renderer = PowerPointRenderer(
            backend=powerpoint_backend,
            delay=powerpoint_delay,
            slideshow_delay=powerpoint_slideshow_delay,
            open_timeout=powerpoint_open_timeout,
            capture_timeout=powerpoint_capture_timeout,
            use_keys=powerpoint_use_keys,
            allow_reopen=not powerpoint_no_reopen,
        )
        if not renderer.available:
            raise SystemExit("PowerPoint rendering is only available on macOS.")
    else:
        if soffice_path:
            renderer = LibreOfficeRenderer(
                soffice_path=soffice_path,
                user_installation=soffice_profile,
            )
        else:
            renderer = default_renderer(user_installation=soffice_profile)
        if not renderer.available:
            raise SystemExit(
                "LibreOffice (soffice) is not available. Install it or set "
                "SVG2OOXML_SOFFICE_PATH before running the suite."
            )

    stack = default_visual_stack()
    builder = stack.builder
    golden = stack.golden
    diff = stack.diff
    browser_renderer = stack.browser_renderer

    for name, svg_path in resolve_scenarios(scenarios, names):
        logger.info("Running scenario %s", name)
        if not svg_path.exists():
            logger.warning("Skipping %s – SVG missing: %s", name, svg_path)
            continue

        scenario_dir = output_dir / name
        render_dir = scenario_dir / "render"
        diff_dir = scenario_dir / "diff"
        browser_dir = scenario_dir / "browser"
        render_dir.mkdir(parents=True, exist_ok=True)
        diff_dir.mkdir(parents=True, exist_ok=True)
        browser_dir.mkdir(parents=True, exist_ok=True)
        for stale in render_dir.glob("*.png"):
            stale.unlink()
        for stale in diff_dir.glob("*.png"):
            stale.unlink()
        for stale in browser_dir.glob("*.png"):
            stale.unlink()

        pptx_path = scenario_dir / "presentation.pptx"
        svg_text = svg_path.read_text(encoding="utf-8")
        build_result = builder.build_from_svg(svg_text, pptx_path, source_path=svg_path)
        logger.info("%s: generated PPTX (%d slide(s))", name, build_result.slide_count)

        try:
            rendered = renderer.render(build_result.pptx_path, render_dir)
        except VisualRendererError as exc:
            logger.error("%s: rendering failed – %s", name, exc)
            raise SystemExit(1) from exc
        logger.info("%s: rendered %d slide image(s)", name, len(rendered.images))

        if export is not None:
            try:
                job_payload = _submit_export_job(
                    svg_text=svg_text,
                    scenario_name=f"{golden_namespace}-{name}",
                    export_options=export,
                )
            except Exception as exc:  # pragma: no cover - network failure
                logger.warning("%s: failed to submit export job – %s", name, exc)
            else:
                logger.info(
                    "%s: submitted export job %s", name, job_payload.get("job_id")
                )

        if os.getenv("SVG2OOXML_VISUAL_BROWSER_COMPARE") == "1":
            if not browser_renderer or not browser_renderer.available:
                logger.warning(
                    "%s: Playwright browser renderer is not available.", name
                )
            else:
                browser_threshold = float(
                    os.getenv("SVG2OOXML_VISUAL_BROWSER_THRESHOLD", "0.90")
                )
                browser_path = browser_dir / f"{name}.png"
                try:
                    browser_renderer.render_svg(
                        svg_text,
                        browser_path,
                        source_path=svg_path,
                    )
                except BrowserRenderError as exc:
                    logger.warning("%s: browser render failed – %s", name, exc)
                else:
                    if not rendered.images:
                        logger.warning(
                            "%s: no rendered slides to compare for browser parity.",
                            name,
                        )
                    else:
                        from PIL import Image

                        actual_path = Path(rendered.images[0])
                        if len(rendered.images) > 1:
                            logger.warning(
                                "%s: multiple rendered slides; comparing only %s",
                                name,
                                actual_path.name,
                            )
                        browser_img = Image.open(browser_path)
                        actual_img = Image.open(actual_path)
                        differ = VisualDiffer(threshold=browser_threshold)
                        result = differ.compare(
                            browser_img, actual_img, generate_diff=True
                        )
                        if not result.passed:
                            diff_path = diff_dir / f"{name}_browser_diff.png"
                            result.save_diff(diff_path)
                            logger.error(
                                "%s: browser parity failed (SSIM %.4f < %.2f, diff %.2f%%). Diff: %s",
                                name,
                                result.ssim_score,
                                browser_threshold,
                                result.pixel_diff_percentage,
                                diff_path,
                            )

        baseline_dir = golden.path_for(Path(golden_namespace) / name)
        if not baseline_dir.exists() or not any(baseline_dir.glob("*.png")):
            logger.warning(
                "%s: baseline images not found at %s. "
                "Run `python -m tools.visual.update_baselines %s` once baselines are prepared.",
                name,
                baseline_dir,
                name,
            )
            continue

        generated_images = list(render_dir.glob("*.png"))
        baseline_images = sorted(baseline_dir.glob("*.png"))
        if len(generated_images) == 1 and len(baseline_images) == 1:
            generated_image = generated_images[0]
            baseline_name = baseline_images[0].name
            if generated_image.name != baseline_name:
                target_path = render_dir / baseline_name
                target_path.write_bytes(generated_image.read_bytes())
                generated_image.unlink()

        try:
            diff.compare_directories(render_dir, baseline_dir, diff_dir=diff_dir)
            logger.info("%s: diff clean", name)
        except ImageDiffError as exc:
            logger.error("%s: visual diff mismatch – %s", name, exc)


def run_cli(
    *,
    description: str,
    scenarios: Mapping[str, Path],
    golden_namespace: str,
    default_output: str,
) -> None:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("scenarios", nargs="*", help="Scenario names to run")
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Directory to write generated artefacts "
            f"(default: {default_output} for soffice, "
            f"{_powerpoint_default_output(default_output)} for PowerPoint)."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--export-service-url",
        default=None,
        help="Optional Cloud Run export API base URL (e.g. https://service.run.app)",
    )
    parser.add_argument(
        "--auth-token",
        default=None,
        help="Bearer token for the export API (omit to send unauthenticated requests)",
    )
    parser.add_argument(
        "--export-format",
        choices=["pptx", "slides"],
        default="slides",
        help="Export format when posting scenarios to the API",
    )
    parser.add_argument(
        "--soffice",
        help="Explicit path to the soffice binary (defaults to PATH lookup).",
    )
    parser.add_argument(
        "--soffice-profile",
        help="LibreOffice user profile directory passed via -env:UserInstallation.",
    )
    parser.add_argument(
        "--renderer",
        choices=("soffice", "powerpoint"),
        default="soffice",
        help="PPTX renderer to use for visual diffs.",
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
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if not args.verbose else logging.DEBUG)
    output_dir = _resolve_cli_output_dir(
        output=args.output,
        renderer_name=args.renderer,
        default_output=default_output,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    export_opts: ExportOptions | None = None
    if args.export_service_url:
        export_opts = {
            "service_url": args.export_service_url.rstrip("/"),
            "auth_token": args.auth_token,
            "output_format": args.export_format,
        }

    run_suite(
        scenarios,
        golden_namespace=golden_namespace,
        names=args.scenarios,
        output_dir=output_dir,
        export=export_opts,
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
    )


def _powerpoint_default_output(default_output: str) -> str:
    output_path = Path(default_output)
    if output_path.parts[:2] == ("reports", "visual"):
        return str(Path("reports/visual/powerpoint").joinpath(*output_path.parts[2:]))
    return str(Path("reports/visual/powerpoint") / output_path)


def _resolve_cli_output_dir(
    *,
    output: str | None,
    renderer_name: str,
    default_output: str,
) -> Path:
    if output:
        return Path(output)
    if renderer_name == "powerpoint":
        return Path(_powerpoint_default_output(default_output))
    return Path(default_output)


def _submit_export_job(
    *,
    svg_text: str,
    scenario_name: str,
    export_options: ExportOptions,
) -> dict[str, object]:
    width, height = _extract_dimensions(svg_text)
    payload = {
        "frames": [
            {
                "name": scenario_name,
                "svg_content": svg_text,
                "width": width,
                "height": height,
            }
        ],
        "figma_file_id": scenario_name,
        "figma_file_name": scenario_name,
        "output_format": export_options["output_format"],
    }

    request = urllib.request.Request(
        f"{export_options['service_url']}/api/v1/export",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    token = export_options.get("auth_token")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def _extract_dimensions(svg_text: str) -> tuple[float, float]:
    from lxml import etree as ET

    root = ET.fromstring(svg_text.encode("utf-8"))
    view_box_tokens = root.attrib.get("viewBox", "").split()
    width = _parse_dimension(root.attrib.get("width", ""), view_box_tokens, 2)
    height = _parse_dimension(root.attrib.get("height", ""), view_box_tokens, 3)
    return width or 1.0, height or 1.0


def _parse_dimension(
    token: str,
    view_box_tokens: list[str],
    fallback_index: int,
) -> float | None:
    normalized = (token or "").strip()
    if normalized.endswith("%") and len(view_box_tokens) == 4:
        try:
            return float(view_box_tokens[fallback_index])
        except (ValueError, IndexError):
            return None
    if normalized:
        try:
            return float(normalized)
        except ValueError:
            return None
    if len(view_box_tokens) == 4:
        try:
            return float(view_box_tokens[fallback_index])
        except (ValueError, IndexError):
            return None
    return None


__all__ = [
    "ExportOptions",
    "resolve_scenarios",
    "run_cli",
    "run_suite",
]
