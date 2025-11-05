"""Tests for text bounding box sizing."""

from svg2ooxml.core.ir.text_converter import TextConverter
from svg2ooxml.ir.text import Run


def test_text_bbox_height_for_18pt_font():
    """Verify text box height accommodates 18pt font (regression test)."""
    runs = [
        Run(
            text="CSS selectors and use element",
            font_family="Arial",
            font_size_pt=18.0,
            rgb="000000",
        )
    ]

    bbox = TextConverter._estimate_text_bbox(runs, origin_x=100, origin_y=100)

    # For 18pt font:
    # - 18pt × (96/72) = 24 pixels
    # - Line height = 24px × 1.5 = 36 pixels
    # - Single line = 36 pixels

    expected_height_px = 36.0
    assert abs(bbox.height - expected_height_px) < 0.1, (
        f"Text box height {bbox.height}px doesn't match expected {expected_height_px}px "
        f"for 18pt font"
    )


def test_text_bbox_height_multiline():
    """Verify text box height accommodates multiple lines."""
    runs = [
        Run(
            text="Line 1\nLine 2\nLine 3",
            font_family="Arial",
            font_size_pt=12.0,
            rgb="000000",
        )
    ]

    bbox = TextConverter._estimate_text_bbox(runs, origin_x=50, origin_y=50)

    # For 12pt font with 3 lines:
    # - 12pt × (96/72) = 16 pixels
    # - Line height = 16px × 1.5 = 24 pixels
    # - 3 lines = 24px × 3 = 72 pixels

    expected_height_px = 72.0
    assert abs(bbox.height - expected_height_px) < 0.1, (
        f"Text box height {bbox.height}px doesn't match expected {expected_height_px}px "
        f"for 3 lines of 12pt font"
    )


def test_text_bbox_height_uses_max_font_size():
    """Verify text box height uses the maximum font size from all runs."""
    runs = [
        Run(text="Small ", font_family="Arial", font_size_pt=12.0, rgb="000000"),
        Run(text="Large", font_family="Arial", font_size_pt=24.0, rgb="000000"),
    ]

    bbox = TextConverter._estimate_text_bbox(runs, origin_x=0, origin_y=0)

    # Should use 24pt (the larger font):
    # - 24pt × (96/72) = 32 pixels
    # - Line height = 32px × 1.5 = 48 pixels

    expected_height_px = 48.0
    assert abs(bbox.height - expected_height_px) < 0.1, (
        f"Text box height {bbox.height}px should use max font size (24pt)"
    )


def test_text_bbox_pt_to_px_conversion():
    """Verify proper point-to-pixel conversion (96 DPI standard)."""
    runs = [
        Run(text="Test", font_family="Arial", font_size_pt=72.0, rgb="000000")
    ]

    bbox = TextConverter._estimate_text_bbox(runs, origin_x=0, origin_y=0)

    # For 72pt font:
    # - 72pt × (96/72) = 96 pixels (exactly 1 inch at 96 DPI)
    # - Line height = 96px × 1.5 = 144 pixels

    expected_height_px = 144.0
    assert abs(bbox.height - expected_height_px) < 0.1, (
        f"Text box height {bbox.height}px doesn't match expected {expected_height_px}px "
        f"(72pt should be 96px after conversion)"
    )


def test_text_bbox_width_estimation():
    """Verify text box width uses reasonable character width estimate."""
    runs = [
        Run(text="Hello", font_family="Arial", font_size_pt=12.0, rgb="000000")
    ]

    bbox = TextConverter._estimate_text_bbox(runs, origin_x=0, origin_y=0)

    # For 12pt font with 5 characters:
    # - 12pt × (96/72) = 16 pixels
    # - Character width ≈ 16px × 0.6 = 9.6px
    # - 5 chars = 9.6px × 5 = 48 pixels

    expected_width_px = 48.0
    assert abs(bbox.width - expected_width_px) < 0.1, (
        f"Text box width {bbox.width}px doesn't match expected {expected_width_px}px "
        f"for 5 characters at 12pt"
    )


def test_text_bbox_empty_runs():
    """Verify empty runs produce zero-size bbox."""
    bbox = TextConverter._estimate_text_bbox([], origin_x=10, origin_y=20)

    assert bbox.x == 10
    assert bbox.y == 20
    assert bbox.width == 0
    assert bbox.height == 0


def test_text_bbox_y_offset_for_baseline():
    """Verify bbox y-coordinate is offset above baseline for ascent."""
    runs = [
        Run(text="Test", font_family="Arial", font_size_pt=12.0, rgb="000000")
    ]

    origin_y = 100.0
    bbox = TextConverter._estimate_text_bbox(runs, origin_x=0, origin_y=origin_y)

    # For 12pt font:
    # - 12pt × (96/72) = 16 pixels
    # - Y offset (ascent) ≈ 16px × 0.8 = 12.8 pixels
    # - bbox.y = origin_y - y_offset = 100 - 12.8 = 87.2

    font_px = 12.0 * (96.0 / 72.0)
    expected_y = origin_y - (font_px * 0.8)

    assert abs(bbox.y - expected_y) < 0.1, (
        f"Bbox y-coordinate {bbox.y} should be offset above baseline {origin_y} "
        f"by ascent (~{font_px * 0.8}px)"
    )
