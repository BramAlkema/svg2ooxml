"""Tests for resvg-derived clip and mask definitions."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.core.ir import IRConverter
from svg2ooxml.core.parser import ParseResult
from svg2ooxml.core.traversal.clipping import resolve_clip_ref, resolve_mask_ref
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.services import configure_services


def _build_converter() -> IRConverter:
    services = configure_services()
    return IRConverter(services=services, logger=None, policy_engine=None, policy_context=None)


def test_resvg_clip_definition_used_in_converter() -> None:
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <defs>
                <clipPath id='clip1'>
                    <path d='M0 0 L10 0 L10 10 L0 10 Z'/>
                </clipPath>
            </defs>
            <rect id='shape' width='10' height='10' clip-path='url(#clip1)' />
        </svg>
    """

    svg_root = etree.fromstring(svg_markup)
    converter = _build_converter()
    converter._build_resvg_lookup(svg_root)

    parse_result = ParseResult.success_with(svg_root, element_count=2)
    converter._prepare_context(parse_result)

    rect_element = svg_root.find("{http://www.w3.org/2000/svg}rect")
    assert rect_element is not None

    clip_ref = resolve_clip_ref(
        rect_element,
        clip_definitions=converter._clip_definitions,
        services=converter._services,
        logger=converter._logger,
        tolerance=0.25,
        is_axis_aligned=lambda matrix, tol: True,
    )
    assert clip_ref is not None
    assert clip_ref.path_segments


def test_resvg_mask_definition_used_in_converter() -> None:
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <defs>
                <mask id='mask1'>
                    <path d='M0 0 L10 0 L10 10 L0 10 Z'/>
                </mask>
            </defs>
            <rect id='shape' width='10' height='10' mask='url(#mask1)' />
        </svg>
    """

    svg_root = etree.fromstring(svg_markup)
    converter = _build_converter()
    converter._build_resvg_lookup(svg_root)

    parse_result = ParseResult.success_with(svg_root, element_count=2)
    converter._prepare_context(parse_result)

    rect_element = svg_root.find("{http://www.w3.org/2000/svg}rect")
    assert rect_element is not None

    mask_ref, mask_instance = resolve_mask_ref(
        rect_element,
        mask_info=converter._mask_info,
    )
    assert mask_ref is not None
    assert mask_ref.definition is not None
    assert mask_ref.definition.segments


def test_resvg_clip_handles_nested_groups_and_use() -> None:
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <defs>
                <path id='star' d='M0 0 L10 0 L5 10 Z'/>
                <clipPath id='complex'>
                    <g transform='translate(2,3) scale(0.5)'>
                        <rect x='0' y='0' width='20' height='20'/>
                        <use href='#star' />
                    </g>
                </clipPath>
            </defs>
            <rect width='10' height='10' clip-path='url(#complex)' />
        </svg>
    """

    converter = _build_converter()
    svg_root = etree.fromstring(svg_markup)
    converter._build_resvg_lookup(svg_root)
    assert 'complex' in converter._resvg_clip_definitions
    definition = converter._resvg_clip_definitions['complex']
    assert definition.segments  # nested group produced geometry
    primitive_types = {primitive['type'] for primitive in definition.primitives}
    assert {'rect', 'path'} <= primitive_types


def test_resvg_clip_bounding_box_tracks_transformed_nested_use_positions() -> None:
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <defs>
                <rect id='leaf' width='2' height='3' />
                <clipPath id='complex'>
                    <g transform='translate(20,10)'>
                        <use href='#leaf' x='3' y='1' />
                        <use href='#leaf' x='8' y='4' transform='matrix(-1 0 0 1 20 0)' />
                    </g>
                </clipPath>
            </defs>
            <rect id='shape' width='10' height='10' clip-path='url(#complex)' />
        </svg>
    """

    converter = _build_converter()
    svg_root = etree.fromstring(svg_markup)
    converter._build_resvg_lookup(svg_root)

    parse_result = ParseResult.success_with(svg_root, element_count=sum(1 for _ in svg_root.iter()))
    converter._prepare_context(parse_result)

    rect_element = svg_root.find("{http://www.w3.org/2000/svg}rect[@id='shape']")
    assert rect_element is not None

    clip_ref = resolve_clip_ref(
        rect_element,
        clip_definitions=converter._clip_definitions,
        services=converter._services,
        logger=converter._logger,
        tolerance=0.25,
        is_axis_aligned=lambda matrix, tol: True,
    )
    assert clip_ref is not None
    assert clip_ref.bounding_box is not None
    assert clip_ref.bounding_box.x == 23.0
    assert clip_ref.bounding_box.y == 11.0
    assert clip_ref.bounding_box.width == 9.0
    assert clip_ref.bounding_box.height == 6.0


def test_resvg_mask_flags_raster_and_unsupported_nodes() -> None:
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <defs>
                <mask id='maskr'>
                    <image href='data:image/png;base64,iVBORw0KGgo=' width='10' height='10'/>
                    <foreignObject width='5' height='5'/>
                </mask>
            </defs>
            <rect width='10' height='10' mask='url(#maskr)' />
        </svg>
    """

    converter = _build_converter()
    svg_root = etree.fromstring(svg_markup)
    converter._build_resvg_lookup(svg_root)
    assert 'maskr' in converter._resvg_mask_info
    info = converter._resvg_mask_info['maskr']
    assert any(primitive['type'] == 'image' for primitive in info.primitives)
    mask_policy = info.policy_hints.get('mask', {})
    assert mask_policy.get('requires_raster') is True
    assert 'unsupported_nodes' in mask_policy


def test_resvg_mask_bounding_box_tracks_transformed_nested_use_positions() -> None:
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <defs>
                <rect id='leaf' width='2' height='3' />
                <mask id='mask1'
                      maskUnits='userSpaceOnUse'
                      maskContentUnits='userSpaceOnUse'
                      x='0' y='0' width='100' height='100'>
                    <g transform='translate(20,10)'>
                        <use href='#leaf' x='3' y='1' />
                        <use href='#leaf' x='8' y='4' transform='matrix(-1 0 0 1 20 0)' />
                    </g>
                </mask>
            </defs>
            <rect id='shape' width='10' height='10' mask='url(#mask1)' />
        </svg>
    """

    converter = _build_converter()
    svg_root = etree.fromstring(svg_markup)
    converter._build_resvg_lookup(svg_root)

    parse_result = ParseResult.success_with(svg_root, element_count=sum(1 for _ in svg_root.iter()))
    converter._prepare_context(parse_result)

    rect_element = svg_root.find("{http://www.w3.org/2000/svg}rect[@id='shape']")
    assert rect_element is not None

    mask_ref, mask_instance = resolve_mask_ref(
        rect_element,
        mask_info=converter._mask_info,
    )
    assert mask_ref is not None
    assert mask_ref.definition is not None
    assert mask_instance is not None
    assert mask_ref.definition.bounding_box == Rect(x=23.0, y=11.0, width=9.0, height=6.0)
    assert mask_ref.definition.region == Rect(x=0.0, y=0.0, width=100.0, height=100.0)
    assert mask_ref.definition.mask_units == "userSpaceOnUse"
    assert mask_ref.definition.mask_content_units == "userSpaceOnUse"
    assert mask_instance.bounds == Rect(x=0.0, y=0.0, width=100.0, height=100.0)
    assert len(mask_ref.definition.content_xml) == 1
    assert "transform=\"translate(20,10)\"" in mask_ref.definition.content_xml[0]
    assert "<use href=\"#leaf\" x=\"3\" y=\"1\"/>" in mask_ref.definition.content_xml[0]


def test_resvg_mask_preserves_percentage_region_and_units_metadata() -> None:
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <defs>
                <mask id='mask1'
                      maskUnits='objectBoundingBox'
                      maskContentUnits='userSpaceOnUse'
                      x='10%' y='20%' width='30%' height='40%'>
                    <rect x='1' y='2' width='3' height='4' />
                </mask>
            </defs>
            <rect id='shape' width='10' height='10' mask='url(#mask1)' />
        </svg>
    """

    converter = _build_converter()
    svg_root = etree.fromstring(svg_markup)
    converter._build_resvg_lookup(svg_root)

    parse_result = ParseResult.success_with(svg_root, element_count=sum(1 for _ in svg_root.iter()))
    converter._prepare_context(parse_result)

    rect_element = svg_root.find("{http://www.w3.org/2000/svg}rect[@id='shape']")
    assert rect_element is not None

    mask_ref, _ = resolve_mask_ref(
        rect_element,
        mask_info=converter._mask_info,
    )
    assert mask_ref is not None
    assert mask_ref.definition is not None
    assert mask_ref.definition.mask_units == "objectBoundingBox"
    assert mask_ref.definition.mask_content_units == "userSpaceOnUse"
    assert mask_ref.definition.region == Rect(x=0.1, y=0.2, width=0.3, height=0.4)
    assert mask_ref.definition.raw_region == {
        "x": "10%",
        "y": "20%",
        "width": "30%",
        "height": "40%",
    }


def test_resvg_gradients_register_with_gradient_service() -> None:
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <defs>
                <linearGradient id='grad1' x1='0%' y1='0%' x2='100%' y2='0%'>
                    <stop offset='0%' stop-color='#000000'/>
                    <stop offset='100%' stop-color='#ffffff'/>
                </linearGradient>
            </defs>
            <rect width='10' height='10' fill='url(#grad1)' />
        </svg>
    """

    converter = _build_converter()
    svg_root = etree.fromstring(svg_markup)
    converter._build_resvg_lookup(svg_root)

    gradient_service = converter._services.gradient_service
    assert gradient_service is not None

    descriptor = gradient_service.get('grad1')
    assert descriptor is not None
    element = gradient_service.as_element(descriptor)
    assert element.tag == 'linearGradient'
    stops = element.findall('.//{http://www.w3.org/2000/svg}stop')
    if not stops:
        stops = element.findall('.//stop')
    assert len(stops) == 2


def test_resvg_patterns_register_with_pattern_service() -> None:
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <defs>
                <pattern id='pat1' patternUnits='userSpaceOnUse' width='10' height='10'>
                    <rect width='10' height='10' fill='#ff0000'/>
                </pattern>
            </defs>
            <rect width='10' height='10' fill='url(#pat1)' />
        </svg>
    """

    converter = _build_converter()
    svg_root = etree.fromstring(svg_markup)
    converter._build_resvg_lookup(svg_root)

    pattern_service = converter._services.pattern_service
    assert pattern_service is not None

    descriptor = pattern_service.get('pat1')
    assert descriptor is not None
    element = pattern_service.as_element(descriptor)
    assert element.tag.endswith('pattern')
    assert len(list(element)) > 0
