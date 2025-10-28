"""Verify resvg filter descriptors integrate with the filter registry."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.ir.geometry import LineSegment, Point
from svg2ooxml.ir.scene import Path
from svg2ooxml.core.ir import IRConverter
from svg2ooxml.services import configure_services
from svg2ooxml.services.filter_types import FilterEffectResult


def _build_converter() -> IRConverter:
    services = configure_services()
    return IRConverter(services=services, logger=None, policy_engine=None, policy_context=None)


class RecordingFilterService:
    def __init__(self) -> None:
        self.registered: dict[str, etree._Element] = {}
        self.last_context: dict | None = None

    def bind_services(self, services) -> None:  # noqa: D401 - simple binding hook
        self._services = services

    def register_filter(self, filter_id: str, element: etree._Element) -> None:
        self.registered[filter_id] = element

    def get(self, filter_id: str) -> etree._Element | None:
        return self.registered.get(filter_id)

    def resolve_effects(self, filter_id: str, *, context=None):
        self.last_context = context
        return [
            FilterEffectResult(
                effect=None,
                strategy="native",
                metadata={"resolver": "recording"},
                fallback=None,
            )
        ]


def test_resvg_filters_register_with_filter_service() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="blur1" filterUnits="userSpaceOnUse">
                    <feGaussianBlur stdDeviation="4"/>
                </filter>
            </defs>
            <rect id="shape" width="10" height="10" filter="url(#blur1)" />
        </svg>
    """

    root = etree.fromstring(svg_markup)
    converter = _build_converter()

    converter._build_resvg_lookup(root)

    filter_service = getattr(converter._services, "filter_service", None)
    assert filter_service is not None

    registered = filter_service.get("blur1")
    assert registered is not None
    effects = filter_service.resolve_effects("url(#blur1)")
    assert isinstance(effects, list)


def test_filter_context_includes_bounds_and_descriptor() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="shadow" filterUnits="objectBoundingBox" primitiveUnits="userSpaceOnUse">
                    <feOffset dx="2" dy="3"/>
                </filter>
            </defs>
            <rect width="10" height="10" filter="url(#shadow)" />
        </svg>
    """

    services = configure_services()
    recording_service = RecordingFilterService()
    services.register("filter", recording_service)
    converter = IRConverter(services=services, logger=None, policy_engine=None, policy_context=None)

    root = etree.fromstring(svg_markup)
    converter._build_resvg_lookup(root)

    rect_element = root.find("{http://www.w3.org/2000/svg}rect")
    assert rect_element is not None

    segments = [
        LineSegment(Point(0.0, 0.0), Point(10.0, 0.0)),
        LineSegment(Point(10.0, 0.0), Point(10.0, 10.0)),
        LineSegment(Point(10.0, 10.0), Point(0.0, 10.0)),
        LineSegment(Point(0.0, 10.0), Point(0.0, 0.0)),
    ]
    ir_path = Path(segments=segments, fill=None)
    metadata: dict = {}

    converter._apply_filter_metadata(ir_path, rect_element, metadata)

    context = recording_service.last_context
    assert context is not None
    assert context.get("ir_bbox") == {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0}
    descriptor = context.get("resvg_descriptor")
    assert descriptor is not None
    assert descriptor["primitive_tags"] == ["feOffset"]
    assert descriptor["filter_region"] == {"x": None, "y": None, "width": None, "height": None}

    filter_entries = metadata.get("filters", [])
    assert filter_entries and filter_entries[0]["bounds"]["width"] == 10.0
    assert filter_entries[0]["descriptor"]["primitive_count"] == 1
