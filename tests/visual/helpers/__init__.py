"""Fixture helpers for the visual testing harness."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tools.visual.renderer import LibreOfficeRenderer, default_renderer

from .builder import PptxBuilder
from .diff import ImageDiff
from .golden import GoldenRepository


@dataclass
class VisualTestTools:
    """Bundle of helpers exposed to visual regression tests."""

    golden: GoldenRepository
    diff: ImageDiff
    builder: PptxBuilder
    renderer: LibreOfficeRenderer


@pytest.fixture
def visual_tools() -> VisualTestTools:
    """Fixture providing the default visual test utilities."""

    golden = GoldenRepository()
    diff = ImageDiff()
    builder = PptxBuilder()
    renderer = default_renderer()
    return VisualTestTools(golden=golden, diff=diff, builder=builder, renderer=renderer)


__all__ = ["VisualTestTools", "visual_tools"]
