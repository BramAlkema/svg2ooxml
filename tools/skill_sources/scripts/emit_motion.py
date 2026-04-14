#!/usr/bin/env python
"""Emit a motion-path <p:par> using the path/motion oracle slot.

Usage:

    python emit_motion.py --shape 2 \\
        --path "M 0 0 L 0.25 0.5 E" \\
        --duration 2000

PATH_DATA is a PowerPoint motion-path string in slide-relative
coordinates (M/L/C commands with 0..1 coordinates, terminated by E).
"""

from __future__ import annotations

import argparse
import sys

from lxml import etree

from svg2ooxml.drawingml.animation.oracle import default_oracle


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--shape", required=True, help="Target shape spid.")
    p.add_argument("--path", required=True, help="PPT motion path string (e.g. 'M 0 0 L 0.2 0.1 E').")
    p.add_argument("--duration", type=int, default=2000, help="Duration ms (default 2000).")
    p.add_argument("--delay", type=int, default=0, help="Start delay ms (default 0).")
    p.add_argument("--par-id", type=int, default=5, help="Outer par/cTn id (default 5).")
    p.add_argument("--behavior-id", type=int, help="Override the inner cBhvr cTn id.")
    p.add_argument(
        "--node-type",
        default="clickEffect",
        choices=["clickEffect", "withEffect", "afterEffect"],
        help="Outer cTn nodeType (default clickEffect).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    oracle = default_oracle()

    behavior_id = args.behavior_id or args.par_id * 10 + 1

    par = oracle.instantiate(
        "path/motion",
        shape_id=args.shape,
        par_id=args.par_id,
        duration_ms=args.duration,
        delay_ms=args.delay,
        BEHAVIOR_ID=behavior_id,
        PATH_DATA=args.path,
        NODE_TYPE=args.node_type,
        INNER_FILL="hold",
    )

    sys.stdout.write(etree.tostring(par, pretty_print=True, encoding="unicode"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
