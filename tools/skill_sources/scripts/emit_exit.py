#!/usr/bin/env python
"""Emit an exit <p:par> using the exit/filter_effect oracle slot.

Mirror of emit_entrance.py for exit effects — same filter vocabulary,
but wrapped in the exit/filter_effect slot with animEffect + set child
order reversed (animEffect first, then the style.visibility hide at
SET_DELAY_MS = duration - 1).

Usage:

    python emit_exit.py --shape 2 --filter "wipe(up)" --duration 500

Use --list-filters to see the full vocabulary.
"""

from __future__ import annotations

import argparse
import sys

from lxml import etree

from svg2ooxml.drawingml.animation.oracle import (
    OracleSlotError,
    default_oracle,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--shape", help="Target shape spid.")
    p.add_argument("--filter", help="animEffect filter string.")
    p.add_argument("--duration", type=int, default=500, help="Duration ms (default 500).")
    p.add_argument("--delay", type=int, default=0, help="Start delay ms (default 0).")
    p.add_argument("--par-id", type=int, default=5, help="Outer par/cTn id (default 5).")
    p.add_argument(
        "--set-behavior-id",
        type=int,
        help="Override the style.visibility set behavior id.",
    )
    p.add_argument(
        "--effect-behavior-id",
        type=int,
        help="Override the animEffect behavior id.",
    )
    p.add_argument(
        "--set-delay-ms",
        type=int,
        help="Override when the visibility set fires (default: duration - 1).",
    )
    p.add_argument("--list-filters", action="store_true")
    return p.parse_args(argv)


def _print_filter_vocabulary(oracle) -> None:
    print("Exit filter vocabulary (from oracle/filter_vocabulary.xml):\n")
    print(f"{'filter':<28} {'preset':>10} {'verification':<22} description")
    print("-" * 100)
    for entry in oracle.filter_vocabulary():
        if entry.exit_preset_id is None or entry.exit_preset_id < 0:
            continue
        preset = f"{entry.exit_preset_id}/{entry.exit_preset_subtype}"
        print(
            f"{entry.value:<28} {preset:>10} {entry.verification:<22} "
            f"{entry.description}"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    oracle = default_oracle()

    if args.list_filters:
        _print_filter_vocabulary(oracle)
        return 0

    if not args.shape or not args.filter:
        sys.stderr.write("ERROR: --shape and --filter are required\n")
        sys.stderr.write("Use --list-filters to see valid filter strings.\n")
        return 2

    try:
        filter_entry = oracle.filter_entry(args.filter)
    except OracleSlotError:
        sys.stderr.write(
            f"ERROR: unknown filter {args.filter!r}. "
            f"Use --list-filters for the valid vocabulary.\n"
        )
        return 1

    if filter_entry.exit_preset_id is None or filter_entry.exit_preset_id < 0:
        sys.stderr.write(
            f"ERROR: filter {args.filter!r} is not valid as a standalone "
            f"exit effect.\n"
        )
        return 1

    set_bid = args.set_behavior_id or args.par_id + 1
    effect_bid = args.effect_behavior_id or args.par_id * 10 + 1
    set_delay = args.set_delay_ms if args.set_delay_ms is not None else max(1, args.duration - 1)

    par = oracle.instantiate(
        "exit/filter_effect",
        shape_id=args.shape,
        par_id=args.par_id,
        duration_ms=args.duration,
        delay_ms=args.delay,
        SET_BEHAVIOR_ID=set_bid,
        EFFECT_BEHAVIOR_ID=effect_bid,
        FILTER=args.filter,
        PRESET_ID=filter_entry.exit_preset_id,
        PRESET_SUBTYPE=filter_entry.exit_preset_subtype or 0,
        SET_DELAY_MS=set_delay,
    )

    sys.stdout.write(etree.tostring(par, pretty_print=True, encoding="unicode"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
