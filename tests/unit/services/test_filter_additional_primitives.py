"""Tests for additional SVG filter primitives."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.services.filter_service import FilterService
from svg2ooxml.services.filter_types import FilterEffectResult
from svg2ooxml.common.units import px_to_emu


def _resolve(service: FilterService, markup: str) -> list[FilterEffectResult]:
    element = etree.fromstring(markup)
    filter_id = element.get("id", "f")
    service.register_filter(filter_id, element)
    return service.resolve_effects(filter_id)


def test_flood_produces_extension_payload() -> None:
    service = FilterService()
    results = _resolve(service, "<filter id='f'><feFlood flood-color='#123456' flood-opacity='0.4'/></filter>")
    assert results
    effect = results[0]
    assert effect.fallback is None
    assert effect.effect.drawingml.startswith("<a:effectLst>")
    assert "<a:solidFill>" in effect.effect.drawingml
    assert "svg2ooxml:flood" not in effect.effect.drawingml


def test_offset_includes_pixel_and_emu_metadata() -> None:
    service = FilterService()
    results = _resolve(service, "<filter id='f'><feOffset dx='5' dy='-3'/></filter>")
    assert results
    effect = results[0]
    assert effect.metadata["dx"] == 5.0
    assert effect.metadata["dx_emu"] == int(px_to_emu(5.0))
    assert effect.effect.drawingml.startswith("<a:effectLst>")
    assert "<a:outerShdw" in effect.effect.drawingml


def test_morphology_dilate_emits_glow_with_colour_strategy() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f'>"
        "  <feFlood flood-color='#112233' flood-opacity='0.8' result='flooded'/>"
        "  <feMorphology operator='dilate' radius='2 4' style='opacity:0.25' in='flooded'/>"
        "</filter>",
    )
    assert results
    effect = results[1]
    assert effect.fallback is None
    assert effect.metadata["filter_type"] == "morphology"
    assert effect.metadata["radius_x"] == 2.0
    assert effect.metadata["radius_y"] == 4.0
    assert effect.metadata["radius_max"] == 4.0
    assert effect.metadata["radius_effective"] == 4.0
    assert effect.metadata["effect"] == "glow"
    assert effect.metadata["color"] == "112233"
    assert effect.metadata["color_strategy"].startswith("pipeline:flood_color")
    assert effect.metadata["alpha"] == 0.25
    assert effect.metadata["radius_emu"] == int(px_to_emu(4.0))
    assert effect.metadata["native_support"] is True
    drawingml = effect.effect.drawingml
    assert drawingml.startswith("<a:effectLst>")
    assert "<a:glow" in drawingml
    assert 'val="112233"' in drawingml


def test_morphology_erode_emits_soft_edge_effect() -> None:
    service = FilterService()
    radius = 3.5
    results = _resolve(service, f"<filter id='f'><feMorphology operator='erode' radius='{radius}'/></filter>")
    assert results
    effect = results[0]
    assert effect.metadata["effect"] == "soft_edge"
    assert effect.metadata["radius_max"] == radius
    expected_rad = int(px_to_emu(radius))
    assert effect.metadata["radius_emu"] == expected_rad
    drawingml = effect.effect.drawingml
    assert drawingml.startswith("<a:effectLst>")
    assert f'<a:softEdge rad="{expected_rad}"/>' in drawingml
    assert effect.fallback is None
    assert effect.metadata.get("native_support") is True


def test_component_transfer_serialises_functions() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f'>"
        "  <feComponentTransfer>"
        "    <feFuncR type='linear' slope='1.2' intercept='0.1'/>"
        "    <feFuncA type='gamma' amplitude='0.9' exponent='2.2' offset='0.05'/>"
        "  </feComponentTransfer>"
        "</filter>",
    )
    assert results
    effect = results[0]
    assert effect.fallback == "emf"
    assert effect.strategy == "vector"
    assets = effect.metadata.get("fallback_assets")
    assert assets and assets[0]["type"] == "emf"
    asset_meta = assets[0].get("metadata", {})
    assert assets[0].get("data_hex") or assets[0].get("data")
    assert asset_meta.get("filter_type") == "component_transfer"


def test_convolve_matrix_tracks_kernel() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f'>"
        "  <feConvolveMatrix order='3 3' kernelMatrix='0 -1 0 -1 5 -1 0 -1 0' divisor='1' bias='0.1'/>"
        "</filter>",
    )
    assert results
    effect = results[0]
    assert effect.metadata["order"] == (3, 3)
    assert effect.fallback == "emf"
    assets = effect.metadata.get("fallback_assets")
    assert assets and assets[0]["type"] == "emf"
    assert assets[0].get("metadata", {}).get("filter_type") == "convolve_matrix"


def test_displacement_map_resvg_path() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f'>"
        "  <feFlood flood-color='#ff8080' result='map'/>"
        "  <feDisplacementMap in='SourceGraphic' in2='map' scale='18' xChannelSelector='R' yChannelSelector='G'/>"
        "</filter>",
    )
    assert results
    effect = next((res for res in results if res.strategy == "resvg"), None)
    assert effect is not None
    assets = effect.metadata.get("fallback_assets") or []
    assert assets and assets[0]["type"] == "raster"
    plan_primitives = effect.metadata.get("plan_primitives")
    assert plan_primitives and plan_primitives[-1]["tag"].lower() == "fedisplacementmap"


def test_turbulence_resvg_path() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f'>"
        "  <feTurbulence baseFrequency='0.04 0.08' numOctaves='2' seed='3' type='fractalNoise'/>"
        "</filter>",
    )
    effect = next((res for res in results if res.metadata.get("filter_type") == "turbulence"), None)
    assert effect is not None
    metadata = effect.metadata or {}
    assert metadata.get("fallback_assets")
    assert metadata.get("filter_type") == "turbulence"


def test_tile_delegates_to_prior_result_when_available() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f'>"
        "  <feGaussianBlur stdDeviation='1' result='blurred'/>"
        "  <feTile in='blurred'/>"
        "</filter>",
    )
    assert len(results) >= 2
    blur, tile = results[0], results[1]
    assert blur.metadata.get("filter_type") == "gaussian_blur"
    assert tile.metadata.get("filter_type") == "tile"
    assert tile.metadata.get("input") == "blurred"
    assert tile.metadata.get("source_metadata", {}).get("filter_type") == "gaussian_blur"
    assert tile.effect.drawingml == blur.effect.drawingml
    # Descriptor fallbacks may still be emitted for diagnostics; ignore them.


def test_merge_combines_inputs_and_preserves_order() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f'>"
        "  <feGaussianBlur stdDeviation='1' result='first'/>"
        "  <feFlood flood-color='#FF0000' result='second'/>"
        "  <feMerge>"
        "    <feMergeNode in='second'/>"
        "    <feMergeNode in='first'/>"
        "  </feMerge>"
        "</filter>",
    )
    assert len(results) >= 3
    blur, flood, merge = results[:3]
    assert blur.metadata.get("filter_type") == "gaussian_blur"
    assert flood.metadata.get("filter_type") == "flood"
    assert merge.metadata.get("filter_type") == "merge"
    expected = flood.effect.drawingml + blur.effect.drawingml
    assert merge.effect.drawingml == expected


def test_diffuse_lighting_resvg_path() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f'>"
        "  <feGaussianBlur stdDeviation='1' result='height'/>"
        "  <feDiffuseLighting in='height' surfaceScale='2' diffuseConstant='1.3' lighting-color='#ffeeaa'>"
        "    <feDistantLight azimuth='45' elevation='45'/>"
        "  </feDiffuseLighting>"
        "</filter>",
    )
    effect = next((res for res in results if res.metadata.get("filter_type") == "diffuse_lighting"), None)
    assert effect is not None
    assert effect.metadata.get("fallback_assets")


def test_specular_lighting_resvg_path() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f'>"
        "  <feSpecularLighting surfaceScale='3' specularConstant='1' specularExponent='8' lighting-color='#aaddff'>"
        "    <feSpotLight x='20' y='15' z='30' pointsAtX='20' pointsAtY='15' pointsAtZ='0' limitingConeAngle='35'/>"
        "  </feSpecularLighting>"
        "</filter>",
    )
    effect = next((res for res in results if res.metadata.get("filter_type") == "specular_lighting"), None)
    assert effect is not None
    assert effect.metadata.get("fallback_assets")


def test_image_without_href_warns_and_falls_back() -> None:
    service = FilterService()
    results = _resolve(service, "<filter id='f'><feImage/></filter>")
    assert results
    effect = results[0]
    assert effect.fallback == "bitmap"


def test_image_with_href_avoids_fallback() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f' xmlns:xlink='http://www.w3.org/1999/xlink'>"
        "<feImage xlink:href='data:image/png;base64,AA=='/>"
        "</filter>",
    )
    assert results
    effect = results[0]
    assert effect.fallback is None
    assert effect.effect.drawingml.startswith("<!-- svg2ooxml:image")


def test_composite_over_reuses_native_inputs() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f'>"
        "  <feFlood flood-color='#222244' flood-opacity='0.6' result='flood'/>"
        "  <feComposite in='flood' in2='SourceAlpha' operator='in' result='masked'/>"
        "  <feGaussianBlur in='masked' stdDeviation='2' result='blurred'/>"
        "  <feOffset in='blurred' dx='3' dy='4' result='shadow'/>"
        "  <feComposite in='SourceGraphic' in2='shadow' operator='over'/>"
        "</filter>",
    )
    composites = [
        effect
        for effect in results
        if effect.metadata.get("filter_type") == "composite"
        and effect.metadata.get("operator") == "over"
    ]
    assert composites, "expected over composite result"
    final = composites[-1]
    assert final.fallback is None
    assert final.effect.drawingml.startswith("<a:effectLst>")
    assert "<a:outerShdw" in final.effect.drawingml
    assert final.metadata.get("native_support") is True
    assert final.metadata.get("inputs") == ["shadow"]
    source_meta = final.metadata.get("source_metadata", {})
    assert source_meta.get("shadow", {}).get("filter_type") == "offset"


def test_diffuse_lighting_captures_light_source() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f'>"
        "  <feDiffuseLighting surfaceScale='2' diffuseConstant='1.5'>"
        "    <feDistantLight azimuth='45' elevation='30'/>"
        "  </feDiffuseLighting>"
        "</filter>",
    )
    assert results
    effect = results[0]
    assert effect.metadata.get("filter_type") == "diffuse_lighting"
    assert effect.metadata.get("native_support") is False
    assert effect.metadata.get("fallback_reason") == "diffuse_lighting_requires_emf"
    assert effect.fallback == "emf"
    assert "svg2ooxml:emf" in effect.effect.drawingml
    assert effect.strategy == "vector"
    assets = effect.metadata.get("fallback_assets")
    assert assets and assets[0]["type"] == "emf"
    assert assets[0].get("data_hex") or assets[0].get("data")
    assert assets[0].get("metadata", {}).get("filter_type") == "diffuse_lighting"


def test_specular_lighting_serialises_spot_light() -> None:
    service = FilterService()
    results = _resolve(
        service,
        "<filter id='f'>"
        "  <feSpecularLighting surfaceScale='3' specularConstant='0.5' specularExponent='12'>"
        "    <feSpotLight x='0' y='0' z='10' pointsAtX='1' pointsAtY='1' pointsAtZ='0'/>"
        "  </feSpecularLighting>"
        "</filter>",
    )
    assert results
    effect = results[0]
    assert effect.metadata.get("filter_type") == "specular_lighting"
    assert effect.metadata.get("native_support") is False
    assert effect.metadata.get("fallback_reason") == "specular_lighting_requires_emf"
    assert effect.fallback == "emf"
    assert effect.strategy == "vector"
    assets = effect.metadata.get("fallback_assets")
    assert assets and assets[0]["type"] == "emf"
    assert assets[0].get("data_hex") or assets[0].get("data")
    assert assets[0].get("metadata", {}).get("filter_type") == "specular_lighting"
