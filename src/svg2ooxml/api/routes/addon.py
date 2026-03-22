"""Lightweight endpoint for Google Workspace add-on and similar integrations.

Accepts raw SVG markup, auto-extracts dimensions, and returns PPTX or
uploads to Google Slides. Authenticated via API key (not Supabase JWT).
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..auth.api_key import verify_api_key
from ..models import SVGFrame
from ..services.converter import render_pptx_for_frames
from ..services.slides_publisher import upload_to_google_slides

logger = logging.getLogger(__name__)

router = APIRouter()

CONVERSION_TIMEOUT = 120  # seconds

# ---------------------------------------------------------------------------
# SVG dimension extraction
# ---------------------------------------------------------------------------

_VIEWBOX_RE = re.compile(
    r'viewBox\s*=\s*["\']'
    r'\s*[\d.+-]+\s+[\d.+-]+\s+([\d.]+)\s+([\d.]+)\s*'
    r'["\']',
)
_WIDTH_RE = re.compile(r'<svg[^>]+\bwidth\s*=\s*["\']?\s*([\d.]+)')
_HEIGHT_RE = re.compile(r'<svg[^>]+\bheight\s*=\s*["\']?\s*([\d.]+)')


def _extract_dimensions(svg: str) -> tuple[float, float]:
    """Best-effort extraction of width/height from SVG markup.

    Tries explicit width/height attributes first, then viewBox.
    Falls back to 960×540 (16:9 widescreen).
    """
    w = h = None

    m = _WIDTH_RE.search(svg)
    if m:
        w = float(m.group(1))
    m = _HEIGHT_RE.search(svg)
    if m:
        h = float(m.group(1))

    if w and h:
        return w, h

    m = _VIEWBOX_RE.search(svg)
    if m:
        vb_w, vb_h = float(m.group(1)), float(m.group(2))
        return w or vb_w, h or vb_h

    return w or 960.0, h or 540.0


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class AddonConvertRequest(BaseModel):
    svg: str = Field(..., min_length=1, description="Raw SVG markup")
    filename: str = Field("converted", description="Output filename (without extension)")
    output_format: str = Field("pptx", pattern="^(slides|pptx)$")
    google_access_token: str | None = None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/convert")
async def addon_convert(
    request: AddonConvertRequest,
    _auth: dict = Depends(verify_api_key),
):
    """Convert a single SVG to PPTX or Google Slides.

    Designed for the Google Workspace add-on: accepts raw SVG,
    auto-extracts dimensions, uses API key auth.
    """
    svg = request.svg.strip()
    if "<svg" not in svg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Input does not appear to be valid SVG markup.",
        )

    if request.output_format == "slides" and not request.google_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="google_access_token is required for slides output.",
        )

    width, height = _extract_dimensions(svg)
    filename = request.filename.removesuffix(".pptx")

    frame = SVGFrame(
        name=filename,
        svg_content=svg,
        width=width,
        height=height,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        pptx_path = Path(tmpdir) / "export.pptx"

        try:
            await asyncio.wait_for(
                run_in_threadpool(render_pptx_for_frames, [frame], pptx_path),
                timeout=CONVERSION_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Conversion timed out. Try a simpler SVG.",
            )
        except Exception as exc:
            logger.error("Add-on conversion failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Conversion failed.",
            ) from exc

        pptx_bytes = pptx_path.read_bytes()

    if request.output_format == "slides":
        try:
            slides_url = await run_in_threadpool(
                upload_to_google_slides,
                pptx_bytes,
                request.google_access_token,
                title=filename,
            )
        except Exception as exc:
            logger.error("Slides upload failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google Slides upload failed.",
            ) from exc

        return {"slides_url": slides_url}

    return StreamingResponse(
        io.BytesIO(pptx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.pptx"',
        },
    )


__all__ = ["router"]
