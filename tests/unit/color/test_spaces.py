"""Tests for the color space converter."""

from svg2ooxml.color.spaces import ColorSpaceConverter


def test_converter_reports_unavailable_when_forced() -> None:
    converter = ColorSpaceConverter(force_disable=True)

    result = converter.convert_bytes(b"data", mime_type="image/png")

    assert result.converted is False
    assert any("Pillow not available" in message for message in result.warnings)


def test_converter_handles_invalid_payload_gracefully() -> None:
    converter = ColorSpaceConverter()

    result = converter.convert_bytes(b"not-an-image", mime_type="image/png")

    assert result.converted is False
    assert result.data == b"not-an-image"
    assert result.warnings, "expected a warning message when conversion fails"
