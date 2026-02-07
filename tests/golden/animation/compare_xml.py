"""Structural XML comparison for golden master tests.

The animation writer outputs namespace-prefixed XML (p:timing, a:srgbClr)
without namespace declarations, which is not parseable by standard XML parsers.
We compare using string equality after normalization, and provide a meaningful
diff on mismatch.
"""

from __future__ import annotations

import difflib


def xml_strings_equal(actual: str, expected: str) -> tuple[bool, str]:
    """Compare two XML strings for exact equality.

    Returns (True, "") if equal, or (False, diff_description) with a
    unified diff showing differences.
    """
    actual = actual.strip()
    expected = expected.strip()

    if actual == expected:
        return True, ""

    # Generate a readable diff
    actual_lines = _format_for_diff(actual)
    expected_lines = _format_for_diff(expected)

    diff = difflib.unified_diff(
        expected_lines,
        actual_lines,
        fromfile="expected",
        tofile="actual",
        lineterm="",
    )
    diff_text = "\n".join(diff)
    return False, diff_text


def _format_for_diff(xml: str) -> list[str]:
    """Break a single-line XML string into readable lines for diffing.

    Inserts newlines before opening tags to make the diff more useful.
    """
    result = xml.replace("><", ">\n<")
    return result.split("\n")
