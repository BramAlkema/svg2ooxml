"""Regression tests for transformed text sizing."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pytest
from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.core.ir.text_converter import TextConverter
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace


class _DummyServices:
    def resolve(self, _name: str):
        return None


class _DummyContext:
    def __init__(self) -> None:
        self.services = _DummyServices()
        self.style_resolver = None
        self.logger = logging.getLogger(__name__)
        self.resvg_tree = None

    def policy_options(self, _target: str):
        return None

    def attach_policy_metadata(self, *_args, **_kwargs) -> None:
        pass

    def trace_geometry_decision(self, *_args, **_kwargs) -> None:
        pass

    @staticmethod
    def local_name(tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag


@dataclass
class _MockColor:
    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    a: float = 1.0


@dataclass
class _MockFillStyle:
    color: _MockColor | None = None
    opacity: float = 1.0
    reference: object | None = None


@dataclass
class _MockTextStyle:
    font_families: tuple[str, ...] = ("Arial",)
    font_size: float | None = 30.0
    font_style: str | None = None
    font_weight: str | None = None
    text_decoration: str | None = None
    letter_spacing: float | None = None


@dataclass
class _MockTextNode:
    text_content: str | None = "Scaled"
    text_style: _MockTextStyle | None = field(default_factory=_MockTextStyle)
    fill: _MockFillStyle | None = field(
        default_factory=lambda: _MockFillStyle(color=_MockColor())
    )
    stroke: object | None = None
    transform: object | None = None
    attributes: dict[str, str] = field(
        default_factory=lambda: {"x": "10", "y": "20"}
    )
    styles: dict[str, str] = field(default_factory=dict)
    children: list[object] = field(default_factory=list)
    source: object | None = None


def test_text_scale_for_coord_space_ignores_translation() -> None:
    coord_space = CoordinateSpace()
    coord_space.push(Matrix2D.translate(120.0, 45.0))

    assert TextConverter._text_scale_for_coord_space(coord_space) == pytest.approx(1.0)


def test_resvg_text_respects_coord_space_scale_in_runs_and_metadata() -> None:
    converter = TextConverter(_DummyContext())
    coord_space = CoordinateSpace()
    coord_space.push(Matrix2D.scale(0.5))

    frame = converter.convert(
        element=etree.fromstring('<text x="10" y="20">Scaled</text>'),
        coord_space=coord_space,
        resvg_node=_MockTextNode(),
    )

    assert frame is not None
    assert frame.runs is not None
    assert frame.runs[0].font_size_pt == pytest.approx(15.0)

    resvg_meta = frame.metadata["resvg_text"]
    assert resvg_meta["strategy"] == "runs"
    assert 'sz="1500"' in resvg_meta["runs_xml"]
