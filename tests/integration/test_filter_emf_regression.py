"""Regression tests for EMF filter fallbacks."""

from __future__ import annotations

import hashlib

from lxml import etree

from svg2ooxml.services.filter_service import FilterService

EXPECTED_EMF_DIGESTS: dict[str, str] = {
    "blend": "7e7f3a7767f9ead23ac7d9ac31c491532fe8fbee",
    "comp": "b9dc0f5f63ec5b1395ccb8661fa075f7efb3d2b9",
    "cmm": "a18f5ef909dc192d0937e0ad5e18818d0aa198b7",
    "disp": "de0c077075581603d6fad4cfb5d0696b1c6c9834",
    "turb": "a6a863ec18fbf60200f41ab6901f5dc636fc8077",
    "conv": "949b74a65438d77da56118b339e2a5b373e3707e",
}


def _emf_hash(filter_markup: str, filter_id: str) -> str:
    service = FilterService()
    service.register_filter(filter_id, etree.fromstring(filter_markup))
    results = service.resolve_effects(filter_id)
    vector_results = [res for res in results if res.fallback == "emf"]
    assert vector_results, "expected an EMF fallback"
    asset = vector_results[-1].metadata["fallback_assets"][0]
    data_hex = asset.get("data_hex")
    if not data_hex:
        raw_bytes = asset.get("data")
        assert isinstance(raw_bytes, (bytes, bytearray)), "expected EMF bytes in fallback asset"
        data = bytes(raw_bytes)
    else:
        data = bytes.fromhex(data_hex)
    return hashlib.sha1(data).hexdigest()


def _assert_lighting_avoids_emf(filter_markup: str, filter_id: str) -> None:
    service = FilterService()
    service.register_filter(filter_id, etree.fromstring(filter_markup))
    results = service.resolve_effects(filter_id)
    assert results
    assert all(res.fallback != "emf" for res in results)
    assert any(
        (res.strategy == "native" and res.fallback is None)
        or res.fallback in {"raster", "bitmap"}
        for res in results
    )


def test_composite_filter_prefers_native() -> None:
    filter_markup = (
        "<filter id='combo'>"
        "  <feGaussianBlur stdDeviation='1.2' result='blurred'/>"
        "  <feComposite operator='over' in='SourceGraphic' in2='blurred' result='combined'/>"
        "</filter>"
    )
    service = FilterService()
    service.register_filter("combo", etree.fromstring(filter_markup))
    results = service.resolve_effects("combo")
    assert results
    assert all(res.fallback != "emf" for res in results)
    assert any(res.strategy == "native" for res in results)


def test_blend_filter_emf_bytes_stable() -> None:
    filter_markup = (
        "<filter id='blend'>"
        "  <feColorMatrix type='saturate' values='0.5' result='sat'/>"
        "  <feGaussianBlur stdDeviation='1.5' result='blur'/>"
        "  <feBlend mode='multiply' in='sat' in2='blur' result='blended'/>"
        "</filter>"
    )
    digest = _emf_hash(filter_markup, "blend")
    assert digest == EXPECTED_EMF_DIGESTS["blend"]


def test_component_transfer_emf_bytes_stable() -> None:
    filter_markup = (
        "<filter id='comp'>"
        "  <feComponentTransfer>"
        "    <feFuncR type='linear' slope='1.1' intercept='0.05'/>"
        "    <feFuncG type='gamma' amplitude='0.8' exponent='1.6' offset='0.02'/>"
        "    <feFuncB type='table' tableValues='0 0.25 0.75 1'/>"
        "    <feFuncA type='discrete' tableValues='0 0.5 1'/>"
        "  </feComponentTransfer>"
        "</filter>"
    )
    digest = _emf_hash(filter_markup, "comp")
    assert digest == EXPECTED_EMF_DIGESTS["comp"]


def test_color_matrix_matrix_emf_bytes_stable() -> None:
    filter_markup = (
        "<filter id='cmm'>"
        "  <feColorMatrix type='matrix' values='" + " ".join(["1"] * 20) + "'/>"
        "</filter>"
    )
    digest = _emf_hash(filter_markup, "cmm")
    assert digest == EXPECTED_EMF_DIGESTS["cmm"]


def test_displacement_map_emf_bytes_stable() -> None:
    filter_markup = (
        "<filter id='disp'>"
        "  <feDisplacementMap in='SourceGraphic' in2='map' scale='18' xChannelSelector='R' yChannelSelector='G'/>"
        "</filter>"
    )
    digest = _emf_hash(filter_markup, "disp")
    assert digest == EXPECTED_EMF_DIGESTS["disp"]


def test_diffuse_lighting_avoids_emf_output() -> None:
    filter_markup = (
        "<filter id='diff'>"
        "  <feDiffuseLighting surfaceScale='2' diffuseConstant='1.5' lighting-color='#9bb8ff'>"
        "    <feDistantLight azimuth='45' elevation='30'/>"
        "  </feDiffuseLighting>"
        "</filter>"
    )
    _assert_lighting_avoids_emf(filter_markup, "diff")


def test_turbulence_emf_bytes_stable() -> None:
    filter_markup = (
        "<filter id='turb'>"
        "  <feTurbulence baseFrequency='0.05 0.15' numOctaves='3' seed='4.2' type='fractalNoise' stitchTiles='stitch'/>"
        "</filter>"
    )
    digest = _emf_hash(filter_markup, "turb")
    assert digest == EXPECTED_EMF_DIGESTS["turb"]


def test_convolve_matrix_emf_bytes_stable() -> None:
    filter_markup = (
        "<filter id='conv'>"
        "  <feConvolveMatrix order='3 3' kernelMatrix='0 -1 0 -1 5 -1 0 -1 0' divisor='1' bias='0.1'/>"
        "</filter>"
    )
    digest = _emf_hash(filter_markup, "conv")
    assert digest == EXPECTED_EMF_DIGESTS["conv"]


def test_specular_lighting_avoids_emf_output() -> None:
    filter_markup = (
        "<filter id='spec'>"
        "  <feSpecularLighting surfaceScale='3' specularConstant='0.6' specularExponent='10' lighting-color='#304060'>"
        "    <feSpotLight x='0' y='0' z='10' pointsAtX='1' pointsAtY='1' pointsAtZ='0'/>"
        "  </feSpecularLighting>"
        "</filter>"
    )
    _assert_lighting_avoids_emf(filter_markup, "spec")
