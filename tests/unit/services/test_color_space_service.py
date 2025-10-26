"""Tests for the color space service."""

from __future__ import annotations

import io

import pytest

from svg2ooxml.color import (
    ADVANCED_COLOR_ENGINE_AVAILABLE,
    ensure_advanced_color_engine,
)
from svg2ooxml.color.spaces import ColorSpaceResult
from svg2ooxml.services import configure_services
from svg2ooxml.services.color_service import ColorSpaceService
from svg2ooxml.services.image_service import ImageResource

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency
    Image = None  # type: ignore[assignment]


class StubConverter:
    def __init__(self) -> None:
        self.available = False

    def convert_bytes(self, data: bytes, *, mime_type: str | None = None, target_mode: str = "RGB") -> ColorSpaceResult:
        return ColorSpaceResult(
            data=data,
            mime_type=mime_type or "application/octet-stream",
            mode=None,
            converted=False,
            warnings=["stub converter"],
        )


def test_color_space_service_returns_original_when_no_conversion() -> None:
    resource = ImageResource(data=b"payload", mime_type="image/png")
    service = ColorSpaceService(converter=StubConverter())

    normalised = service.normalize_resource(resource, normalization="rgb")

    assert normalised.resource is resource
    assert normalised.result.converted is False
    assert normalised.result.warnings
    assert normalised.result.metadata["policy_normalization"] == "rgb"


def test_color_space_service_registered_in_container() -> None:
    services = configure_services()

    assert services.color_space_service is not None


def test_color_space_service_skip_normalization_returns_passthrough() -> None:
    resource = ImageResource(data=b"payload", mime_type="image/png")
    service = ColorSpaceService(converter=StubConverter())

    normalised = service.normalize_resource(resource, normalization="skip")

    assert normalised.resource is resource
    assert normalised.result.metadata["policy_normalization"] == "skip"
    assert normalised.result.converted is False
    assert normalised.result.warnings


def test_color_space_service_perceptual_normalization() -> None:
    if Image is None:
        pytest.skip("Pillow not installed")
    pytest.importorskip("numpy")
    pytest.importorskip("colorspacious")
    if not ADVANCED_COLOR_ENGINE_AVAILABLE:
        pytest.skip("advanced color engine unavailable")
    ensure_advanced_color_engine()

    image = Image.new("RGBA", (4, 4))
    pixels = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 0, 255),
    ]
    image.putdata(pixels * 4)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    resource = ImageResource(data=buffer.getvalue(), mime_type="image/png")
    service = ColorSpaceService()

    normalised = service.normalize_resource(resource, normalization="perceptual")

    assert normalised.resource.mime_type == "image/png"
    assert normalised.result.converted is True
    metadata = normalised.result.metadata
    assert metadata["policy_normalization"] == "perceptual"
    assert "palette" in metadata
    perceptual_meta = metadata.get("perceptual")
    assert perceptual_meta is not None
    assert perceptual_meta.get("applied") is True
    assert perceptual_meta.get("space") == "linear_rgb"
