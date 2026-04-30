"""Tests for SVG content cleaning helpers."""

import pytest

from svg2ooxml.core.parser.content_cleaner import (
    XML_DECLARATION,
    fix_encoding_issues,
    prepare_svg_content,
)


def test_prepare_svg_content_adds_declaration_and_strips_bom() -> None:
    raw = "\ufeff  <svg></svg>"

    report: dict[str, object] = {}
    cleaned = prepare_svg_content(raw, report=report)

    assert cleaned.startswith(XML_DECLARATION)
    assert "<svg></svg>" in cleaned
    assert report["removed_bom"] is True
    assert report["added_xml_declaration"] is True
    assert report["encoding_replacements"] == 0


def test_prepare_svg_content_expands_safe_internal_markup_entities() -> None:
    raw = (
        "<!DOCTYPE svg ["
        "<!ENTITY Viewport \"<rect x='.5' y='.5' width='49' height='29'/>\">"
        "]>"
        "<svg width='50' height='30'>&Viewport;</svg>"
    )

    report: dict[str, object] = {}
    cleaned = prepare_svg_content(raw, report=report)

    assert "&Viewport;" not in cleaned
    assert "<rect x='.5' y='.5' width='49' height='29'/>" in cleaned
    assert report["internal_entities_defined"] == 1
    assert report["internal_entity_expansions"] == 1


def test_prepare_svg_content_rejects_non_svg() -> None:
    report: dict[str, object] = {}
    with pytest.raises(ValueError):
        prepare_svg_content("<html></html>", report=report)
    assert report.get("error") == "missing_svg_tag"


def test_fix_encoding_issues_replaces_problem_chars() -> None:
    dirty = "a\x00b\x0bc\x0c"

    report: dict[str, object] = {}
    cleaned = fix_encoding_issues(dirty, report=report)

    assert "\x00" not in cleaned
    assert "\x0b" not in cleaned
    assert "\x0c" not in cleaned
    assert report["encoding_replacements"] == 3
    assert report["encoding_replacements_by_char"]["U+0000"] == 1
