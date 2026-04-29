"""Export API route: synchronous SVG-to-PPTX/Slides conversion."""

from __future__ import annotations

import asyncio
import io
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from figma2gslides.api.auth.supabase import verify_supabase_token
from figma2gslides.api.services.slides_publisher import upload_to_google_slides
from svg2ooxml.export import SVGFrame, render_pptx_for_frames

logger = logging.getLogger(__name__)

router = APIRouter()

CONVERSION_TIMEOUT = 120  # seconds


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class ExportRequest(BaseModel):
    frames: list[SVGFrame] = Field(..., min_length=1)
    figma_file_name: str = "Untitled"
    output_format: str = Field("slides", pattern="^(slides|pptx)$")
    google_access_token: str | None = None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/export")
async def export_frames(
    request: ExportRequest,
    user: dict = Depends(verify_supabase_token),
):
    """Convert SVG frames to PPTX and optionally upload to Google Slides."""
    logger.info(
        "Export request: %d frame(s), format=%s, user=%s",
        len(request.frames),
        request.output_format,
        user.get("uid"),
    )

    if request.output_format == "slides" and not request.google_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="google_access_token is required for slides output",
        )

    # Render PPTX in a thread (CPU-bound) with timeout.
    with tempfile.TemporaryDirectory() as tmpdir:
        pptx_path = Path(tmpdir) / "export.pptx"

        try:
            await asyncio.wait_for(
                run_in_threadpool(render_pptx_for_frames, request.frames, pptx_path),
                timeout=CONVERSION_TIMEOUT,
            )
        except TimeoutError as exc:
            logger.error("PPTX conversion timed out after %ds", CONVERSION_TIMEOUT)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Conversion timed out. Try fewer or simpler frames.",
            ) from exc
        except Exception as exc:
            logger.error("PPTX conversion failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Conversion failed. Please try again with a simpler SVG.",
            ) from exc

        pptx_bytes = pptx_path.read_bytes()

    if request.output_format == "slides":
        try:
            slides_url = await run_in_threadpool(
                upload_to_google_slides,
                pptx_bytes,
                request.google_access_token,
                title=request.figma_file_name,
            )
        except Exception as exc:
            logger.error("Slides upload failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google Slides upload failed. Please sign in again.",
            ) from exc

        return {"slides_url": slides_url}

    # PPTX download
    return StreamingResponse(
        io.BytesIO(pptx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": f'attachment; filename="{request.figma_file_name}.pptx"'
        },
    )


__all__ = ["router"]
