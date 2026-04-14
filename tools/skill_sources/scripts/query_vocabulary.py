#!/usr/bin/env python
"""Look up entries in the oracle's three XML vocabularies.

Usage:

    python query_vocabulary.py filter wipe
    python query_vocabulary.py filter           # list all verified filters
    python query_vocabulary.py attrname style.visibility
    python query_vocabulary.py attrname         # list all 17 valid attrNames
    python query_vocabulary.py dead fill.opacity
    python query_vocabulary.py dead              # list all dead paths

Subcommand + optional substring:
    filter   — look up a filter from filter_vocabulary.xml
    attrname — look up an attrName from attrname_vocabulary.xml
    dead     — look up a dead path by id or attrName
"""

from __future__ import annotations

import argparse
import sys

from svg2ooxml.drawingml.animation.oracle import default_oracle


def _cmd_filter(query: str | None) -> int:
    oracle = default_oracle()
    vocab = oracle.filter_vocabulary()
    if query:
        matches = [e for e in vocab if query.lower() in e.value.lower()]
        if not matches:
            sys.stderr.write(f"No filter vocabulary entries match {query!r}\n")
            return 1
    else:
        matches = list(vocab)

    for entry in matches:
        print(f"{entry.value}")
        print(f"  description:   {entry.description}")
        ent = (
            f"preset {entry.entrance_preset_id}/{entry.entrance_preset_subtype}"
            if entry.entrance_preset_id and entry.entrance_preset_id > 0
            else "—"
        )
        ext = (
            f"preset {entry.exit_preset_id}/{entry.exit_preset_subtype}"
            if entry.exit_preset_id and entry.exit_preset_id > 0
            else "—"
        )
        print(f"  entrance:      {ent}")
        print(f"  exit:          {ext}")
        print(f"  verification:  {entry.verification}")
        print()
    return 0


def _cmd_attrname(query: str | None) -> int:
    oracle = default_oracle()
    vocab = oracle.attrname_vocabulary()
    if query:
        matches = [e for e in vocab if query.lower() in e.value.lower()]
        if not matches:
            sys.stderr.write(f"No attrName vocabulary entries match {query!r}\n")
            sys.stderr.write(
                "(If your attribute is missing, check 'query_vocabulary.py dead' "
                "— it may be a known dead path.)\n"
            )
            return 1
    else:
        matches = list(vocab)

    for entry in matches:
        print(f"{entry.value}")
        print(f"  category:      {entry.category}")
        print(f"  scope:         {entry.scope}")
        print(f"  description:   {entry.description}")
        print(f"  used_by:       {entry.used_by}")
        print(f"  verification:  {entry.verification}")
        print()
    return 0


def _cmd_dead(query: str | None) -> int:
    oracle = default_oracle()
    dps = oracle.dead_paths()
    if query:
        q = query.lower()
        matches = [
            dp
            for dp in dps
            if q in dp.id.lower()
            or any(q in v.lower() for v in dp.attribute_values)
        ]
        if not matches:
            sys.stderr.write(f"No dead path entries match {query!r}\n")
            return 1
    else:
        matches = list(dps)

    for dp in matches:
        attrs = ", ".join(
            f"{k}={v!r}"
            for k, v in zip(dp.attribute_names, dp.attribute_values)
        )
        print(f"{dp.id}")
        print(f"  element:       {dp.element}")
        print(f"  attributes:    {attrs}")
        if dp.context:
            print(f"  context:       {dp.context}")
        print(f"  verdict:       {dp.verdict}")
        print(f"  replacement:   {dp.replacement_slot}")
        print(f"  note:          {dp.replacement_note}")
        print()
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)
    for cmd in ("filter", "attrname", "dead"):
        sp = sub.add_parser(cmd)
        sp.add_argument(
            "query",
            nargs="?",
            help=f"optional substring filter (list all if omitted)",
        )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "filter":
        return _cmd_filter(args.query)
    if args.command == "attrname":
        return _cmd_attrname(args.query)
    if args.command == "dead":
        return _cmd_dead(args.query)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
