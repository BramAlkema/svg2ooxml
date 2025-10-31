"""Tests for PathMapper."""

from __future__ import annotations

from svg2ooxml.ir.geometry import LineSegment, Point
from svg2ooxml.ir.scene import Path
from svg2ooxml.core.pipeline.mappers import PathMapper, OutputFormat


def _path() -> Path:
    segments = [
        LineSegment(Point(0, 0), Point(10, 0)),
        LineSegment(Point(10, 0), Point(10, 10)),
        LineSegment(Point(10, 10), Point(0, 10)),
        LineSegment(Point(0, 10), Point(0, 0)),
    ]
    return Path(segments=segments, fill=None, stroke=None, metadata={})


def test_path_mapper_native_output() -> None:
    mapper = PathMapper()
    path = _path()

    result = mapper.map(path)

    assert result.output_format == OutputFormat.NATIVE_DML
    assert "<p:sp>" in result.xml_content


def test_path_mapper_emf_fallback() -> None:
    class FallbackPolicy:
        def decide_path(self, path: Path):
            from svg2ooxml.core.pipeline.mappers.path_mapper import PathDecision

            return PathDecision(use_native=False)

    mapper = PathMapper(policy=FallbackPolicy())
    result = mapper.map(_path())
    assert result.output_format == OutputFormat.EMF_VECTOR
