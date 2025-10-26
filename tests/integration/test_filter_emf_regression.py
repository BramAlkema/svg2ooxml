"""Regression tests for EMF filter fallbacks."""

from __future__ import annotations

import hashlib

from lxml import etree

from svg2ooxml.services.filter_service import FilterService


EXPECTED_EMF_DIGESTS: dict[str, str] = {
    "combo": "b9a266b65511ec45fa1ed63caabb3f91395f2a6e",
    "blend": "d0fece35a0303436280fa0f1c8caba92d6ba716c",
    "comp": "4985b41c0bba61f4df05797dd99a2dd5765d8a63",
    "cmm": "dfdadbfe00d1dce897d50c8421e8db3558fc698e",
    "disp": "1e2a7fd86413497baa990a8f4c503db365112b1e",
    "diff": "4212f8bac5070e1d6cde2e1939b358c0667e41c1",
    "turb": "b0ee27cc9973dea3bab3da7f8f69a4a57802050f",
    "conv": "8c9a4a3be870745d35c5578d96d75911c5f41613",
    "spec": "c21085baa1b220e3fc984621779e50877424394b",
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


def test_composite_filter_emf_bytes_stable() -> None:
    filter_markup = (
        "<filter id='combo'>"
        "  <feGaussianBlur stdDeviation='1.2' result='blurred'/>"
        "  <feComposite operator='over' in='SourceGraphic' in2='blurred' result='combined'/>"
        "</filter>"
    )
    digest = _emf_hash(filter_markup, "combo")
    assert digest == EXPECTED_EMF_DIGESTS["combo"]


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


def test_diffuse_lighting_emf_bytes_stable() -> None:
    filter_markup = (
        "<filter id='diff'>"
        "  <feDiffuseLighting surfaceScale='2' diffuseConstant='1.5' lighting-color='#9bb8ff'>"
        "    <feDistantLight azimuth='45' elevation='30'/>"
        "  </feDiffuseLighting>"
        "</filter>"
    )
    digest = _emf_hash(filter_markup, "diff")
    assert digest == EXPECTED_EMF_DIGESTS["diff"]


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


def test_specular_lighting_emf_bytes_stable() -> None:
    filter_markup = (
        "<filter id='spec'>"
        "  <feSpecularLighting surfaceScale='3' specularConstant='0.6' specularExponent='10' lighting-color='#304060'>"
        "    <feSpotLight x='0' y='0' z='10' pointsAtX='1' pointsAtY='1' pointsAtZ='0'/>"
        "  </feSpecularLighting>"
        "</filter>"
    )
    digest = _emf_hash(filter_markup, "spec")
    assert digest == EXPECTED_EMF_DIGESTS["spec"]
