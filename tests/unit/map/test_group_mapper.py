"""Tests for GroupMapper."""

from __future__ import annotations

from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.geometry import LineSegment, Point
from svg2ooxml.ir.scene import Group, Path
from svg2ooxml.core.pipeline.mappers import GroupMapper, OutputFormat, PathMapper


def _child_path() -> Path:
    segments = [
        LineSegment(Point(0, 0), Point(5, 0)),
        LineSegment(Point(5, 0), Point(5, 5)),
        LineSegment(Point(5, 5), Point(0, 5)),
        LineSegment(Point(0, 5), Point(0, 0)),
    ]
    path = Path(segments=segments, fill=None, stroke=None, metadata={})
    xml = PathMapper().map(path).xml_content
    path.metadata["generated_xml"] = xml
    return path


def _group() -> Group:
    return Group(children=[_child_path()], metadata={})


def test_group_mapper_wraps_children() -> None:
    mapper = GroupMapper()
    group = _group()

    result = mapper.map(group)
    assert result.output_format == OutputFormat.NATIVE_DML
    assert "<p:grpSp>" in result.xml_content
