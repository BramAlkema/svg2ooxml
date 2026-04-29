"""Kelvin Lawrence SVG corpus validation tests.

Tests hand-crafted SVGs from https://www.kelvinlawrence.net/svg/
covering animations, transforms, text, gradients, filters, clipping,
masking, patterns, and complex compositions.

SVGs are downloaded on first run (not redistributed).
Run `python -m tests.corpus.kelvin_lawrence.download_corpus` to prefetch.
"""

from __future__ import annotations

import pytest

from svg2ooxml.public import SvgToPptxExporter

from .download_corpus import corpus_svgs


@pytest.fixture(scope="module")
def svgs():
    paths = corpus_svgs()
    if not paths:
        pytest.skip("Kelvin Lawrence corpus not available (network required)")
    return paths


@pytest.fixture(scope="module")
def exporter():
    return SvgToPptxExporter(geometry_mode="legacy")


@pytest.mark.integration
@pytest.mark.requires_network
def test_kelvin_corpus_converts_and_validates(svgs, exporter, tmp_path_factory):
    """Each Kelvin Lawrence SVG converts to valid OOXML."""
    tmp = tmp_path_factory.mktemp("kelvin")
    failures: list[str] = []

    for svg_path in svgs:
        out = tmp / f"{svg_path.stem}.pptx"
        try:
            exporter.convert_file(svg_path, out)
            assert out.exists() and out.stat().st_size > 0
        except Exception as e:
            failures.append(f"{svg_path.name}: ERR {type(e).__name__}: {e}")
            continue

        try:
            from openxml_audit import validate_pptx

            result = validate_pptx(str(out))
            if not result.is_valid:
                failures.append(
                    f"{svg_path.name}: FAIL "
                    + "; ".join(str(e) for e in result.errors[:2])
                )
        except ImportError:
            pass  # skip validation if not installed

    assert not failures, (
        f"{len(failures)}/{len(svgs)} failures:\n" + "\n".join(failures)
    )
