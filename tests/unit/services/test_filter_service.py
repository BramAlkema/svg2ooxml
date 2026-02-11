"""FilterService scaffolding tests."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from lxml import etree

from svg2ooxml.filters.base import FilterResult
from svg2ooxml.filters.registry import FilterRegistry
from svg2ooxml.filters.resvg_bridge import (
    ResolvedFilter,
    build_filter_node,
    resolve_filter_element,
)
from svg2ooxml.render.filters import plan_filter
from svg2ooxml.services.conversion import ConversionServices
from svg2ooxml.services.filter_service import FilterService
from tests.unit.filters.policy import assert_fallback

ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"


def _make_filter_element(markup: str) -> etree._Element:
    return etree.fromstring(f"<svg xmlns='http://www.w3.org/2000/svg'>{markup}</svg>")[0]


def _make_descriptor(markup: str) -> ResolvedFilter:
    return resolve_filter_element(_make_filter_element(markup))


class _NoopRegistry:
    """Simple registry stub returning no rendering results."""

    def render_filter_element(self, element, context):
        return []

    def clone(self):
        return self


class _TraceRecorder:
    """Collect stage events emitted by FilterService tracing."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def record_stage_event(
        self,
        *,
        stage: str,
        action: str,
        subject: str,
        metadata: dict[str, object],
    ) -> None:
        self.events.append(
            {
                "stage": stage,
                "action": action,
                "subject": subject,
                "metadata": dict(metadata),
            }
        )



def test_filter_service_registers_and_requires_definitions() -> None:
    service = FilterService()
    descriptor = _make_descriptor("<filter id='blur'/>")
    service.update_definitions({"blur": descriptor})

    fetched = service.get("blur")
    assert isinstance(fetched, ResolvedFilter)
    assert fetched.filter_id == "blur"
    assert service.require("blur").filter_id == "blur"
    assert list(service.ids()) == ["blur"]


def test_filter_service_clone_preserves_state() -> None:
    service = FilterService()
    service.register_filter("shadow", _make_descriptor("<filter id='shadow'/>"))

    clone = service.clone()
    fetched = clone.get("shadow")
    assert isinstance(fetched, ResolvedFilter)
    assert fetched.filter_id == "shadow"
    assert clone.registry is not None
    assert isinstance(clone.registry, FilterRegistry)


def test_filter_service_binds_policy_engine_from_services() -> None:
    services = ConversionServices()
    policy_engine = object()
    services.register("policy_engine", policy_engine)

    filter_defs = {"blur": _make_filter_element("<filter id='blur'/>")}
    services.register("filters", filter_defs)

    filter_service = FilterService()
    filter_service.bind_services(services)

    assert filter_service.policy_engine is policy_engine
    fetched = filter_service.get("blur")
    assert isinstance(fetched, ResolvedFilter)
    assert fetched.filter_id == "blur"


def test_descriptor_fallback_prefers_vector_hint() -> None:
    service = FilterService(registry=_NoopRegistry())
    service.register_filter("vectorish", _make_descriptor("<filter id='vectorish'><feComponentTransfer/></filter>"))
    service.set_strategy("vector")

    context = {
        "policy": {},
        "resvg_descriptor": {
            "primitive_tags": ["feComponentTransfer"],
            "primitive_count": 1,
            "filter_units": "userSpaceOnUse",
            "primitive_units": "userSpaceOnUse",
            "filter_region": {"x": 0.0, "y": 0.0, "width": 120.0, "height": 80.0},
        },
        "ir_bbox": {"x": 0.0, "y": 0.0, "width": 120.0, "height": 80.0},
    }

    results = service.resolve_effects("vectorish", context=context)

    assert results
    fallback = results[-1]
    assert fallback.strategy == "vector"
    assert fallback.fallback == "emf"
    assert fallback.metadata["descriptor"]["primitive_tags"] == ["feComponentTransfer"]
    assert fallback.metadata["bounds"]["width"] == 120.0


def test_descriptor_fallback_produces_placeholder_when_rendering_absent() -> None:
    service = FilterService(registry=_NoopRegistry())
    service.register_filter("rasterish", _make_descriptor("<filter id='rasterish'><feGaussianBlur/></filter>"))
    service.set_strategy("raster")

    context = {
        "resvg_descriptor": {
            "primitive_tags": ["feGaussianBlur"],
            "primitive_count": 1,
            "filter_units": "objectBoundingBox",
            "primitive_units": "userSpaceOnUse",
            "filter_region": {"x": None, "y": None, "width": None, "height": None},
        },
        "ir_bbox": {"x": 5.0, "y": 6.0, "width": 32.0, "height": 18.0},
    }

    results = service.resolve_effects("rasterish", context=context)

    assert results
    placeholder = results[-1]
    assert placeholder.fallback == "bitmap"
    assert placeholder.strategy in {"raster", "auto"}
    metadata = placeholder.metadata
    renderer = metadata.get("renderer")
    assert renderer in {"placeholder", "skia", "resvg", "raster"} or renderer is None
    if renderer == "resvg":
        assert metadata.get("render_passes", 0) >= 0
        assert metadata.get("width_px", 0) > 0
        assert metadata.get("height_px", 0) > 0
    # The fallback assets list should contain a raster entry
    assets = metadata.get("fallback_assets")
    assert isinstance(assets, list) and assets[0].get("type") == "raster"


def test_raster_adapter_produces_png_asset() -> None:
    service = FilterService(registry=_NoopRegistry())
    filter_descriptor = _make_descriptor(
        "<filter id='skiaTest'><feGaussianBlur stdDeviation='8'/></filter>"
    )
    service.register_filter("skiaTest", filter_descriptor)
    service.set_strategy("raster")

    results = service.resolve_effects("skiaTest")
    assert results

    raster_effect = results[-1]
    metadata = raster_effect.metadata or {}
    assets = metadata.get("fallback_assets")
    assert isinstance(assets, list)
    raster_asset = next((asset for asset in assets if asset.get("type") == "raster"), None)
    assert raster_asset is not None
    assert raster_asset.get("format") == "png"
    raw = raster_asset.get("data")
    assert isinstance(raw, (bytes, bytearray))
    # PNG header check
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_resvg_path_returns_bitmap_result() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor("<filter id='resvg'><feGaussianBlur stdDeviation='2'/></filter>")
    service.register_filter("resvg", descriptor)

    context = {
        "ir_bbox": {"x": 0.0, "y": 0.0, "width": 32.0, "height": 24.0},
    }

    results = service.resolve_effects("resvg", context=context)

    assert results
    assert [result.strategy for result in results] == ["native"]
    effect = results[0]
    metadata = effect.metadata or {}
    assert metadata.get("filter_type") == "gaussian_blur"
    assert metadata.get("native_support") is True
    assert not metadata.get("fallback_assets")


def test_resvg_promotes_blend_to_emf_asset() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='blend'><feBlend mode='multiply' in='SourceGraphic' in2='SourceAlpha'/></filter>"
    )
    service.register_filter("blend", descriptor)
    service.set_strategy("resvg")

    results = service.resolve_effects("blend")

    assert results
    effect = results[0]
    assert effect.strategy in {"vector", "emf", "resvg"}
    assert effect.fallback in {"emf", "bitmap", "raster"}
    metadata = effect.metadata or {}
    assets = metadata.get("fallback_assets") or []
    assert assets and assets[0].get("type") in {"emf", "raster"}


def test_resvg_promotes_composite_to_emf_asset() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='composite'><feComposite in='SourceGraphic' in2='SourceAlpha' operator='over'/></filter>"
    )
    service.register_filter("composite", descriptor)
    service.set_strategy("resvg")

    results = service.resolve_effects("composite")

    assert results
    effect = results[0]
    assert effect.strategy in {"vector", "emf", "resvg"}
    assert effect.fallback in {"emf", "bitmap", "raster"}
    metadata = effect.metadata or {}
    primitives = metadata.get("primitives") or []
    assert any(tag.lower() == "fecomposite" for tag in primitives)


def test_resvg_promotes_color_matrix_to_emf_asset() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='matrix'><feColorMatrix type='matrix' values='1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 1 0'/></filter>"
    )
    service.register_filter("matrix", descriptor)
    service.set_strategy("resvg")

    results = service.resolve_effects("matrix")

    assert results
    effect = results[0]
    assert_fallback(effect, modern=None, legacy="emf")
    metadata = effect.metadata or {}
    if effect.fallback == "emf":
        assert metadata.get("filter_type") == "color_matrix"
        assert metadata.get("value_count") == 20
    else:
        assert metadata.get("renderer") == "resvg"
        assert metadata.get("resvg_promotion") in {"native", "vector", "emf"}
        plan_primitives = metadata.get("plan_primitives") or []
        assert any(
            isinstance(item, dict) and str(item.get("tag", "")).lower() == "fecolormatrix"
            for item in plan_primitives
        )


def test_resvg_lighting_metadata_includes_light_params() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='light'>"
        "  <feDiffuseLighting surfaceScale='3' diffuseConstant='1.2' lighting-color='#ffeeaa'>"
        "    <feSpotLight x='1' y='2' z='3' pointsAtX='4' pointsAtY='5' pointsAtZ='6' specularExponent='7' limitingConeAngle='30'/>"
        "  </feDiffuseLighting>"
        "</filter>"
    )
    service.register_filter("light", descriptor)
    service.set_strategy("resvg")

    results = service.resolve_effects("light", context={"ir_bbox": {"x": 0, "y": 0, "width": 64, "height": 48}})

    assert results
    metadata = results[0].metadata or {}
    descriptor_meta = metadata.get("descriptor") or {}
    primitive_meta = (descriptor_meta.get("primitive_metadata") or [{}])[0]
    assert primitive_meta.get("light_type") in {"spotlight", None}
    assert primitive_meta.get("spotlight_x") == "1"
    assert primitive_meta.get("spotlight_limitingConeAngle") == "30"


def test_resvg_promotes_morphology_soft_edge() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='morph'><feMorphology operator='erode' radius='2' in='SourceGraphic'/></filter>"
    )
    service.register_filter("morph", descriptor)
    service.set_strategy("resvg")

    results = service.resolve_effects("morph")

    assert results
    effect = results[0]
    assert effect.strategy in {"vector", "resvg", "native"}
    metadata = effect.metadata or {}
    assert metadata.get("resvg_promotion") == "vector"
    assert metadata.get("filter_type") == "morphology"


def test_resvg_promotes_flood_tile_stack() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='tile'>"
        "  <feFlood flood-color='#00ffff' result='fill'/>"
        "  <feTile in='fill' result='tiled'/>"
        "</filter>"
    )
    service.register_filter("tile", descriptor)
    service.set_strategy("resvg")

    results = service.resolve_effects("tile")

    assert results
    effect = results[0]
    metadata = effect.metadata or {}
    assert metadata.get("promotion_plan_length") == 2
    assert metadata.get("promotion_primitives") == ["feFlood", "feTile"]
    assert metadata.get("resvg_promotion") in {"vector", "emf"}


def test_resvg_promotes_component_transfer_merge_chain() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='advanced'>"
        "  <feFlood flood-color='#ff0000' result='fill'/>"
        "  <feComponentTransfer in='fill' result='tint'>"
        "    <feFuncR type='table' tableValues='0 1'/>"
        "    <feFuncG type='table' tableValues='0 1'/>"
        "    <feFuncB type='table' tableValues='0 1'/>"
        "  </feComponentTransfer>"
        "  <feOffset dx='3' dy='-2' in='tint' result='offsetFill'/>"
        "  <feComposite in='offsetFill' in2='SourceGraphic' operator='over' result='comp'/>"
        "  <feMerge>"
        "    <feMergeNode in='comp'/>"
        "    <feMergeNode in='SourceGraphic'/>"
        "  </feMerge>"
        "</filter>"
    )
    service.register_filter("advanced", descriptor)
    service.set_strategy("resvg")

    results = service.resolve_effects("advanced")

    assert results
    effect = results[0]
    metadata = effect.metadata or {}
    assert metadata.get("promotion_plan_length") == 5
    assert metadata.get("promotion_primitives") == [
        "feFlood",
        "feComponentTransfer",
        "feOffset",
        "feComposite",
        "feMerge",
    ]
    assert metadata.get("resvg_promotion") in {"vector", "emf"}
    plan_meta = metadata.get("plan_primitives") or []
    assert any(entry.get("metadata") for entry in plan_meta if entry.get("tag") == "feComponentTransfer")


def test_resvg_tracer_emits_plan_characteristics() -> None:
    pytest.importorskip("skia")

    tracer = _TraceRecorder()
    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='lighting'>"
        "  <feDiffuseLighting surfaceScale='3' diffuseConstant='1.2' result='light'>"
        "    <fePointLight x='2' y='3' z='5'/>"
        "  </feDiffuseLighting>"
        "  <feComposite in='light' in2='SourceGraphic' operator='over'/>"
        "</filter>"
    )
    service.register_filter("lighting", descriptor)
    service.set_strategy("resvg")

    context = {
        "tracer": tracer,
        "ir_bbox": {"x": 0.0, "y": 0.0, "width": 64.0, "height": 48.0},
    }
    results = service.resolve_effects("lighting", context=context)

    assert results
    plan_events = [event for event in tracer.events if event["action"] == "resvg_plan_characterised"]
    assert plan_events
    payload = plan_events[-1]["metadata"]
    assert payload.get("primitive_count") == 2
    assert payload.get("primitive_tags") == ["feDiffuseLighting", "feComposite"]
    plan_primitives = payload.get("plan_primitives")
    assert isinstance(plan_primitives, list) and plan_primitives
    diffuse = plan_primitives[0]
    assert diffuse.get("tag") == "feDiffuseLighting"
    extras = diffuse.get("metadata") or {}
    light = extras.get("light") or {}
    assert (light.get("type") or "").startswith("point")


def test_resvg_lighting_candidate_event() -> None:
    pytest.importorskip("skia")

    tracer = _TraceRecorder()
    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='lighting'>"
        "  <feDiffuseLighting surfaceScale='2' diffuseConstant='1.1' result='lit'>"
        "    <fePointLight x='4' y='4' z='6'/>"
        "  </feDiffuseLighting>"
        "  <feComposite in='lit' in2='SourceGraphic' operator='over'/>"
        "</filter>"
    )
    service.register_filter("lighting", descriptor)
    service.set_strategy("resvg")

    context = {
        "tracer": tracer,
        "ir_bbox": {"x": 0.0, "y": 0.0, "width": 32.0, "height": 32.0},
    }
    results = service.resolve_effects("lighting", context=context)

    assert results
    lighting_events = [event for event in tracer.events if event["action"] == "resvg_lighting_promoted"]
    assert lighting_events
    lighting_meta = lighting_events[-1]["metadata"] or {}
    assert lighting_meta.get("primitive") == "fediffuselighting"
    plan_extra = lighting_meta.get("plan_extra") or {}
    assert plan_extra.get("light", {}).get("type")


def test_resvg_promotes_diffuse_lighting_chain() -> None:
    pytest.importorskip("skia")

    tracer = _TraceRecorder()
    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='lit'>"
        "  <feDiffuseLighting surfaceScale='2' diffuseConstant='1.2' lighting-color='#ffeeaa' result='light'>"
        "    <fePointLight x='3' y='4' z='5'/>"
        "  </feDiffuseLighting>"
        "  <feComposite in='light' in2='SourceGraphic' operator='over'/>"
        "</filter>"
    )
    service.register_filter("lit", descriptor)
    service.set_strategy("resvg")

    results = service.resolve_effects("lit", context={"tracer": tracer, "ir_bbox": {"x": 0, "y": 0, "width": 64, "height": 48}})

    assert results
    effect = results[0]
    assert effect.fallback in ("emf", "bitmap")
    meta = effect.metadata or {}
    if effect.fallback == "emf":
        assert meta.get("resvg_promotion") == "emf"
        assert meta.get("lighting_primitives") == ["fediffuselighting"]
    else:
        # Bitmap path: resvg renders lighting natively as PNG
        assert meta.get("renderer") == "resvg"
        assert "feDiffuseLighting" in (meta.get("primitives") or [])
    lighting_events = [event for event in tracer.events if event["action"] == "resvg_lighting_promoted"]
    assert lighting_events


def test_resvg_promotes_specular_lighting_chain() -> None:
    pytest.importorskip("skia")

    tracer = _TraceRecorder()
    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='spec'>"
        "  <feSpecularLighting surfaceScale='3' specularConstant='1.5' specularExponent='8' lighting-color='#88ccff' result='spec'>"
        "    <feSpotLight x='8' y='-4' z='15' pointsAtX='24' pointsAtY='12' pointsAtZ='0' limitingConeAngle='40'/>"
        "  </feSpecularLighting>"
        "  <feComposite in='spec' in2='SourceGraphic' operator='over'/>"
        "</filter>"
    )
    service.register_filter("spec", descriptor)
    service.set_strategy("resvg")

    results = service.resolve_effects("spec", context={"tracer": tracer, "ir_bbox": {"x": 0, "y": 0, "width": 64, "height": 48}})

    assert results
    effect = results[0]
    assert effect.fallback in ("emf", "bitmap")
    meta = effect.metadata or {}
    if effect.fallback == "emf":
        assert meta.get("resvg_promotion") == "emf"
        assert meta.get("lighting_primitives") == ["fespecularlighting"]
    else:
        # Bitmap path: resvg renders lighting natively as PNG
        assert meta.get("renderer") == "resvg"
        assert "feSpecularLighting" in (meta.get("primitives") or [])
    lighting_events = [event for event in tracer.events if event["action"] == "resvg_lighting_promoted"]
    assert any(event["metadata"].get("primitive") == "fespecularlighting" for event in lighting_events)

def test_fixture_turbulence_descriptor_preserves_stitch_metadata() -> None:
    svg_path = ASSETS_DIR / "turbulence_stitch.svg"
    tree = etree.parse(str(svg_path))
    filter_element = tree.find(".//{http://www.w3.org/2000/svg}filter")
    assert filter_element is not None
    descriptor = resolve_filter_element(filter_element)

    filter_node = build_filter_node(descriptor)
    plan = plan_filter(filter_node)
    assert plan is not None
    primitive_tags = [primitive.tag for primitive in plan.primitives]
    assert primitive_tags == ["feTurbulence", "feComposite"]
    turbulence_meta = plan.primitives[0].extra
    assert turbulence_meta.get("stitch") == "stitch"

def test_resvg_promotion_blocked_by_merge_policy_limit() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='advanced'>"
        "  <feFlood flood-color='#ff0000' result='fill'/>"
        "  <feComponentTransfer in='fill' result='tint'>"
        "    <feFuncR type='table' tableValues='0 1'/>"
        "  </feComponentTransfer>"
        "  <feOffset dx='3' dy='-2' in='tint' result='offsetFill'/>"
        "  <feComposite in='offsetFill' in2='SourceGraphic' operator='over' result='comp'/>"
        "  <feMerge>"
        "    <feMergeNode in='comp'/>"
        "    <feMergeNode in='SourceGraphic'/>"
        "  </feMerge>"
        "</filter>"
    )
    service.register_filter("advanced", descriptor)
    service.set_strategy("resvg")

    tracer = _TraceRecorder()
    context = {
        "policy": {"primitives": {"femerge": {"max_merge_inputs": 1}}},
        "tracer": tracer,
    }
    results = service.resolve_effects("advanced", context=context)

    assert results
    metadata = results[0].metadata or {}
    assert metadata.get("resvg_promotion") is None
    blocked = [
        event
        for event in tracer.events
        if event["action"] == "resvg_promotion_policy_blocked"
    ]
    assert blocked
    payload = blocked[-1]["metadata"]
    assert payload.get("primitive") == "femerge"
    assert payload.get("rule") == "max_merge_inputs"


def test_resvg_promotes_flood_composite_stack() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='stack'>"
        "  <feFlood flood-color='#ff0000' result='flood'/>"
        "  <feComposite in='flood' in2='SourceGraphic' operator='over'/>"
        "</filter>"
    )
    service.register_filter("stack", descriptor)
    service.set_strategy("resvg")

    results = service.resolve_effects("stack")

    assert results
    effect = results[0]
    assert effect.fallback in {None, "emf", "bitmap", "raster"}
    metadata = effect.metadata or {}
    assert metadata.get("promotion_plan_length") == 2
    assert metadata.get("promotion_primitives") == ["feFlood", "feComposite"]
    if metadata.get("fallback_assets"):
        assets = metadata.get("fallback_assets") or []
        assert assets[0].get("type") in {"emf", "raster"}


def test_resvg_promotion_blocked_by_offset_distance_policy() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='offset-policy'>"
        "  <feFlood flood-color='#ff0000' result='flood'/>"
        "  <feOffset in='flood' dx='8' dy='6' result='shifted'/>"
        "  <feComposite in='shifted' in2='SourceGraphic' operator='over'/>"
        "</filter>"
    )
    service.register_filter("offset-policy", descriptor)
    service.set_strategy("resvg")

    tracer = _TraceRecorder()
    context = {
        "policy": {"primitives": {"feoffset": {"max_offset_distance": 5.0}}},
        "tracer": tracer,
    }
    results = service.resolve_effects("offset-policy", context=context)

    assert results
    metadata = results[0].metadata or {}
    assert metadata.get("resvg_promotion") is None
    blocked = [
        event
        for event in tracer.events
        if event["action"] == "resvg_promotion_policy_blocked"
    ]
    assert blocked
    payload = blocked[-1]["metadata"]
    assert payload.get("primitive") == "feoffset"
    assert payload.get("rule") == "max_offset_distance"


def test_resvg_promotion_disabled_by_policy() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor("<filter id='blend'><feBlend mode='screen'/></filter>")
    service.register_filter("blend", descriptor)
    service.set_strategy("resvg")

    context = {
        "policy": {"primitives": {"feblend": {"allow_promotion": False}}},
    }

    results = service.resolve_effects("blend", context=context)

    assert results
    effect = results[0]
    assert effect.fallback == "bitmap" or effect.metadata.get("resvg_promotion") is None
    metadata = effect.metadata or {}
    assert metadata.get("resvg_promotion") is None


def test_resvg_promotion_respects_arithmetic_coeff_limits() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='arith'>"
        "  <feFlood flood-color='#00ff00' result='fill'/>"
        "  <feComposite in='fill' in2='SourceGraphic' operator='arithmetic' k1='1.2'/>"
        "</filter>"
    )
    service.register_filter("arith", descriptor)
    service.set_strategy("resvg")

    limited_context = {
        "policy": {"primitives": {"fecomposite": {"max_arithmetic_coeff": 0.5}}},
    }

    limited_results = service.resolve_effects("arith", context=limited_context)
    assert limited_results
    limited_metadata = limited_results[0].metadata or {}
    assert limited_metadata.get("resvg_promotion") is None


def test_promotion_policy_allows_blocks_arithmetic_coefficients() -> None:
    result = FilterResult(
        success=True,
        fallback="emf",
        metadata={"operator": "arithmetic", "k1": 1.2, "k2": 0.0, "k3": 0.0, "k4": 0.0},
    )

    assert not FilterService._promotion_policy_allows("fecomposite", result, {"max_arithmetic_coeff": 0.5})
    assert FilterService._promotion_policy_allows("fecomposite", result, {"max_arithmetic_coeff": 2.0})


def test_promotion_policy_allows_enforces_additional_limits() -> None:
    offset = FilterResult(success=True, fallback="emf", metadata={"dx": 10.0, "dy": 4.0})
    assert not FilterService._promotion_policy_allows("feoffset", offset, {"max_offset_distance": 5.0})
    assert FilterService._promotion_policy_allows("feoffset", offset, {"max_offset_distance": 12.0})
    violation = FilterService._promotion_policy_violation("feoffset", offset, {"max_offset_distance": 5.0})
    assert violation == {
        "rule": "max_offset_distance",
        "limit": 5.0,
        "observed": pytest.approx(math.hypot(10.0, 4.0)),
        "dx": 10.0,
        "dy": 4.0,
    }

    merge = FilterResult(success=True, fallback="emf", metadata={"inputs": ["a", "b", "c"]})
    assert not FilterService._promotion_policy_allows("femerge", merge, {"max_merge_inputs": 2})
    assert FilterService._promotion_policy_allows("femerge", merge, {"max_merge_inputs": 3})
    violation = FilterService._promotion_policy_violation("femerge", merge, {"max_merge_inputs": 2})
    assert violation == {"rule": "max_merge_inputs", "limit": 2, "observed": 3}

    component = FilterResult(
        success=True,
        fallback="emf",
        metadata={
            "functions": [
                {"channel": "r", "params": {"values": [0.0, 1.0, 2.0]}},
                {"channel": "g", "params": {"values": [0.0, 1.0]}},
                {"channel": "b", "params": {"values": [0.0]}},
            ]
        },
    )
    assert not FilterService._promotion_policy_allows(
        "fecomponenttransfer",
        component,
        {"max_component_functions": 2},
    )
    violation_funcs = FilterService._promotion_policy_violation(
        "fecomponenttransfer",
        component,
        {"max_component_functions": 2},
    )
    assert violation_funcs == {"rule": "max_component_functions", "limit": 2, "observed": 3}
    assert not FilterService._promotion_policy_allows(
        "fecomponenttransfer",
        component,
        {"max_component_table_values": 2},
    )
    assert FilterService._promotion_policy_allows(
        "fecomponenttransfer",
        component,
        {"max_component_functions": 5, "max_component_table_values": 4},
    )
    violation = FilterService._promotion_policy_violation(
        "fecomponenttransfer",
        component,
        {"max_component_table_values": 2},
    )
    assert violation == {"rule": "max_component_table_values", "limit": 2, "observed": 3, "channel": "r"}

    convolve = FilterResult(
        success=True,
        fallback="emf",
        metadata={"kernel": [1.0] * 10, "order": (5, 3)},
    )
    assert not FilterService._promotion_policy_allows("feconvolvematrix", convolve, {"max_convolve_kernel": 9})
    assert not FilterService._promotion_policy_allows("feconvolvematrix", convolve, {"max_convolve_order": 12})
    assert FilterService._promotion_policy_allows(
        "feconvolvematrix",
        convolve,
        {"max_convolve_kernel": 12, "max_convolve_order": 20},
    )
    violation = FilterService._promotion_policy_violation(
        "feconvolvematrix",
        convolve,
        {"max_convolve_kernel": 9},
    )
    assert violation == {"rule": "max_convolve_kernel", "limit": 9, "observed": 10}


def test_resvg_policy_disable_prevents_resvg_execution() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='lighting'><feDiffuseLighting surfaceScale='2' diffuseConstant='1.5'>"
        "<feDistantLight azimuth='30' elevation='45'/></feDiffuseLighting></filter>"
    )
    service.register_filter("lighting", descriptor)

    context = {
        "ir_bbox": {"x": 0.0, "y": 0.0, "width": 64.0, "height": 48.0},
        "policy": {"primitives": {"fediffuselighting": {"allow_resvg": False}}},
    }

    results = service.resolve_effects("lighting", context=context)

    assert results
    assert all(result.strategy != "resvg" for result in results)


def test_resvg_policy_max_pixels_blocks_large_surfaces() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='lighting'><feDiffuseLighting surfaceScale='2' diffuseConstant='1.5'>"
        "<feDistantLight azimuth='30' elevation='45'/></feDiffuseLighting></filter>"
    )
    service.register_filter("lighting", descriptor)

    context = {
        "ir_bbox": {"x": 0.0, "y": 0.0, "width": 256.0, "height": 256.0},
        "policy": {"primitives": {"fediffuselighting": {"max_pixels": 10_000}}},
    }

    results = service.resolve_effects("lighting", context=context)

    assert results
    assert all(result.strategy != "resvg" for result in results)


def test_legacy_strategy_skips_resvg_path() -> None:
    service = FilterService(registry=_NoopRegistry())
    service.set_strategy("legacy")
    descriptor = _make_descriptor("<filter id='legacy'><feGaussianBlur stdDeviation='2'/></filter>")
    service.register_filter("legacy", descriptor)

    results = service.resolve_effects("legacy")

    assert results
    assert all(result.strategy != "resvg" for result in results)


def test_resvg_strategy_prefers_resvg_only() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    service.set_strategy("resvg")
    descriptor = _make_descriptor("<filter id='r'><feFlood flood-color='#112233'/></filter>")
    service.register_filter("r", descriptor)

    results = service.resolve_effects("r")

    assert len(results) == 1
    result = results[0]
    assert result.strategy in {"resvg", "vector", "native"}
    metadata = result.metadata or {}
    assert metadata.get("resvg_promotion") in {"vector", "emf"}
