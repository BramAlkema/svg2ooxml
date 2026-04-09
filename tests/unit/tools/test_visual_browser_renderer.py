from __future__ import annotations

from tools.visual.browser_renderer import (
    _extract_dimensions as extract_browser_dimensions,
    _prepare_browser_source_text,
    _resolve_inline_svg_markup,
)
from tools.visual.suite_runner import _extract_dimensions as extract_suite_dimensions


def test_browser_extract_dimensions_accepts_xml_declaration() -> None:
    svg = """<?xml version="1.0" encoding="UTF-8"?>
    <svg xmlns="http://www.w3.org/2000/svg" width="320" height="200"></svg>
    """

    assert extract_browser_dimensions(svg) == (320, 200)


def test_suite_runner_extract_dimensions_accepts_xml_declaration() -> None:
    svg = """<?xml version="1.0" encoding="UTF-8"?>
    <svg xmlns="http://www.w3.org/2000/svg" width="320" height="200"></svg>
    """

    assert extract_suite_dimensions(svg) == (320.0, 200.0)


def test_browser_extract_dimensions_recovers_from_broken_svg_header() -> None:
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000">
<
<path d="M0,0 L10,10"/>
</svg>
"""

    assert extract_browser_dimensions(svg) == (1000, 1000)


def test_prepare_browser_source_text_recovers_malformed_svg() -> None:
    source = """<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000">
<
<path d="M0,0 L10,10"/>
</svg>
"""

    prepared = _prepare_browser_source_text(source)

    assert "<\n<path" not in prepared
    assert 'width="1000"' in prepared


def test_resolve_inline_svg_markup_strips_xml_prolog() -> None:
    svg = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN">
<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"></svg>
"""

    inline_svg, temp_path = _resolve_inline_svg_markup(svg, source_path=None)

    assert temp_path is None
    assert inline_svg.lstrip().startswith("<svg")
    assert "<?xml" not in inline_svg
    assert "<!DOCTYPE" not in inline_svg
