"""Export API route: synchronous SVG-to-PPTX/Slides conversion."""

from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..auth.supabase import verify_supabase_token
from ..services.converter import render_pptx_for_frames
from ..services.slides_publisher import upload_to_google_slides

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ExportFrame(BaseModel):
    name: str = ""
    svg_content: str
    width: float = Field(..., gt=0)
    height: float = Field(..., gt=0)


class ExportRequest(BaseModel):
    frames: list[ExportFrame] = Field(..., min_length=1)
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

    # Convert frames to the SVGFrame model expected by the converter.
    from ..models import SVGFrame

    svg_frames = [
        SVGFrame(
            name=f.name,
            svg_content=f.svg_content,
            width=f.width,
            height=f.height,
        )
        for f in request.frames
    ]

    # Render PPTX in a thread (CPU-bound).
    with tempfile.TemporaryDirectory() as tmpdir:
        pptx_path = Path(tmpdir) / "export.pptx"

        try:
            artifacts = await run_in_threadpool(
                render_pptx_for_frames, svg_frames, pptx_path
            )
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
