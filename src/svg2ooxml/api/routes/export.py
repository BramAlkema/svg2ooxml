"""Export API routes for Figma SVG to PPTX/Slides conversion."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from ..background import enqueue_export_job
from ..models import ExportRequest, ExportResponse, JobStatusResponse
from ..services.export_service import ExportService, ExportStatus, JobNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize service
export_service = ExportService()


@router.post("/export", response_model=ExportResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_export_job(
    request: ExportRequest,
) -> ExportResponse:
    """
    Create a new export job to convert Figma SVG frames to PowerPoint/Slides.

    The conversion runs asynchronously. Use the returned job_id to poll for status.

    - **frames**: List of SVG frames with content and dimensions
    - **output_format**: Either "pptx" (download PPTX) or "slides" (publish to Google Slides)
    - **fonts**: Optional list of font names to download/cache
    """
    try:
        logger.info(
            f"Creating export job: {len(request.frames)} frames, "
            f"format={request.output_format}, "
            f"file_id={request.figma_file_id}"
        )

        # Create job in Firestore
        job_id = await run_in_threadpool(
            export_service.create_job,
            frames=request.frames,
            figma_file_id=request.figma_file_id,
            figma_file_name=request.figma_file_name,
            output_format=request.output_format,
            fonts=request.fonts,
        )

        # Queue background processing
        enqueue_export_job(job_id)

        return ExportResponse(
            job_id=job_id,
            status=ExportStatus.QUEUED.value,
            message=f"Export job created with {len(request.frames)} frame(s)",
        )

    except Exception as e:
        logger.error(f"Failed to create export job: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create export job: {str(e)}",
        )


@router.get("/export/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """
    Get the status of an export job.

    Poll this endpoint to check progress and retrieve download URLs when complete.

    - **job_id**: The unique identifier returned when creating the job
    """
    try:
        job_data = await run_in_threadpool(export_service.get_job_status, job_id)

        return JobStatusResponse(
            job_id=job_id,
            status=job_data["status"],
            message=job_data.get("message", ""),
            progress=job_data.get("progress", 0.0),
            pptx_url=job_data.get("pptx_url"),
            slides_url=job_data.get("slides_url"),
            thumbnail_urls=job_data.get("thumbnail_urls"),
            error=job_data.get("error"),
            slides_error=job_data.get("slides_error"),
            created_at=job_data["created_at"],
            updated_at=job_data["updated_at"],
            conversion_summary=job_data.get("conversion_summary"),
            font_summary=job_data.get("font_summary"),
            slides_embed_url=job_data.get("slides_embed_url"),
            slides_presentation_id=job_data.get("slides_presentation_id"),
        )

    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    except Exception as e:
        logger.error(f"Failed to get job status for {job_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve job status: {str(e)}",
        )


@router.delete("/export/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str):
    """
    Delete an export job and clean up associated resources.

    This will remove the job metadata from Firestore and delete files from Cloud Storage.

    - **job_id**: The unique identifier of the job to delete
    """
    try:
        await run_in_threadpool(export_service.delete_job, job_id)
        return None

    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    except Exception as e:
        logger.error(f"Failed to delete job {job_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete job: {str(e)}",
        )


__all__ = ["router"]
