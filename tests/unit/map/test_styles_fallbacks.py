"""Tests for style metadata fallback normalization."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.color.spaces import ColorSpaceResult
from svg2ooxml.core.ir.policy_hooks import PolicyHooksMixin
from svg2ooxml.core.ir.shape_converters import ShapeConversionMixin
from svg2ooxml.core.styling.style_extractor import StyleExtractor, StyleResult
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.drawingml.bridges import describe_gradient_element
from svg2ooxml.policy.constants import FALLBACK_EMF, FALLBACK_RASTERIZE
from svg2ooxml.services.color_service import ColorNormalizedImage
from svg2ooxml.services.image_service import ImageResource
from svg2ooxml.services.setup import configure_services


def _extractor() -> StyleExtractor:
    # Bypass __init__; _maybe_set_geometry_fallback does not depend on _resolver.
    instance: StyleExtractor = StyleExtractor.__new__(StyleExtractor)  # type: ignore[call-arg]
    instance._resolver = None  # type: ignore[attr-defined]
    instance._tracer = None  # type: ignore[attr-defined]
    return instance


def test_geometry_fallback_maps_rasterize_to_emf() -> None:
    extractor = _extractor()
    metadata: dict[str, object] = {}

    extractor._maybe_set_geometry_fallback(metadata, FALLBACK_RASTERIZE)

    geometry = metadata["policy"]["geometry"]  # type: ignore[index]
    assert geometry["suggest_fallback"] == FALLBACK_EMF


def test_geometry_fallback_preserves_emf() -> None:
    extractor = _extractor()
    metadata: dict[str, object] = {}

    extractor._maybe_set_geometry_fallback(metadata, FALLBACK_EMF)

    geometry = metadata["policy"]["geometry"]  # type: ignore[index]
    assert geometry["suggest_fallback"] == FALLBACK_EMF


def test_gradient_metadata_records_recommended_color_space() -> None:
    services = configure_services()
    gradient_service = services.gradient_service
    assert gradient_service is not None

    gradient_xml = etree.fromstring(
        """
        <linearGradient>
            <stop offset="0%" stop-color="#111111"/>
            <stop offset="50%" stop-color="rgb(128, 10, 200)"/>
            <stop offset="100%" stop-color="#eeeeee"/>
        </linearGradient>
        """
    )

    extractor = _extractor()
    metadata: dict[str, object] = {}
    descriptor = describe_gradient_element(gradient_xml)
    gradient_service.register_gradient("g1", descriptor)
    extractor._record_gradient_metadata(
        gradient_id="g1",
        descriptor=descriptor,
        gradient_service=gradient_service,
        services=services,
        metadata=metadata,
        role="fill",
        context=None,
    )

    paint_analysis = metadata["paint_analysis"]["fill"]["gradient"]  # type: ignore[index]
    assert "color_statistics" in paint_analysis
    stats = paint_analysis["color_statistics"]
    assert stats["recommended_space"] in {"srgb", "linear_rgb"}

    paint_policy = metadata["policy"]["paint"]["fill"]  # type: ignore[index]
    assert paint_policy["recommended_color_space"] in {"srgb", "linear_rgb"}


class _StubColorSpaceService:
    def __init__(self) -> None:
        self._result = ColorSpaceResult(
            data=b"stub",
            mime_type="image/png",
            mode="RGB",
            converted=False,
            warnings=[],
            metadata={"analysis": {"palette": []}},
        )

    def normalize_resource(self, resource: ImageResource, *, normalization: str = "rgb") -> ColorNormalizedImage:
        return ColorNormalizedImage(resource=resource, result=self._result)


class _StubImageService:
    def __init__(self, resource: ImageResource) -> None:
        self._resource = resource

    def resolve(self, _href: str) -> ImageResource:
        return self._resource


class _DummyServices:
    def __init__(self, resource: ImageResource) -> None:
        self.image_service = _StubImageService(resource)
        self.color_space_service = _StubColorSpaceService()


class _StubStyleExtractor:
    """Minimal stub that returns a default StyleResult."""

    def extract(self, element, services, *, context=None):
        return StyleResult(fill=None, stroke=None, opacity=1.0, effects=[], metadata={})


class _DummyConverter(ShapeConversionMixin, PolicyHooksMixin):
    def __init__(self, services: _DummyServices, policy: dict[str, object]) -> None:
        self._services = services
        self._policy_context = {"image": policy}
        self._style_extractor = _StubStyleExtractor()
        self._css_context = None
        self._resvg_tree = None

    def _resolve_clip_ref(self, _element):  # pragma: no cover - simple stub
        return None

    def _resolve_mask_ref(self, _element):  # pragma: no cover - simple stub
        return (None, None)

    def _process_mask_metadata(self, _ir_object):  # pragma: no cover - simple stub
        return None

    def _trace_stage(self, *_args, **_kwargs):  # pragma: no cover - simple stub
        return None


def test_convert_image_attaches_colorspace_metadata() -> None:
    resource = ImageResource(data=b"data", mime_type="image/png", source="stub")
    services = _DummyServices(resource)
    converter = _DummyConverter(services, {"colorspace_normalization": "rgb"})

    element = etree.fromstring('<image href="stub" width="10" height="10" />')
    coord_space = CoordinateSpace()

    image = converter._convert_image(element=element, coord_space=coord_space)

    policy_meta = image.metadata["policy"]["image"]  # type: ignore[index]
    assert "colorspace_metadata" in policy_meta
    assert policy_meta["colorspace_metadata"].get("analysis") == {"palette": []}
