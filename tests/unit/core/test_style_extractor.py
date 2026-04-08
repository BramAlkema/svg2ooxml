from __future__ import annotations

from lxml import etree

from svg2ooxml.common.style.resolver import StyleResolver
from svg2ooxml.core.styling.style_extractor import StyleExtractor
from svg2ooxml.ir.paint import SolidPaint


class DummyServices:
    gradient_service = None
    pattern_service = None
    filter_service = None


def _build_svg(markup: str) -> tuple[etree._Element, etree._Element]:
    root = etree.fromstring(markup)
    target = root.xpath(".//*[@id='target']")[0]
    return root, target  # type: ignore[return-value]


def test_style_extractor_inherits_parent_fill() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <g fill='#008000'>
                <rect id='target' width='10' height='10'/>
            </g>
        </svg>
    """
    root, rect = _build_svg(markup)

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)

    style = extractor.extract(rect, DummyServices())
    assert isinstance(style.fill, SolidPaint)
    assert style.fill.rgb.upper() == '008000'


def test_style_extractor_respects_inline_override() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <g fill='#008000'>
                <rect id='target' width='10' height='10' fill='#ff0000'/>
            </g>
        </svg>
    """
    root, rect = _build_svg(markup)

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)

    style = extractor.extract(rect, DummyServices())
    assert isinstance(style.fill, SolidPaint)
    assert style.fill.rgb.upper() == 'FF0000'


def test_style_extractor_normalizes_filter_url_before_resolution() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <rect id='target' width='10' height='10' fill='#ff0000' filter='url(#glow)'/>
        </svg>
    """
    root, rect = _build_svg(markup)

    class DummyFilterService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def resolve_effects(self, filter_ref: str, *, context=None):
            self.calls.append(filter_ref)
            return ["effect"]

    services = DummyServices()
    services.filter_service = DummyFilterService()

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)

    style = extractor.extract(rect, services)

    assert style.effects == ["effect"]
    assert services.filter_service.calls == ["glow"]


def test_style_extractor_passes_source_element_into_filter_context() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <rect id='target' width='10' height='10' fill='#ff0000' filter='url(#blur)'/>
        </svg>
    """
    root, rect = _build_svg(markup)

    class DummyFilterService:
        def __init__(self) -> None:
            self.contexts: list[dict] = []

        def resolve_effects(self, filter_ref: str, *, context=None):
            assert filter_ref == "blur"
            assert isinstance(context, dict)
            self.contexts.append(context)
            return []

    services = DummyServices()
    services.filter_service = DummyFilterService()

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)

    extractor.extract(rect, services, context={"sentinel": "ok"})

    assert len(services.filter_service.contexts) == 1
    filter_context = services.filter_service.contexts[0]
    assert filter_context["sentinel"] == "ok"
    assert filter_context["element"] is rect
