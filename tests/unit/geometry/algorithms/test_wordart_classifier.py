"""Tests for the WordArt classifier port."""

import math

from svg2ooxml.common.geometry.algorithms.wordart_classifier import (
    WordArtClassificationResult,
    classify_text_path_warp,
)
from svg2ooxml.ir.text import Run
from svg2ooxml.ir.text_path import PathPoint, TextPathFrame


def _build_text_path(points: list[PathPoint]) -> TextPathFrame:
    return TextPathFrame(
        runs=[Run(text="Hello", font_family="Arial", font_size_pt=20.0)],
        path_reference="path-1",
        path_points=points,
    )


def _line_points(count: int = 20) -> list[PathPoint]:
    points: list[PathPoint] = []
    for i in range(count):
        x = float(i)
        points.append(PathPoint(x=x, y=0.0, tangent_angle=0.0, distance_along_path=x))
    return points


def _circle_points(radius: float = 1.0, count: int = 40) -> list[PathPoint]:
    points: list[PathPoint] = []
    for i in range(count):
        theta = 2 * math.pi * (i / count)
        x = radius * math.cos(theta)
        y = radius * math.sin(theta)
        tangent = theta + math.pi / 2.0
        points.append(PathPoint(x=x, y=y, tangent_angle=tangent, distance_along_path=i))
    points.append(points[0])
    return points


def _wave_points(amplitude: float = 1.0, count: int = 60) -> list[PathPoint]:
    points: list[PathPoint] = []
    for i in range(count):
        x = i / 10.0
        y = amplitude * math.sin(x)
        tangent = math.atan(math.cos(x))
        points.append(PathPoint(x=x, y=y, tangent_angle=tangent, distance_along_path=i))
    return points


def test_classify_plain_line() -> None:
    frame = _build_text_path(_line_points())
    result = classify_text_path_warp(frame, frame.path_points or [])

    assert isinstance(result, WordArtClassificationResult)
    assert result.preset == "textPlain"
    assert result.confidence >= 0.55


def test_classify_circle_path() -> None:
    frame = _build_text_path(_circle_points())
    result = classify_text_path_warp(frame, frame.path_points or [])

    assert result is not None
    assert result.preset == "textCircle"
    assert result.confidence >= 0.55


def test_classify_wave_path() -> None:
    frame = _build_text_path(_wave_points())
    result = classify_text_path_warp(frame, frame.path_points or [])

    assert result is not None
    assert result.preset == "textWave1"
    assert result.confidence >= 0.55
