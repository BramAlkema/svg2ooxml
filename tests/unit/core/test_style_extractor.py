from __future__ import annotations

from types import SimpleNamespace

import pytest
from lxml import etree

from svg2ooxml.common.style.resolver import StyleResolver
from svg2ooxml.common.units import UnitConverter
from svg2ooxml.core.styling.style_extractor import StyleExtractor
from svg2ooxml.drawingml.bridges.resvg_paint_bridge import describe_gradient_element
from svg2ooxml.ir.paint import LinearGradientPaint, SolidPaint, StrokeCap, StrokeJoin
from svg2ooxml.services import configure_services


class DummyServices:
    gradient_service = None
    pattern_service = None
    filter_service = None
    policy_context = None

    def resolve(self, name: str, default=None):
        return getattr(self, name, default)


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
    assert style.fill.rgb.upper() == "008000"


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
    assert style.fill.rgb.upper() == "FF0000"


def test_style_extractor_resolves_absolute_stroke_dash_lengths() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <rect id='target' width='10' height='10'
                  fill='none' stroke='#000000' stroke-width='1'
                  stroke-dasharray='0.25in 6pt' stroke-dashoffset='3pt'/>
        </svg>
    """
    root, rect = _build_svg(markup)

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)

    style = extractor.extract(rect, DummyServices())

    assert style.stroke is not None
    assert style.stroke.dash_array == [24.0, 8.0]
    assert style.stroke.dash_offset == 4.0


def test_style_extractor_resolves_calc_stroke_dash_lengths() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <rect id='target' width='10' height='10'
                  fill='none' stroke='#000000' stroke-width='1'
                  stroke-dasharray='calc(0.25in + 6pt), calc(2 * 1em)'
                  stroke-dashoffset='calc(1pt + 3pt)'/>
        </svg>
    """
    root, rect = _build_svg(markup)

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)

    style = extractor.extract(rect, DummyServices())

    assert style.stroke is not None
    assert style.stroke.dash_array == [32.0, 24.0]
    assert style.stroke.dash_offset == pytest.approx(16.0 / 3.0)


def test_style_extractor_inherits_stroke_dash_presentation() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <g stroke='#000000' stroke-width='3'
               stroke-linecap='round' stroke-linejoin='bevel'
               stroke-dasharray='25 5' stroke-dashoffset='4'>
                <circle id='target' cx='10' cy='10' r='5'/>
            </g>
        </svg>
    """
    root, circle = _build_svg(markup)

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)

    style = extractor.extract(circle, DummyServices())

    assert style.stroke is not None
    assert style.stroke.width == pytest.approx(3.0)
    assert style.stroke.cap is StrokeCap.ROUND
    assert style.stroke.join is StrokeJoin.BEVEL
    assert style.stroke.dash_array == [25.0, 5.0]
    assert style.stroke.dash_offset == pytest.approx(4.0)


def test_style_extractor_accepts_calc_opacity_and_stroke_width() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <rect id='target' width='10' height='10'
                  fill='#ffffff' fill-opacity='calc(25% + 25%)'
                  opacity='50%' stroke='#000000'
                  stroke-opacity='calc(20% + 30%)'
                  stroke-width='calc(1px + 1px)'/>
        </svg>
    """
    root, rect = _build_svg(markup)

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)

    style = extractor.extract(rect, DummyServices())

    assert isinstance(style.fill, SolidPaint)
    assert style.fill.opacity == pytest.approx(0.5)
    assert style.opacity == pytest.approx(0.5)
    assert style.stroke is not None
    assert style.stroke.width == pytest.approx(2.0)
    assert style.stroke.opacity == pytest.approx(0.5)


def test_style_extractor_preserves_zero_stroke_width() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <rect id='target' width='10' height='10'
                  fill='none' stroke='#000000' stroke-width='0'/>
        </svg>
    """
    root, rect = _build_svg(markup)

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)

    style = extractor.extract(rect, DummyServices())

    assert style.stroke is not None
    assert style.stroke.width == 0.0


def test_style_extractor_records_vector_effect_from_css() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>
                #target { vector-effect: non-scaling-stroke; }
            </style>
            <rect id='target' width='10' height='10'
                  fill='none' stroke='#000000' stroke-width='2'/>
        </svg>
    """
    root, rect = _build_svg(markup)

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)

    style = extractor.extract(rect, DummyServices())

    assert style.metadata["vector_effect"] == "non-scaling-stroke"


def test_style_extractor_accepts_calc_stroke_miterlimit() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <rect id='target' width='10' height='10'
                  fill='none' stroke='#000000'
                  stroke-miterlimit='calc(2 + 2)'/>
        </svg>
    """
    root, rect = _build_svg(markup)

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)

    style = extractor.extract(rect, DummyServices())

    assert style.stroke is not None
    assert style.stroke.miter_limit == pytest.approx(4.0)


def test_style_extractor_resolves_userspace_gradient_coordinates() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg' width='200' height='100'>
            <defs>
                <linearGradient id='grad' gradientUnits='userSpaceOnUse'
                                x1='0.25in' y1='6pt'>
                    <stop offset='0' stop-color='#000000'/>
                    <stop offset='1' stop-color='#ffffff'/>
                </linearGradient>
            </defs>
            <rect id='target' width='100' height='50' fill='url(#grad)'/>
        </svg>
    """
    root, rect = _build_svg(markup)
    gradient = root.xpath(".//*[local-name()='linearGradient']")[0]
    services = configure_services()
    assert services.gradient_service is not None
    services.gradient_service.register_gradient(
        "grad", describe_gradient_element(gradient)
    )

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)
    conversion = UnitConverter().create_context(width=200.0, height=100.0)
    context = SimpleNamespace(conversion=conversion)

    style = extractor.extract(rect, services, context=context)

    assert isinstance(style.fill, LinearGradientPaint)
    assert style.fill.gradient_units == "userSpaceOnUse"
    assert style.fill.start == pytest.approx((24.0, 8.0))
    assert style.fill.end == pytest.approx((200.0, 0.0))


def test_style_extractor_preserves_explicit_object_bbox_gradient_override() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg' width='200' height='100'>
            <defs>
                <linearGradient id='base' gradientUnits='userSpaceOnUse' x2='100%'>
                    <stop offset='0' stop-color='#000000'/>
                    <stop offset='1' stop-color='#ffffff'/>
                </linearGradient>
                <linearGradient id='child' href='#base' gradientUnits='objectBoundingBox'/>
            </defs>
            <rect id='target' width='100' height='50' fill='url(#child)'/>
        </svg>
    """
    root, rect = _build_svg(markup)
    services = configure_services()
    assert services.gradient_service is not None
    for gradient in root.xpath(".//*[local-name()='linearGradient']"):
        services.gradient_service.register_gradient(
            gradient.get("id"),
            describe_gradient_element(gradient),
        )

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)
    conversion = UnitConverter().create_context(width=200.0, height=100.0)
    context = SimpleNamespace(conversion=conversion)

    style = extractor.extract(rect, services, context=context)

    assert isinstance(style.fill, LinearGradientPaint)
    assert style.fill.gradient_units == "objectBoundingBox"
    assert style.fill.end == pytest.approx((1.0, 0.0))


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


def test_style_extractor_uses_service_filter_policy_for_non_dict_context() -> None:
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

    class DummyPolicyContext:
        def get(self, target: str):
            if target == "filter":
                return {
                    "enable_effect_dag": True,
                    "enable_native_color_transforms": True,
                    "enable_blip_effect_enrichment": True,
                }
            return None

    services = DummyServices()
    services.filter_service = DummyFilterService()
    services.policy_context = DummyPolicyContext()

    resolver = StyleResolver()
    resolver.collect_css(root)
    extractor = StyleExtractor(resolver)

    extractor.extract(rect, services, context=object())

    assert len(services.filter_service.contexts) == 1
    filter_context = services.filter_service.contexts[0]
    assert filter_context["element"] is rect
    assert filter_context["policy"] == {
        "enable_effect_dag": True,
        "enable_native_color_transforms": True,
        "enable_blip_effect_enrichment": True,
    }
