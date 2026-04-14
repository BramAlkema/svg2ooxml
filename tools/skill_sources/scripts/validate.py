#!/usr/bin/env python
"""Validate PowerPoint animation timing XML against the dead_paths SSOT.

Reads XML from stdin or a --file argument, walks every element, and
flags any shape that matches an entry in dead_paths.xml. Prints
structured issues to stdout; exits 1 if any dead paths are found, 0
if the XML is oracle-clean.

Usage:

    cat timing.xml | python validate.py
    python validate.py --file timing.xml
    python validate.py --file some.pptx-slide-fragment.xml

Empty output + exit 0 = oracle-clean. Non-empty output + exit 1 = one
or more dead-path matches; each with the offending shape signature, a
verdict, and the replacement slot to use instead.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from svg2ooxml.drawingml.animation.oracle import DeadPath, default_oracle
from svg2ooxml.drawingml.xml_builder import NS_P


@dataclass
class ValidationIssue:
    dead_path: DeadPath
    line: int | None
    offending_xml: str


def _element_matches_shape(
    elem: etree._Element,
    dead_path: DeadPath,
) -> bool:
    """Return True if *elem* matches *dead_path*'s shape signature."""
    # Check element name (strip namespace)
    local_name = etree.QName(elem).localname
    expected_local = dead_path.element.split(":")[-1] if ":" in dead_path.element else dead_path.element
    if local_name != expected_local:
        return False

    # Walk through the dead-path attribute signatures
    for attr_name, attr_value in zip(
        dead_path.attribute_names, dead_path.attribute_values
    ):
        if attr_name == "attrName":
            # attrName lives inside <p:attrNameLst><p:attrName>value</p:attrName>
            # which is a CHILD of <p:cBhvr> inside the containing element.
            found = False
            for attr_name_el in elem.iter(f"{{{NS_P}}}attrName"):
                if (attr_name_el.text or "").strip() == attr_value:
                    found = True
                    break
            if not found:
                return False
        elif attr_name == "filter":
            if elem.get("filter") != attr_value:
                return False
        elif attr_name == "prLst":
            if elem.get("prLst") != attr_value:
                return False
        else:
            if elem.get(attr_name) != attr_value:
                return False

    return True


def validate_xml(xml_bytes: bytes) -> list[ValidationIssue]:
    """Walk *xml_bytes* and return a list of dead-path matches."""
    parser = etree.XMLParser(remove_blank_text=False, recover=False)
    root = etree.fromstring(xml_bytes, parser)
    oracle = default_oracle()
    issues: list[ValidationIssue] = []

    for dead_path in oracle.dead_paths():
        # Iterate every element in the tree; simpler than pre-computing namespace.
        for elem in root.iter():
            if _element_matches_shape(elem, dead_path):
                issues.append(
                    ValidationIssue(
                        dead_path=dead_path,
                        line=elem.sourceline,
                        offending_xml=etree.tostring(
                            elem, encoding="unicode"
                        )[:200],
                    )
                )

    return issues


def format_issue(issue: ValidationIssue) -> str:
    dp = issue.dead_path
    lines: list[str] = []
    loc = f"line {issue.line}" if issue.line else "line ?"
    attrs = ", ".join(
        f"{k}={v!r}"
        for k, v in zip(dp.attribute_names, dp.attribute_values)
    )
    lines.append(f"{loc}: {dp.element} {{{attrs}}} — DEAD PATH ({dp.verdict})")
    lines.append(f"  id:          {dp.id}")
    lines.append(f"  replacement: {dp.replacement_slot}")
    lines.append(f"  note:        {dp.replacement_note}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--file",
        type=Path,
        help="Read XML from this file instead of stdin.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.file:
        xml_bytes = args.file.read_bytes()
    else:
        xml_bytes = sys.stdin.buffer.read()

    if not xml_bytes.strip():
        sys.stderr.write("ERROR: no XML input\n")
        return 2

    try:
        issues = validate_xml(xml_bytes)
    except etree.XMLSyntaxError as exc:
        sys.stderr.write(f"XML parse error: {exc}\n")
        return 2

    if not issues:
        return 0

    print(f"Found {len(issues)} dead-path match(es):\n")
    for issue in issues:
        print(format_issue(issue))
        print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
