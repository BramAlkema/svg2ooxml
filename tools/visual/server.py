"""Side-by-side visual comparison server for svg2ooxml."""

from __future__ import annotations

import base64
import html
import logging
import os
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from tools.visual.builder import PptxBuilder, VisualBuildError
from tools.visual.renderer import LibreOfficeRenderer, VisualRendererError, default_renderer

logger = logging.getLogger(__name__)

DEFAULT_FIXTURE_ROOT = Path("tests/visual/fixtures")
DEFAULT_OUTPUT_ROOT = Path(".visual_server")


def _discover_fixtures(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(root.glob("*.svg"))


def _encode_svg(svg_text: str) -> str:
    return base64.b64encode(svg_text.encode("utf-8")).decode("ascii")


def create_app(
    *,
    fixture_root: Path | str | None = None,
    output_root: Path | str | None = None,
    builder: PptxBuilder | None = None,
    renderer: LibreOfficeRenderer | None = None,
) -> FastAPI:
    """Return a configured FastAPI app for visual comparisons."""

    fixture_root = Path(fixture_root or DEFAULT_FIXTURE_ROOT).resolve()
    output_root = Path(output_root or DEFAULT_OUTPUT_ROOT).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    if builder is None:
        filter_strategy = os.getenv("SVG2OOXML_VISUAL_FILTER_STRATEGY", "resvg")
        slide_size_mode = os.getenv("SVG2OOXML_SLIDE_SIZE_MODE", "same")
        pptx_builder = PptxBuilder(
            filter_strategy=filter_strategy,
            slide_size_mode=slide_size_mode,
        )
    else:
        pptx_builder = builder
    pptx_renderer = renderer or default_renderer()
    app = FastAPI(title="svg2ooxml Visual Diff", version="0.1")

    app.mount("/artefacts", StaticFiles(directory=str(output_root)), name="artefacts")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        fixtures = _discover_fixtures(fixture_root)
        fixture_items = "".join(
            f'<li><a href="/compare?name={html.escape(item.name)}">{html.escape(item.name)}</a></li>'
            for item in fixtures
        )
        renderer_status = (
            "✅ LibreOffice renderer available" if pptx_renderer.available else "⚠️ LibreOffice renderer not detected"
        )

        content = f"""
        <html>
          <head>
            <title>svg2ooxml Visual Diff</title>
            <style>
              body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 2rem; color: #1f2933; }}
              h1 {{ margin-bottom: 0.5rem; }}
              form {{ margin-bottom: 1.5rem; }}
              input[type=text] {{ width: 360px; padding: 0.4rem; }}
              .status {{ margin: 1rem 0; font-weight: 600; }}
            </style>
          </head>
          <body>
            <h1>svg2ooxml Visual Diff</h1>
            <div class="status">{renderer_status}</div>
            <form action="/compare" method="get">
              <label for="path">Compare local SVG path:</label>
              <input id="path" name="path" type="text" placeholder="/path/to/graphic.svg" />
              <button type="submit">Compare</button>
            </form>
            <h2>Fixture Library</h2>
            <ul>{fixture_items or '<li>No fixtures found.</li>'}</ul>
          </body>
        </html>
        """
        return HTMLResponse(content)

    @app.get("/compare", response_class=HTMLResponse)
    async def compare(
        name: str | None = Query(default=None, description="Fixture filename under tests/visual/fixtures"),
        path: str | None = Query(default=None, description="Absolute or relative path to an SVG file"),
    ) -> HTMLResponse:
        if not name and not path:
            raise HTTPException(status_code=400, detail="Provide either ?name=<fixture.svg> or ?path=/file.svg")

        if name:
            svg_path = (fixture_root / name).resolve()
        else:
            svg_path = Path(path or "").expanduser().resolve()

        if not svg_path.exists():
            raise HTTPException(status_code=404, detail=f"SVG not found: {svg_path}")
        if svg_path.suffix.lower() != ".svg":
            raise HTTPException(status_code=400, detail="Only SVG sources are supported.")

        svg_text = svg_path.read_text(encoding="utf-8")
        svg_b64 = _encode_svg(svg_text)

        token = uuid4().hex
        session_dir = output_root / token
        session_dir.mkdir(parents=True, exist_ok=False)
        pptx_path = session_dir / "presentation.pptx"
        render_dir = session_dir / "render"
        render_dir.mkdir()

        notes: list[str] = []

        try:
            build_result = pptx_builder.build_from_svg(svg_text, pptx_path)
        except VisualBuildError as exc:
            logger.exception("Failed to build PPTX", exc_info=exc)
            raise HTTPException(status_code=500, detail=f"Failed to build PPTX: {exc}")

        slide_count = build_result.slide_count
        pptx_link = f"/artefacts/{token}/presentation.pptx"

        png_tags = ""
        try:
            rendered = pptx_renderer.render(build_result.pptx_path, render_dir)
        except VisualRendererError as exc:
            notes.append(f"Rendering failed: {html.escape(str(exc))}")
            rendered_images: list[Path] = []
        else:
            rendered_images = list(rendered.images)

        if rendered_images:
            png_tags = "".join(
                f'<figure><img class="media" src="/artefacts/{token}/render/{img.name}" alt="Slide {index}" />'
                f'<figcaption>Slide {index}</figcaption></figure>'
                for index, img in enumerate(rendered_images, start=1)
            )
        else:
            png_tags = "<p>No rendered slides.</p>"

        note_html = "".join(f"<li>{message}</li>" for message in notes)
        if note_html:
            note_html = f"<ul class='notes'>{note_html}</ul>"

        content = f"""
        <html>
          <head>
            <title>Compare – {html.escape(svg_path.name)}</title>
            <style>
              body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 1.5rem; color: #1f2933; }}
              h1, h2 {{ margin-bottom: 0.5rem; }}
              .columns {{ display: flex; gap: 2rem; flex-wrap: wrap; }}
              .pane {{ flex: 1 1 420px; min-width: 360px; }}
              .media {{ border: 1px solid #d2d6dc; border-radius: 6px; max-width: 100%; height: auto; }}
              figure {{ margin: 0 0 1rem 0; }}
              figcaption {{ margin-top: 0.25rem; font-size: 0.85rem; color: #52606d; }}
              .meta {{ margin-top: 1rem; }}
              .notes {{ margin-top: 1rem; color: #c81e1e; }}
              a.button {{ display: inline-block; padding: 0.5rem 0.75rem; background: #2563eb; color: white; border-radius: 4px; text-decoration: none; }}
            </style>
          </head>
          <body>
            <p><a href="/">⟵ Back to library</a></p>
            <h1>{html.escape(svg_path.name)}</h1>
            <div class="meta">
              <p>Slides generated: <strong>{slide_count}</strong></p>
              <p><a class="button" href="{pptx_link}">Download PPTX</a></p>
            </div>
            {note_html}
            <div class="columns">
              <section class="pane">
                <h2>Source SVG</h2>
                <img class="media" src="data:image/svg+xml;base64,{svg_b64}" alt="SVG source" />
              </section>
              <section class="pane">
                <h2>PPTX Render</h2>
                {png_tags}
              </section>
            </div>
          </body>
        </html>
        """
        return HTMLResponse(content)

    return app


__all__ = ["create_app"]
