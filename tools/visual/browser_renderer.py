"""Render SVG sources to PNG using a headless browser (optional dependency)."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - handled at runtime
    PlaywrightError = None
    sync_playwright = None


class BrowserRenderError(RuntimeError):
    """Raised when browser rendering fails."""


@dataclass(frozen=True)
class RenderedSvg:
    """Container describing the output from a browser render."""

    image: Path
    renderer: str


class BrowserSvgRenderer:
    """Render SVG markup to PNG using Playwright-managed browsers."""

    def __init__(
        self,
        *,
        engine: str = "chromium",
        timeout: float | None = 30.0,
        device_scale_factor: float | None = None,
    ) -> None:
        self._engine = engine
        self._timeout = timeout
        self._device_scale_factor = device_scale_factor

    @property
    def available(self) -> bool:
        """Return True if Playwright is installed."""

        return sync_playwright is not None

    def render_svg(self, svg_text: str, output_path: Path | str) -> RenderedSvg:
        """Render SVG markup to a PNG file."""

        if not self.available:
            raise BrowserRenderError(
                "Playwright is not available. Install with `pip install playwright` "
                "and run `playwright install`."
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        width, height = _extract_dimensions(svg_text)
        html = _wrap_svg(svg_text, width=width, height=height)

        try:
            with sync_playwright() as playwright:
                browser_type = getattr(playwright, self._engine, None)
                if browser_type is None:
                    raise BrowserRenderError(f"Unknown browser engine '{self._engine}'.")
                browser = browser_type.launch()
                viewport = {"width": width, "height": height}
                if self._device_scale_factor:
                    viewport["deviceScaleFactor"] = self._device_scale_factor
                page = browser.new_page(viewport=viewport)
                page.set_content(html, wait_until="load")
                page.screenshot(path=str(output_path), omit_background=True)
                browser.close()
        except BrowserRenderError:
            raise
        except Exception as exc:
            detail = str(exc)
            if PlaywrightError and isinstance(exc, PlaywrightError):
                detail = str(exc)
            raise BrowserRenderError(f"Browser render failed: {detail}") from exc

        if not output_path.exists():
            raise BrowserRenderError(f"Browser did not produce image: {output_path}")

        return RenderedSvg(image=output_path, renderer=self._engine)


def default_browser_renderer() -> BrowserSvgRenderer:
    """Return a browser renderer configured by environment variables."""

    engine = os.getenv("SVG2OOXML_BROWSER_ENGINE", "chromium")
    scale_raw = os.getenv("SVG2OOXML_BROWSER_SCALE")
    scale = float(scale_raw) if scale_raw else None
    return BrowserSvgRenderer(engine=engine, device_scale_factor=scale)


def _extract_dimensions(svg_text: str) -> Tuple[int, int]:
    from xml.etree import ElementTree as ET

    root = ET.fromstring(svg_text)
    view_box_tokens = root.attrib.get("viewBox", "").split()
    width = _parse_dimension(root.attrib.get("width", ""), view_box_tokens, 2)
    height = _parse_dimension(root.attrib.get("height", ""), view_box_tokens, 3)
    width = width or 800.0
    height = height or 600.0
    return max(1, int(round(width))), max(1, int(round(height)))


def _parse_dimension(token: str, view_box_tokens: list[str], fallback_index: int) -> float | None:
    normalized = (token or "").strip()
    if normalized.endswith("%") and len(view_box_tokens) == 4:
        return _parse_float(view_box_tokens[fallback_index])
    if normalized:
        match = re.match(r"^([0-9]*\.?[0-9]+)", normalized)
        if match:
            return _parse_float(match.group(1))
        return None
    if len(view_box_tokens) == 4:
        return _parse_float(view_box_tokens[fallback_index])
    return None


def _parse_float(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None


def _wrap_svg(svg_text: str, *, width: int, height: int) -> str:
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        width: {width}px;
        height: {height}px;
        background: transparent;
      }}
    </style>
  </head>
  <body>
    {svg_text}
  </body>
</html>
"""


__all__ = ["BrowserSvgRenderer", "BrowserRenderError", "RenderedSvg", "default_browser_renderer"]
