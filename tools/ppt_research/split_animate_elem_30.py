#!/usr/bin/env python3
"""Split animate-elem-30-t into one animated element per PPTX/capture."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from lxml import etree as ET
from PIL import Image, ImageDraw, ImageFont, ImageOps

from tools.ppt_research.w3c_proof_deck import (
    _build_montage,
    _detect_animation_duration,
    _make_placeholder,
    _save_apng,
)
from tools.visual.builder import PptxBuilder, VisualBuildError
from tools.visual.renderer import PowerPointRenderer, VisualRendererError

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


@dataclass(frozen=True)
class CaseSpec:
    key: str
    label: str
    target_id: str


@dataclass
class CaseArtifacts:
    key: str
    label: str
    target_id: str
    svg_path: str
    pptx_path: str | None
    preview_path: str
    apng_path: str | None
    status: str
    error: str | None = None


CASES: tuple[CaseSpec, ...] = (
    CaseSpec("01-line", "Line", "lineID"),
    CaseSpec("02-rect", "Rectangle", "rectID"),
    CaseSpec("03-circle", "Circle", "circleID"),
    CaseSpec("04-polyline", "Polyline", "polylineID"),
    CaseSpec("05-polygon", "Polygon", "polygonID"),
    CaseSpec("06-image", "Image", "imageID"),
)
TARGET_IDS = {case.target_id for case in CASES}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("tests/svg/animate-elem-30-t.svg"),
        help="Source W3C SVG fixture.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory. Defaults to reports/visual/animate-elem-30-solo-<timestamp>.",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=4.0,
        help="PowerPoint live-capture frame rate.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Override capture duration in seconds. Defaults to the detected SVG duration.",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=5.0,
        help="Upper bound when auto-detecting animation duration.",
    )
    parser.add_argument(
        "--montage-frames",
        type=int,
        default=6,
        help="Maximum frames to include in preview montages.",
    )
    parser.add_argument(
        "--skip-capture",
        action="store_true",
        help="Build the isolated PPTX files but do not capture live PowerPoint previews.",
    )
    return parser.parse_args()


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(f"reports/visual/animate-elem-30-solo-{stamp}")


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _href_target_id(element: ET._Element) -> str | None:
    href = element.get(f"{{{XLINK_NS}}}href") or element.get("href")
    if not href or not href.startswith("#"):
        return None
    return href[1:]


def _iter_elements(root: ET._Element) -> Iterable[ET._Element]:
    for element in root.iter():
        if isinstance(element.tag, str):
            yield element


def _defs_target_ids(defs_element: ET._Element) -> set[str]:
    ids: set[str] = set()
    if defs_element.get("id") in TARGET_IDS:
        ids.add(str(defs_element.get("id")))
    for child in _iter_elements(defs_element):
        child_id = child.get("id")
        if child_id in TARGET_IDS:
            ids.add(str(child_id))
    return ids


def _is_target_use(element: ET._Element) -> bool:
    return _local_name(element.tag) == "use" and _href_target_id(element) in TARGET_IDS


def _split_svg(svg_text: str, case: CaseSpec) -> str:
    parser = ET.XMLParser(remove_blank_text=False, recover=True)
    root = ET.fromstring(svg_text.encode("utf-8"), parser)

    for defs_element in list(root.xpath(".//*[local-name()='defs']")):
        target_ids = _defs_target_ids(defs_element)
        if target_ids and case.target_id not in target_ids:
            parent = defs_element.getparent()
            if parent is not None:
                parent.remove(defs_element)

    for use_element in list(root.xpath(".//*[local-name()='use']")):
        if not _is_target_use(use_element):
            continue
        if _href_target_id(use_element) == case.target_id:
            continue
        parent = use_element.getparent()
        if parent is not None:
            parent.remove(use_element)

    title_elements = root.xpath(".//*[local-name()='title' and @id='test-title']")
    if title_elements:
        title_elements[0].text = f"animate-elem-30-t {case.label}"

    return ET.tostring(
        root,
        encoding="unicode",
        pretty_print=True,
    )


def _rel(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _build_overview(results: list[CaseArtifacts], output_path: Path) -> Path:
    preview_paths = [output_path.parent / result.preview_path for result in results if result.preview_path]
    if not preview_paths:
        raise ValueError("No previews available for overview.")

    thumbs: list[tuple[str, Image.Image]] = []
    try:
        for result in results:
            preview = output_path.parent / result.preview_path
            image = Image.open(preview).convert("RGB")
            thumbs.append((result.label, image))

        thumb_box = (360, 240)
        columns = 2
        rows = (len(thumbs) + columns - 1) // columns
        padding = 16
        header_height = 26
        canvas_width = padding + columns * (thumb_box[0] + padding)
        canvas_height = padding + rows * (thumb_box[1] + header_height + padding)
        canvas = Image.new("RGB", (canvas_width, canvas_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()

        for index, (label, image) in enumerate(thumbs):
            row = index // columns
            column = index % columns
            left = padding + column * (thumb_box[0] + padding)
            top = padding + row * (thumb_box[1] + header_height + padding)
            thumb = ImageOps.contain(image, thumb_box)
            thumb_left = left + (thumb_box[0] - thumb.width) // 2
            canvas.paste(thumb, (thumb_left, top + header_height))
            draw.text((left + 4, top + 4), label, font=font, fill=(0, 0, 0))
            draw.rectangle(
                (left, top + header_height, left + thumb_box[0], top + header_height + thumb_box[1]),
                outline=(180, 180, 180),
                width=1,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path)
        canvas.close()
        return output_path
    finally:
        for _, image in thumbs:
            image.close()


def _capture_case(
    renderer: PowerPointRenderer,
    case: CaseSpec,
    pptx_path: Path,
    case_dir: Path,
    *,
    duration: float,
    fps: float,
    montage_frames: int,
    root_output_dir: Path,
) -> CaseArtifacts:
    try:
        frame_paths = renderer.capture_animation(
            pptx_path,
            case_dir / "frames",
            duration=duration,
            fps=fps,
        )
        preview_path = _build_montage(
            frame_paths,
            case_dir / "preview.png",
            fps=fps,
            max_frames=montage_frames,
        )
        apng_path = _save_apng(frame_paths, case_dir / "preview.apng", fps=fps)
        return CaseArtifacts(
            key=case.key,
            label=case.label,
            target_id=case.target_id,
            svg_path=_rel(case_dir / "fixture.svg", root_output_dir) or "",
            pptx_path=_rel(pptx_path, root_output_dir),
            preview_path=_rel(preview_path, root_output_dir) or str(preview_path),
            apng_path=_rel(apng_path, root_output_dir),
            status="ok",
        )
    except (OSError, RuntimeError, ValueError, VisualRendererError) as exc:
        placeholder = _make_placeholder(
            case_dir / "preview.png",
            title=f"{case.label} capture failed",
            detail=str(exc),
        )
        return CaseArtifacts(
            key=case.key,
            label=case.label,
            target_id=case.target_id,
            svg_path=_rel(case_dir / "fixture.svg", root_output_dir) or "",
            pptx_path=_rel(pptx_path, root_output_dir) if pptx_path.exists() else None,
            preview_path=_rel(placeholder, root_output_dir) or str(placeholder),
            apng_path=None,
            status="error",
            error=str(exc),
        )


def main() -> int:
    args = _parse_args()
    output_dir = args.output or _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    svg_path: Path = args.input
    svg_text = svg_path.read_text(encoding="utf-8")
    duration = args.duration
    if duration is None:
        duration = _detect_animation_duration(
            svg_text,
            default_duration=3.0,
            max_duration=args.max_duration,
        )

    builder = PptxBuilder(slide_size_mode="same", fidelity_tier="direct")
    renderer = None if args.skip_capture else PowerPointRenderer()

    results: list[CaseArtifacts] = []
    for case in CASES:
        case_dir = output_dir / case.key
        case_dir.mkdir(parents=True, exist_ok=True)
        split_svg = _split_svg(svg_text, case)
        fixture_path = case_dir / "fixture.svg"
        fixture_path.write_text(split_svg, encoding="utf-8")

        pptx_path = case_dir / "presentation.pptx"
        try:
            builder.build_from_svg(split_svg, pptx_path, source_path=fixture_path)
        except (OSError, RuntimeError, ValueError, VisualBuildError) as exc:
            placeholder = _make_placeholder(
                case_dir / "preview.png",
                title=f"{case.label} build failed",
                detail=str(exc),
            )
            results.append(
                CaseArtifacts(
                    key=case.key,
                    label=case.label,
                    target_id=case.target_id,
                    svg_path=_rel(fixture_path, output_dir) or str(fixture_path),
                    pptx_path=None,
                    preview_path=_rel(placeholder, output_dir) or str(placeholder),
                    apng_path=None,
                    status="error",
                    error=str(exc),
                )
            )
            continue

        if renderer is None:
            placeholder = _make_placeholder(
                case_dir / "preview.png",
                title=f"{case.label} capture skipped",
                detail="Run again without --skip-capture to generate live PowerPoint frames.",
            )
            results.append(
                CaseArtifacts(
                    key=case.key,
                    label=case.label,
                    target_id=case.target_id,
                    svg_path=_rel(fixture_path, output_dir) or str(fixture_path),
                    pptx_path=_rel(pptx_path, output_dir),
                    preview_path=_rel(placeholder, output_dir) or str(placeholder),
                    apng_path=None,
                    status="skipped",
                )
            )
            continue

        results.append(
            _capture_case(
                renderer,
                case,
                pptx_path,
                case_dir,
                duration=duration,
                fps=args.fps,
                montage_frames=args.montage_frames,
                root_output_dir=output_dir,
            )
        )

    overview_path = _build_overview(results, output_dir / "overview.png")
    manifest_path = output_dir / "manifest.json"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_svg": str(svg_path),
        "duration": duration,
        "fps": args.fps,
        "cases": [asdict(result) for result in results],
        "overview_path": _rel(overview_path, output_dir),
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"wrote {manifest_path}")
    for result in results:
        detail = f" status={result.status}"
        if result.error:
            detail += f" error={result.error}"
        print(f"{result.key} {result.label}: {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
