"""CLI for PowerPoint visual capture."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.ppt_research.powerpoint_capture import (
    capture_live_animation,
    capture_pptx_slideshow,
    capture_pptx_slideshow_all,
    capture_pptx_window,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture PowerPoint window screenshot."
    )
    parser.add_argument("pptx", type=Path, help="Path to the PPTX file to open.")
    parser.add_argument(
        "output",
        type=Path,
        help="Output PNG path (window/slideshow) or output directory (slideshow-all/live).",
    )
    parser.add_argument(
        "--mode",
        choices=("window", "slideshow", "slideshow-all", "live"),
        default="window",
        help="Capture mode: live records a single slide's animation.",
    )
    parser.add_argument(
        "--duration", type=float, default=5.0, help="Duration for live recording."
    )
    parser.add_argument(
        "--fps", type=float, default=10.0, help="FPS for live recording."
    )
    parser.add_argument(
        "--delay", type=float, default=1.5, help="Delay after opening (seconds)."
    )
    parser.add_argument(
        "--slideshow-delay",
        type=float,
        default=1.0,
        help="Delay after slideshow starts (seconds).",
    )
    parser.add_argument(
        "--slide-delay",
        type=float,
        default=0.15,
        help="Delay between slides (seconds) for slideshow-all.",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "screencapture", "sckit"),
        default="auto",
        help="Capture backend: auto uses ScreenCaptureKit when available.",
    )
    parser.add_argument(
        "--capture-timeout",
        type=float,
        default=5.0,
        help="Max seconds to wait for ScreenCaptureKit frame capture.",
    )
    parser.add_argument(
        "--open-timeout",
        type=float,
        default=120.0,
        help="Max seconds to wait for PowerPoint to open/repair the file.",
    )
    parser.add_argument(
        "--no-reopen",
        action="store_true",
        help="Disable periodic reopen attempts while waiting for slides.",
    )
    parser.add_argument(
        "--no-keys",
        action="store_true",
        help="Disable keystroke fallbacks; only click visible buttons.",
    )
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Leave the slideshow running after capture.",
    )
    args = parser.parse_args()

    try:
        if args.mode == "live":
            capture_live_animation(
                args.pptx,
                args.output,
                args.duration,
                fps=args.fps,
                delay=args.delay,
                slideshow_delay=args.slideshow_delay,
                open_timeout=args.open_timeout,
                capture_timeout=args.capture_timeout,
                use_keys=not args.no_keys,
                allow_reopen=not args.no_reopen,
                backend=args.backend,
            )
        elif args.mode == "slideshow":
            capture_pptx_slideshow(
                args.pptx,
                args.output,
                args.delay,
                args.slideshow_delay,
                args.open_timeout,
                args.capture_timeout,
                exit_after=not args.keep_open,
                use_keys=not args.no_keys,
                allow_reopen=not args.no_reopen,
                backend=args.backend,
            )
        elif args.mode == "slideshow-all":
            capture_pptx_slideshow_all(
                args.pptx,
                args.output,
                args.delay,
                args.slideshow_delay,
                args.slide_delay,
                args.open_timeout,
                args.capture_timeout,
                exit_after=not args.keep_open,
                use_keys=not args.no_keys,
                allow_reopen=not args.no_reopen,
                backend=args.backend,
            )
        else:
            capture_pptx_window(
                args.pptx,
                args.output,
                args.delay,
                backend=args.backend,
                capture_timeout=args.capture_timeout,
            )
    except Exception as exc:
        print(f"PowerPoint capture failed: {exc}", file=sys.stderr)
        return 1
    return 0




if __name__ == "__main__":
    raise SystemExit(main())
