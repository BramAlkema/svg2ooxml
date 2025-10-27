"""Cloud Tasks worker endpoints for background job processing."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ..services.export_service import ExportService

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize service
export_service = ExportService()


class TaskRequest(BaseModel):
    """Request payload from Cloud Tasks."""

    job_id: str


@router.post("/process-export", status_code=status.HTTP_200_OK)
async def process_export_task(request: TaskRequest) -> dict:
    """
    Process an export job (called by Cloud Tasks).

    This endpoint is invoked by Google Cloud Tasks to process jobs
    asynchronously. It should only be accessible from Cloud Tasks.

    Args:
        request: Task request containing job_id

    Returns:
        Success status
    """
    job_id = request.job_id

    try:
        logger.info(f"Processing export job from Cloud Tasks: {job_id}")

        # Process the job synchronously (within this request)
        export_service.process_job(job_id)

        logger.info(f"Successfully processed export job: {job_id}")

        return {
            "status": "success",
            "job_id": job_id,
            "message": "Export job processed successfully",
        }

    except Exception as e:
        logger.error(
            f"Failed to process export job {job_id}: {e}", exc_info=True
        )

        # Return 500 so Cloud Tasks will retry
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process job: {str(e)}",
        )


__all__ = ["router"]
