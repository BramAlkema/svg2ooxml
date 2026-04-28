"""Tests for shared RGBA8 pixel helpers."""

from __future__ import annotations

from svg2ooxml.render.rgba import encode_rgba8_png, source_over_straight_rgba8_pixel


def test_source_over_straight_rgba8_pixel_composites_over_transparent() -> None:
    pixels = bytearray(4)

    source_over_straight_rgba8_pixel(
        pixels,
        width_px=1,
        x=0,
        y=0,
        color=(255, 0, 0),
        alpha=0.5,
    )

    assert tuple(pixels) == (255, 0, 0, 128)


def test_source_over_straight_rgba8_pixel_composites_over_opaque() -> None:
    pixels = bytearray([0, 0, 255, 255])

    source_over_straight_rgba8_pixel(
        pixels,
        width_px=1,
        x=0,
        y=0,
        color=(255, 0, 0),
        alpha=0.5,
    )

    assert tuple(pixels) == (128, 0, 128, 255)


def test_encode_rgba8_png_writes_png_signature() -> None:
    png = encode_rgba8_png(bytearray([255, 0, 0, 255]), 1, 1)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"IHDR" in png[:32]
