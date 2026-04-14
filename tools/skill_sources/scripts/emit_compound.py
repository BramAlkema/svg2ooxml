#!/usr/bin/env python
"""Emit a compound <p:par> containing multiple behavior fragments.

Wraps ``AnimationOracle.instantiate_compound`` with a CLI. All behaviors
fire simultaneously on the outer click trigger — under the hood this is
one ``<p:cTn>`` with every fragment's children appended as siblings in
its ``childTnLst``. The structure is empirically verified to play in
Microsoft PowerPoint.

Usage:

    python emit_compound.py --shape 2 --duration 3000 --par-id 5 \\
        --behaviors '[
          {"name": "transparency", "tokens": {"SET_BEHAVIOR_ID": 10,
              "EFFECT_BEHAVIOR_ID": 11, "TARGET_OPACITY": "0.5"}},
          {"name": "rotate", "tokens": {"BEHAVIOR_ID": 20,
              "ROTATION_BY": "21600000"}},
          {"name": "motion", "tokens": {"BEHAVIOR_ID": 30,
              "PATH_DATA": "M 0 0 L 0.2 0.1 E"}}
        ]'

The behaviors argument is a JSON list of ``{"name": str, "tokens": dict}``
objects. See references/compound_api.md for the full fragment catalog.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lxml import etree

from svg2ooxml.drawingml.animation.oracle import (
    BehaviorFragment,
    OracleSlotError,
    default_oracle,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--shape",
        required=True,
        help="Target shape spid (e.g. '2').",
    )
    p.add_argument(
        "--duration",
        type=int,
        default=3000,
        help="Compound duration in milliseconds (default: 3000).",
    )
    p.add_argument(
        "--delay",
        type=int,
        default=0,
        help="Start delay in milliseconds (default: 0).",
    )
    p.add_argument(
        "--par-id",
        type=int,
        default=5,
        help="Outer cTn/par id (default: 5).",
    )
    p.add_argument(
        "--behaviors",
        required=True,
        help='JSON list of {"name": ..., "tokens": {...}} objects.',
    )
    p.add_argument(
        "--behaviors-file",
        type=Path,
        help="Alternative to --behaviors: read the JSON list from a file.",
    )
    return p.parse_args(argv)


def _load_behaviors(arg_value: str, arg_file: Path | None) -> list[BehaviorFragment]:
    if arg_file is not None:
        raw = arg_file.read_text(encoding="utf-8")
    else:
        raw = arg_value
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("behaviors must be a JSON list of fragment specs")
    fragments: list[BehaviorFragment] = []
    for entry in data:
        if not isinstance(entry, dict) or "name" not in entry:
            raise ValueError(
                f"behavior entry missing 'name' field: {entry!r}"
            )
        fragments.append(
            BehaviorFragment(name=entry["name"], tokens=entry.get("tokens", {}))
        )
    return fragments


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        behaviors = _load_behaviors(args.behaviors, args.behaviors_file)
    except (ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"ERROR parsing --behaviors: {exc}\n")
        return 2

    oracle = default_oracle()
    try:
        par = oracle.instantiate_compound(
            shape_id=args.shape,
            par_id=args.par_id,
            duration_ms=args.duration,
            delay_ms=args.delay,
            behaviors=behaviors,
        )
    except OracleSlotError as exc:
        sys.stderr.write(f"ERROR instantiating compound: {exc}\n")
        sys.stderr.write(
            "\nAvailable behavior fragments (under oracle/emph/behaviors/):\n"
        )
        fragments_dir = oracle.root / "emph" / "behaviors"
        if fragments_dir.is_dir():
            for f in sorted(fragments_dir.glob("*.xml")):
                sys.stderr.write(f"  - {f.stem}\n")
        return 1
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2

    sys.stdout.write(
        etree.tostring(par, pretty_print=True, encoding="unicode")
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
