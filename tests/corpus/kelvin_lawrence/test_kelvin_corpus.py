"""Kelvin Lawrence SVG corpus validation tests.

Tests 45 hand-crafted SVGs from https://www.kelvinlawrence.net/svg/
covering animations, transforms, text, gradients, filters, clipping,
masking, patterns, and complex compositions.

Source: 860-sample corpus, representative subset selected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from svg2ooxml.public import SvgToPptxExporter

CORPUS_DIR = Path(__file__).parent
SVGS = sorted(CORPUS_DIR.glob("*.svg"))


@pytest.fixture(scope="module")
def exporter():
    return SvgToPptxExporter(geometry_mode="legacy")


@pytest.mark.integration
@pytest.mark.parametrize("svg_path", SVGS, ids=[s.stem for s in SVGS])
def test_kelvin_corpus_converts_and_validates(svg_path: Path, exporter, tmp_path):
    """Each Kelvin Lawrence SVG converts to valid OOXML."""
    out = tmp_path / f"{svg_path.stem}.pptx"
    exporter.convert_file(svg_path, out)

    assert out.exists(), f"PPTX not created for {svg_path.name}"
    assert out.stat().st_size > 0, f"PPTX empty for {svg_path.name}"

    try:
        from openxml_audit import validate_pptx

        result = validate_pptx(str(out))
        assert result.is_valid, (
            f"{svg_path.name} failed validation: "
            + "; ".join(str(e) for e in result.errors[:3])
        )
    except ImportError:
        pytest.skip("openxml-audit not installed")
