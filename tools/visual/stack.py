"""Shared visual testing stack for tools and tests."""

from __future__ import annotations

from dataclasses import dataclass
import os

from tools.visual.browser_renderer import BrowserSvgRenderer, default_browser_renderer
from tools.visual.builder import PptxBuilder
from tools.visual.diff import ImageDiff
from tools.visual.golden import GoldenRepository
from tools.visual.renderer import PptxRenderer, resolve_renderer


@dataclass
class VisualStack:
    """Bundle of helpers for visual regression workflows."""

    golden: GoldenRepository
    diff: ImageDiff
    builder: PptxBuilder
    renderer: PptxRenderer
    browser_renderer: BrowserSvgRenderer | None = None


def default_visual_stack() -> VisualStack:
    """Return the default visual stack configured by environment variables."""

    filter_strategy = os.getenv("SVG2OOXML_VISUAL_FILTER_STRATEGY", "resvg")
    slide_size_mode = os.getenv("SVG2OOXML_SLIDE_SIZE_MODE", "same")
    builder = PptxBuilder(filter_strategy=filter_strategy, slide_size_mode=slide_size_mode)
    renderer = resolve_renderer()
    browser_renderer = default_browser_renderer()
    return VisualStack(
        golden=GoldenRepository(),
        diff=ImageDiff(),
        builder=builder,
        renderer=renderer,
        browser_renderer=browser_renderer,
    )


__all__ = ["VisualStack", "default_visual_stack"]
