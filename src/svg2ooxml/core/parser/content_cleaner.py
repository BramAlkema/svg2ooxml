"""Helpers for preparing raw SVG content before parsing."""

from __future__ import annotations

import re

XML_DECLARATION = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
_ENTITY_DEF_RE = re.compile(
    r"<!ENTITY\s+"
    r"(?P<name>[A-Za-z_:][A-Za-z0-9_.:-]*)\s+"
    r"(?P<quote>['\"])(?P<value>.*?)(?P=quote)\s*>",
    re.DOTALL,
)
_ENTITY_REF_RE = re.compile(r"&(?P<name>[A-Za-z_:][A-Za-z0-9_.:-]*);")
_XML_BUILTIN_ENTITIES = frozenset({"amp", "apos", "gt", "lt", "quot"})


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
    content = expand_safe_internal_entities(content, report=instrumentation)

    added_xml_declaration = False
    if not content.startswith("<?xml"):
        content = f"{XML_DECLARATION}{content}"
        added_xml_declaration = True
    instrumentation["added_xml_declaration"] = added_xml_declaration

    return content


def expand_safe_internal_entities(
    content: str,
    *,
    report: dict[str, object] | None = None,
) -> str:
    """Inline simple internal general entities while leaving external ones inert.

    The W3C SVG corpus uses internal entities as markup macros. Our XML parser
    deliberately disables entity resolution, so these safe local snippets need a
    small preparse expansion path that does not touch ``SYSTEM``/``PUBLIC``
    declarations.
    """

    subset_bounds = _doctype_internal_subset_bounds(content)
    if subset_bounds is None:
        if report is not None:
            report.setdefault("internal_entities_defined", 0)
            report.setdefault("internal_entity_expansions", 0)
        return content

    subset_start, subset_end, doctype_end = subset_bounds
    subset = content[subset_start:subset_end]
    entities = _collect_safe_internal_entities(subset)
    if not entities:
        if report is not None:
            report["internal_entities_defined"] = 0
            report["internal_entity_expansions"] = 0
        return content

    prefix = content[:doctype_end]
    body = content[doctype_end:]
    total_expansions = 0
    for _ in range(8):
        expansions = 0

        def _replace(match: re.Match[str]) -> str:
            nonlocal expansions
            name = match.group("name")
            if name in _XML_BUILTIN_ENTITIES:
                return match.group(0)
            value = entities.get(name)
            if value is None:
                return match.group(0)
            expansions += 1
            return value

        updated = _ENTITY_REF_RE.sub(_replace, body)
        if expansions == 0:
            break
        total_expansions += expansions
        body = updated

    if report is not None:
        report["internal_entities_defined"] = len(entities)
        report["internal_entity_expansions"] = total_expansions
    return f"{prefix}{body}"


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


def _doctype_internal_subset_bounds(content: str) -> tuple[int, int, int] | None:
    doctype_start = content.lower().find("<!doctype")
    if doctype_start < 0:
        return None
    subset_start = content.find("[", doctype_start)
    if subset_start < 0:
        return None

    quote: str | None = None
    index = subset_start + 1
    while index < len(content):
        char = content[index]
        if quote is not None:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == "]":
            end = index + 1
            while end < len(content) and content[end].isspace():
                end += 1
            if end < len(content) and content[end] == ">":
                return (subset_start + 1, index, end + 1)
        index += 1
    return None


def _collect_safe_internal_entities(subset: str) -> dict[str, str]:
    entities: dict[str, str] = {}
    for match in _ENTITY_DEF_RE.finditer(subset):
        declaration = match.group(0)
        if re.search(r"<!ENTITY\s+%", declaration, flags=re.IGNORECASE):
            continue
        if re.search(r"\s(?:SYSTEM|PUBLIC)\s", declaration, flags=re.IGNORECASE):
            continue
        value = match.group("value")
        lowered = value.lower()
        if "<!doctype" in lowered or "<!entity" in lowered or "<!notation" in lowered:
            continue
        entities[match.group("name")] = value
    return entities


__all__ = [
    "XML_DECLARATION",
    "expand_safe_internal_entities",
    "fix_encoding_issues",
    "prepare_svg_content",
]
