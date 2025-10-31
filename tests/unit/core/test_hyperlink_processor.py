"""Tests for the core hyperlink processor."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.core.hyperlinks import HyperlinkProcessor
from svg2ooxml.core.pipeline.navigation import NavigationKind


def _build_element(svg: str):
    return etree.fromstring(svg).find("{http://www.w3.org/2000/svg}a")


def test_resolve_navigation_parses_data_attributes() -> None:
    svg = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <a data-slide="1" data-bookmark="intro">
                <title>Go!</title>
            </a>
        </svg>
    """
    element = _build_element(svg)
    assert element is not None

    processor = HyperlinkProcessor(logger=_DummyLogger())
    nav = processor.resolve_navigation(element)

    assert nav is not None
    assert nav.kind is NavigationKind.SLIDE
    assert nav.slide is not None and nav.slide.index == 1
    assert nav.bookmark is None
    assert nav.tooltip == "Go!"
    assert nav.tooltip == "Go!"


def test_resolve_inline_navigation_handles_missing_attributes() -> None:
    svg = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <a href="#local"/>
        </svg>
    """
    element = _build_element(svg)
    assert element is not None

    processor = HyperlinkProcessor(logger=_DummyLogger())
    nav = processor.resolve_inline_navigation(element)

    assert nav is not None
    assert nav.kind is NavigationKind.BOOKMARK
    assert nav.bookmark is not None and nav.bookmark.name == "local"


def test_resolve_navigation_supports_bookmark_data() -> None:
    svg = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <a data-bookmark="intro" data-visited="false"/>
        </svg>
    """
    element = _build_element(svg)
    assert element is not None

    processor = HyperlinkProcessor(logger=_DummyLogger())
    nav = processor.resolve_navigation(element)

    assert nav is not None
    assert nav.kind is NavigationKind.BOOKMARK
    assert nav.bookmark is not None and nav.bookmark.name == "intro"
    assert nav.visited is False


class _DummyLogger:
    def warning(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass
