"""Helpers for preparing raw SVG content before parsing."""

from __future__ import annotations

XML_DECLARATION = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"


def prepare_svg_content(
    svg_content: str,
    *,
    report: dict[str, object] | None = None,
) -> str:
    """Normalize incoming SVG text and ensure it looks parseable.

    When ``report`` is provided, it is populated with lightweight instrumentation
    that mirrors the legacy svg2pptx parser output. Keys include:

    - ``removed_bom``: whether a UTF-8 BOM was stripped
    - ``encoding_replacements``: total characters replaced prior to parsing
    - ``encoding_replacements_by_char``: mapping of replaced codepoints to counts
    - ``added_xml_declaration``: whether the XML declaration was injected
    """

    instrumentation: dict[str, object] = {} if report is None else report

    removed_bom = svg_content.startswith("\ufeff")
    if removed_bom:
        svg_content = svg_content.lstrip("\ufeff")
    instrumentation["removed_bom"] = removed_bom

    content = svg_content.strip()
    if not content:
        instrumentation["error"] = "empty_content"
        raise ValueError("Empty SVG content")

    lowered = content.lower()
    if "<svg" not in lowered:
        instrumentation["error"] = "missing_svg_tag"
        raise ValueError("Content does not appear to be SVG")

    content = fix_encoding_issues(content, report=instrumentation)

    added_xml_declaration = False
    if not content.startswith("<?xml"):
        content = f"{XML_DECLARATION}{content}"
        added_xml_declaration = True
    instrumentation["added_xml_declaration"] = added_xml_declaration

    return content


def fix_encoding_issues(
    content: str,
    *,
    report: dict[str, object] | None = None,
) -> str:
    """Replace characters that confuse XML parsers.

    Returns the cleaned string while optionally populating ``report`` with
    aggregate counts for the characters that were substituted.
    """

    replacements = {
        "\x00": "",
        "\x0b": " ",
        "\x0c": " ",
    }

    replacement_counts: dict[str, int] = {}
    for old, new in replacements.items():
        occurrences = content.count(old)
        if occurrences:
            content = content.replace(old, new)
            replacement_counts[f"U+{ord(old):04X}"] = occurrences

    if report is not None:
        total = sum(replacement_counts.values())
        report["encoding_replacements"] = total
        if replacement_counts:
            report["encoding_replacements_by_char"] = replacement_counts
        else:
            report.setdefault("encoding_replacements_by_char", {})

    return content


__all__ = ["prepare_svg_content", "fix_encoding_issues", "XML_DECLARATION"]
