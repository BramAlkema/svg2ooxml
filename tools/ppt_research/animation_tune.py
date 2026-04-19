"""Interactive tune loop for hand-built animation samples.

Workflow::

    python -m tools.ppt_research.animation_tune fade_in

Opens Microsoft PowerPoint with the freshly built sample, records a
frame strip of slideshow playback, writes metrics, and drops into a REPL::

    [r] rebuild + reload + recapture
    [c] recapture without rebuilding
    [q] quit (closes the presentation, leaves PowerPoint running)

All captures land under ``reports/tune/<sample>/round-<NNN>/``.

One-shot (non-interactive) form::

    python -m tools.ppt_research.animation_tune fade_in --once
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

from tools.ppt_research.animation_samples import (
    available_samples,
    build_sample,
    load_sample,
)
from tools.ppt_research.pptx_session import PptxSession, PptxSessionError

logger = logging.getLogger("animation_tune")

REPORTS_ROOT = Path("reports/tune")
SAMPLES_ROOT = Path(".visual_tmp/samples")


# ---------------------------------------------------------------------- metrics


@dataclass
class FrameMetrics:
    frame: int
    filename: str
    non_background_pct: float
    delta_from_first_pct: float


def _load_rgb(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGB")
    return img


def _non_background_percent(img: Image.Image, *, tolerance: int = 12) -> float:
    """Percent of pixels that are not near-white (PowerPoint default background)."""
    from PIL import ImageChops

    white = Image.new("RGB", img.size, (255, 255, 255))
    diff = ImageChops.difference(img, white)
    # Any channel differing by > tolerance → foreground.
    bbox = diff.getbbox()  # cheap early exit when fully white
    if bbox is None:
        return 0.0
    gray = diff.convert("L").point(lambda v, t=tolerance: 255 if v > t else 0)
    histogram = gray.histogram()
    fg = histogram[255] if len(histogram) > 255 else 0
    total = img.size[0] * img.size[1]
    return (fg / total) * 100.0 if total else 0.0


def _mean_pixel_delta(base: Image.Image, other: Image.Image) -> float:
    """Mean absolute pixel difference (0–100)."""
    from PIL import ImageChops

    if base.size != other.size:
        other = other.resize(base.size)
    diff = ImageChops.difference(base, other).convert("L")
    histogram = diff.histogram()
    total = sum(histogram)
    if not total:
        return 0.0
    weighted = sum(value * count for value, count in enumerate(histogram))
    mean = weighted / total
    return (mean / 255.0) * 100.0


def compute_metrics(frames: Sequence[Path]) -> list[FrameMetrics]:
    if not frames:
        return []
    base = _load_rgb(frames[0])
    metrics: list[FrameMetrics] = []
    for index, path in enumerate(frames):
        img = _load_rgb(path)
        metrics.append(
            FrameMetrics(
                frame=index,
                filename=path.name,
                non_background_pct=round(_non_background_percent(img), 3),
                delta_from_first_pct=round(_mean_pixel_delta(base, img), 3),
            )
        )
    return metrics


# ------------------------------------------------------------------ contact sheet


def build_contact_sheet(frames: Sequence[Path], output_path: Path, *, cell_width: int = 320) -> Path:
    if not frames:
        raise ValueError("No frames to assemble")
    images = [_load_rgb(path) for path in frames]
    first = images[0]
    ratio = cell_width / first.size[0]
    cell_height = int(first.size[1] * ratio)
    strip = Image.new("RGB", (cell_width * len(images), cell_height), (32, 32, 36))
    for idx, img in enumerate(images):
        thumb = img.resize((cell_width, cell_height))
        strip.paste(thumb, (cell_width * idx, 0))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    strip.save(output_path)
    return output_path


# ---------------------------------------------------------------------- reports


def _next_round_dir(sample_name: str) -> Path:
    base = REPORTS_ROOT / sample_name
    base.mkdir(parents=True, exist_ok=True)
    existing = sorted(p for p in base.iterdir() if p.is_dir() and p.name.startswith("round-"))
    next_index = 1
    if existing:
        try:
            next_index = int(existing[-1].name.removeprefix("round-")) + 1
        except ValueError:
            next_index = len(existing) + 1
    round_dir = base / f"round-{next_index:03d}"
    round_dir.mkdir(parents=True, exist_ok=True)
    return round_dir


def _write_metrics(round_dir: Path, sample_name: str, metrics: list[FrameMetrics]) -> Path:
    payload = {
        "sample": sample_name,
        "frame_count": len(metrics),
        "frames": [asdict(m) for m in metrics],
        "summary": _summarize_metrics(metrics),
    }
    path = round_dir / "metrics.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _summarize_metrics(metrics: Sequence[FrameMetrics]) -> dict[str, float | bool]:
    if not metrics:
        return {
            "visible_any_frame": False,
            "visible_all_frames": False,
            "max_delta_from_first_pct": 0.0,
            "animation_detected": False,
        }
    non_bg = [m.non_background_pct for m in metrics]
    deltas = [m.delta_from_first_pct for m in metrics]
    max_delta = max(deltas) if deltas else 0.0
    return {
        "visible_any_frame": any(v > 0.1 for v in non_bg),
        "visible_all_frames": all(v > 0.1 for v in non_bg),
        "min_non_background_pct": round(min(non_bg), 3),
        "max_non_background_pct": round(max(non_bg), 3),
        "max_delta_from_first_pct": round(max_delta, 3),
        "animation_detected": max_delta > 0.2,
    }


def print_summary(sample_name: str, round_dir: Path, metrics: Sequence[FrameMetrics]) -> None:
    summary = _summarize_metrics(metrics)
    print()
    print(f"== {sample_name} :: {round_dir} ==")
    print(f"frames: {len(metrics)}")
    print(f"visible any frame : {summary['visible_any_frame']}")
    print(f"visible all frames: {summary['visible_all_frames']}")
    print(
        f"non-background %  : min={summary.get('min_non_background_pct')}"
        f"  max={summary.get('max_non_background_pct')}"
    )
    print(f"max delta vs t0   : {summary.get('max_delta_from_first_pct')}")
    print(f"animation detected: {summary['animation_detected']}")
    if metrics:
        print()
        print("  frame  visible%   delta%")
        for m in metrics:
            print(f"  {m.frame:>4d}   {m.non_background_pct:>7.2f}   {m.delta_from_first_pct:>6.2f}")
    print()


# ------------------------------------------------------------------------ loop


def run_round(
    session: PptxSession,
    sample_name: str,
    *,
    duration: float,
    fps: float,
    pre_advances: int = 0,
    trigger_advance: bool = True,
) -> tuple[Path, list[FrameMetrics]]:
    round_dir = _next_round_dir(sample_name)
    frames_dir = round_dir / "frames"
    frames = session.capture_animation(
        frames_dir,
        duration=duration,
        fps=fps,
        pre_advances=pre_advances,
        trigger_advance=trigger_advance,
    )
    metrics = compute_metrics(frames)
    _write_metrics(round_dir, sample_name, metrics)
    if frames:
        build_contact_sheet(frames, round_dir / "strip.png")
    return round_dir, metrics


def _rebuild(sample_name: str, output_path: Path) -> None:
    build_sample(sample_name, output_path)
    logger.info("Rebuilt sample %s → %s", sample_name, output_path)


# ------------------------------------------------------------------------ main


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", help=f"Sample name ({', '.join(available_samples())})")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Build, capture one round, write artefacts, exit (no REPL).",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=10.0,
        help="Capture frames per second (default: 10).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Override capture duration in seconds (default: sample's DURATION_S).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override sample PPTX output path (default: .visual_tmp/samples/<sample>.pptx).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.sample not in available_samples():
        print(
            f"Unknown sample '{args.sample}'. Available: {', '.join(available_samples())}",
            file=sys.stderr,
        )
        return 2

    module = load_sample(args.sample)
    duration = float(args.duration if args.duration is not None else module.DURATION_S)
    pre_advances = int(getattr(module, "PRE_ADVANCES", 0))
    trigger_advance = bool(getattr(module, "TRIGGER_ADVANCE", True))
    output_path = (args.output or SAMPLES_ROOT / f"{args.sample}.pptx").resolve()

    _rebuild(args.sample, output_path)

    session = PptxSession(output_path)
    try:
        session.open()
    except PptxSessionError as exc:
        print(f"Failed to open PowerPoint session: {exc}", file=sys.stderr)
        return 1

    try:
        round_dir, metrics = run_round(session, args.sample, duration=duration, fps=args.fps, pre_advances=pre_advances, trigger_advance=trigger_advance)
        print_summary(args.sample, round_dir, metrics)

        if args.once:
            return 0

        while True:
            try:
                choice = input("[r]ebuild+reload+recapture  [c]apture  [q]uit > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if choice in ("q", "quit", "exit"):
                break
            if choice in ("c", "capture"):
                round_dir, metrics = run_round(
                    session,
                    args.sample,
                    duration=duration,
                    fps=args.fps,
                    pre_advances=pre_advances,
                    trigger_advance=trigger_advance,
                )
                print_summary(args.sample, round_dir, metrics)
                continue
            if choice in ("r", "rebuild", "reload", ""):
                start = time.time()
                _rebuild(args.sample, output_path)
                session.reload()
                round_dir, metrics = run_round(
                    session,
                    args.sample,
                    duration=duration,
                    fps=args.fps,
                    pre_advances=pre_advances,
                    trigger_advance=trigger_advance,
                )
                elapsed = time.time() - start
                print(f"(round cycle: {elapsed:.1f}s)")
                print_summary(args.sample, round_dir, metrics)
                continue
            print(f"Unknown choice: {choice!r}")
    finally:
        session.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
