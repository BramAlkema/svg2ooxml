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
            f'<li data-testid="fixture-item"><a data-testid="fixture-link" '
            f'href="/compare?name={html.escape(item.name)}">{html.escape(item.name)}</a></li>'
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
            <ul data-testid="fixture-list">{fixture_items or '<li data-testid="fixture-empty">No fixtures found.</li>'}</ul>
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
        (session_dir / "source.svg").write_text(svg_text, encoding="utf-8")

        engines = ["resvg"]
        renders: dict[str, list[Path]] = {}
        notes: list[str] = []

        trace_reports: dict[str, dict[str, Any]] = {}

        for engine in engines:
            engine_dir = session_dir / engine
            engine_dir.mkdir()
            pptx_path = engine_dir / "presentation.pptx"
            render_dir = engine_dir / "render"
            render_dir.mkdir()

            builder = PptxBuilder(
                filter_strategy=engine,
                geometry_mode=engine,
                slide_size_mode=pptx_builder._slide_size_mode,
                allow_promotion=False if engine == "resvg" else True,
            )

            try:
                from svg2ooxml.core.tracing import ConversionTracer
                tracer = ConversionTracer()
                
                build_result = builder.build_from_svg(svg_text, pptx_path, source_path=svg_path, tracer=tracer)
                trace_reports[engine] = tracer.report().to_dict()
                
                rendered = pptx_renderer.render(build_result.pptx_path, render_dir)
                renders[engine] = list(rendered.images)
            except (VisualBuildError, VisualRendererError) as exc:
                notes.append(f"{engine.capitalize()} failed: {html.escape(str(exc))}")
                renders[engine] = []

        def _get_tags(engine: str):
            images = renders.get(engine, [])
            if not images:
                return f"<p>No {engine} slides.</p>"
            return "".join(
                f'<figure><img class="media" src="/artefacts/{token}/{engine}/render/{img.name}" alt="{engine} {index}" />'
                f'<figcaption>{engine.capitalize()} Slide {index}</figcaption></figure>'
                for index, img in enumerate(images, start=1)
            )

        resvg_tags = _get_tags("resvg")

        def _format_trace(engine: str):
            report = trace_reports.get(engine)
            if not report:
                return "<p>No trace available.</p>"
            
            rows = []
            
            # Stage Events
            for event in report.get("stage_events", []):
                stage = event.get("stage", "")
                action = event.get("action", "")
                subject = event.get("subject") or ""
                metadata = event.get("metadata")
                meta_str = html.escape(str(metadata)) if metadata else ""
                rows.append(f"<tr><td>{stage}</td><td>{action}</td><td>{subject}</td><td><small>{meta_str}</small></td></tr>")
            
            # Geometry Decisions
            for event in report.get("geometry_events", []):
                tag = event.get("tag", "")
                decision = event.get("decision", "")
                element_id = event.get("element_id") or ""
                metadata = event.get("metadata")
                meta_str = html.escape(str(metadata)) if metadata else ""
                rows.append(f"<tr><td>geometry</td><td>{decision} ({tag})</td><td>{element_id}</td><td><small>{meta_str}</small></td></tr>")

            # Paint Decisions
            for event in report.get("paint_events", []):
                ptype = event.get("paint_type", "")
                decision = event.get("decision", "")
                paint_id = event.get("paint_id") or ""
                metadata = event.get("metadata")
                meta_str = html.escape(str(metadata)) if metadata else ""
                rows.append(f"<tr><td>paint</td><td>{decision} ({ptype})</td><td>{paint_id}</td><td><small>{meta_str}</small></td></tr>")

            totals = []
            if report.get("resvg_metrics"):
                metrics = ", ".join(f"{k}: {v}" for k, v in report["resvg_metrics"].items())
                totals.append(f"<li><strong>Resvg Metrics:</strong> {metrics}</li>")
            
            geom_totals = report.get("geometry_totals", {})
            if geom_totals:
                totals.append(f"<li><strong>Geometry:</strong> {', '.join(f'{k}={v}' for k, v in geom_totals.items())}</li>")

            paint_totals = report.get("paint_totals", {})
            if paint_totals:
                totals.append(f"<li><strong>Paint:</strong> {', '.join(f'{k}={v}' for k, v in paint_totals.items())}</li>")

            totals_html = f"<ul>{''.join(totals)}</ul>" if totals else ""
            
            return f"""
                <details>
                  <summary>{engine.capitalize()} Conversion Trace ({len(rows)} events)</summary>
                  {totals_html}
                  <table style='font-size: 0.75rem; border-collapse: collapse; width: 100%;'>
                    <thead><tr style='text-align: left; border-bottom: 1px solid #ccc;'><th>Stage</th><th>Action</th><th>Subject</th><th>Metadata</th></tr></thead>
                    <tbody>{"".join(rows)}</tbody>
                  </table>
                </details>
            """

        resvg_trace = _format_trace("resvg")
        # Update the columns section to include traces
        columns_html = f"""
            <div class="columns" data-testid="compare-columns">
              <section class="pane" data-testid="pane-source">
                <h2>Source SVG</h2>
                <img class="media" src="data:image/svg+xml;base64,{svg_b64}" alt="SVG source" />
              </section>
              <section class="pane" data-testid="pane-resvg">
                <h2>Resvg Render</h2>
                {resvg_tags}
                {resvg_trace}
              </section>
            </div>
        """

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
              .columns {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
              .pane {{ flex: 1 1 300px; min-width: 300px; }}
              .media {{ border: 1px solid #d2d6dc; border-radius: 6px; max-width: 100%; height: auto; }}
              .diff-bg {{ background: #f8f9fa; }}
              figure {{ margin: 0 0 1rem 0; }}
              figcaption {{ margin-top: 0.25rem; font-size: 0.85rem; color: #52606d; }}
              .meta {{ margin-top: 1rem; display: flex; gap: 1rem; }}
              .notes {{ margin-top: 1rem; color: #c81e1e; }}
              a.button {{ display: inline-block; padding: 0.4rem 0.6rem; background: #2563eb; color: white; border-radius: 4px; text-decoration: none; font-size: 0.9rem; }}
              table th, table td {{ padding: 0.25rem; border-bottom: 1px solid #eee; }}
              details {{ margin-top: 1rem; padding: 0.5rem; background: #f1f5f9; border-radius: 4px; }}
              summary {{ cursor: pointer; font-weight: bold; }}
            </style>
          </head>
          <body>
            <p><a href="/">⟵ Back to library</a></p>
            <h1>{html.escape(svg_path.name)}</h1>
            <div class="meta" data-testid="download-links">
              <a class="button" data-testid="download-resvg" href="/artefacts/{token}/resvg/presentation.pptx">
                Download Resvg PPTX
              </a>
            </div>
            {note_html}
            {columns_html}
          </body>
        </html>
        """
        return HTMLResponse(content)

    return app


__all__ = ["create_app"]
