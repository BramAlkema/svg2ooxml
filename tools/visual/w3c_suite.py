#!/usr/bin/env python3
"""Run a curated set of SVG → PPTX comparisons for W3C fixtures."""

from __future__ import annotations

import argparse
import json
import logging
import urllib.request
from pathlib import Path
from typing import Iterable, TypedDict

from tests.visual.helpers.builder import PptxBuilder
from tests.visual.helpers.diff import ImageDiff, ImageDiffError
from tests.visual.helpers.golden import GoldenRepository
from tools.visual.renderer import VisualRendererError, default_renderer

logger = logging.getLogger("w3c_suite")


SCENARIOS = {
    "struct-use-10-f": Path("tests/svg/struct-use-10-f.svg"),
    "simple-rect": Path("tests/visual/fixtures/simple_rect.svg"),
}


class ExportOptions(TypedDict):
    service_url: str
    auth_token: str | None
    output_format: str


def _resolve_scenarios(names: Iterable[str] | None) -> list[tuple[str, Path]]:
    if not names:
        return [(name, path) for name, path in SCENARIOS.items()]
    resolved: list[tuple[str, Path]] = []
    for name in names:
        svg = SCENARIOS.get(name)
        if svg is None:
            raise SystemExit(f"Unknown scenario '{name}'. Available: {', '.join(SCENARIOS)}")
        resolved.append((name, svg))
    return resolved


def run_suite(names: Iterable[str] | None, output_dir: Path, export: ExportOptions | None = None) -> None:
    renderer = default_renderer()
    if not renderer.available:
        raise SystemExit(
            "LibreOffice (soffice) is not available. Install it or set "
            "SVG2OOXML_SOFFICE_PATH before running the suite."
        )

    builder = PptxBuilder()
    golden = GoldenRepository(Path("tests/visual/golden"))
    diff = ImageDiff()

    for name, svg_path in _resolve_scenarios(names):
        logger.info("Running scenario %s", name)
        if not svg_path.exists():
            logger.warning("Skipping %s – SVG missing: %s", name, svg_path)
            continue

        scenario_dir = output_dir / name
        render_dir = scenario_dir / "render"
        diff_dir = scenario_dir / "diff"
        render_dir.mkdir(parents=True, exist_ok=True)
        diff_dir.mkdir(parents=True, exist_ok=True)

        pptx_path = scenario_dir / "presentation.pptx"
        svg_text = svg_path.read_text(encoding="utf-8")
        build_result = builder.build_from_svg(svg_text, pptx_path)
        logger.info("%s: generated PPTX (%d slide(s))", name, build_result.slide_count)

        try:
            rendered = renderer.render(build_result.pptx_path, render_dir)
        except VisualRendererError as exc:
            logger.warning("%s: rendering failed – %s", name, exc)
            continue
        logger.info("%s: rendered %d slide image(s)", name, len(rendered.images))

        if export is not None:
            try:
                job_payload = _submit_export_job(
                    svg_text=svg_text,
                    scenario_name=name,
                    export_options=export,
                )
            except Exception as exc:  # pragma: no cover - network failure
                logger.warning("%s: failed to submit export job – %s", name, exc)
            else:
                logger.info("%s: submitted export job %s", name, job_payload.get("job_id"))

        baseline_dir = golden.path_for(Path("w3c") / name)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenarios", nargs="*", help="Scenario names to run")
    parser.add_argument(
        "--output",
        default="reports/visual/w3c",
        help="Directory to write generated artefacts",
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
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if not args.verbose else logging.DEBUG)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    export_opts: ExportOptions | None = None
    if args.export_service_url:
        export_opts = {
            "service_url": args.export_service_url.rstrip("/"),
            "auth_token": args.auth_token,
            "output_format": args.export_format,
        }

    run_suite(args.scenarios, output_dir, export=export_opts)


def _submit_export_job(*, svg_text: str, scenario_name: str, export_options: ExportOptions) -> dict[str, object]:
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
        "figma_file_id": f"w3c-{scenario_name}",
        "figma_file_name": f"W3C {scenario_name}",
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
    from xml.etree import ElementTree as ET

    root = ET.fromstring(svg_text)
    view_box_tokens = root.attrib.get("viewBox", "").split()
    width = _parse_dimension(root.attrib.get("width", ""), view_box_tokens, 2)
    height = _parse_dimension(root.attrib.get("height", ""), view_box_tokens, 3)
    return width or 1.0, height or 1.0


def _parse_dimension(token: str, view_box_tokens: list[str], fallback_index: int) -> float | None:
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


if __name__ == "__main__":
    main()
