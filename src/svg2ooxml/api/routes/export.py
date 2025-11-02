"""Export API routes for Figma SVG to PPTX/Slides conversion."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from ..auth.middleware import verify_firebase_token
from ..background import enqueue_export_job
from ..models import ExportRequest, ExportResponse, JobStatusResponse
from ..services.export_service import ExportService, ExportStatus, JobNotFoundError
from ..services.subscription_repository import SubscriptionRepository

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize services
export_service = ExportService()
subscription_repo = SubscriptionRepository()

# Free tier limit
FREE_TIER_LIMIT = 5


@router.post(
    "/export",
    response_model=ExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"description": "Unauthorized - Invalid or missing authentication token"},
        403: {"description": "Forbidden - Insufficient permissions"},
    },
)
async def create_export_job(
    request: ExportRequest,
    user: dict = Depends(verify_firebase_token),
) -> ExportResponse:
    """
    Create a new export job to convert Figma SVG frames to PowerPoint/Slides.

    The conversion runs asynchronously. Use the returned job_id to poll for status.

    **Authentication Required**: Include Firebase ID token in Authorization header:
    ```
    Authorization: Bearer <firebase-id-token>
    ```

    The token must include the following OAuth scopes:
    - `https://www.googleapis.com/auth/drive.file`
    - `https://www.googleapis.com/auth/presentations`

    - **frames**: List of SVG frames with content and dimensions
    - **output_format**: Either "pptx" (download PPTX) or "slides" (publish to Google Slides)
    - **fonts**: Optional list of font names to download/cache
    """
    try:
        firebase_uid = user['uid']

        logger.info(
            f"Creating export job: {len(request.frames)} frames, "
            f"format={request.output_format}, "
            f"file_id={request.figma_file_id}, "
            f"user_id={firebase_uid}"
        )

        # Check subscription and usage limits
        from datetime import datetime
        import asyncio

        current_month = datetime.now().strftime("%Y-%m")

        # Run both queries in parallel for better performance
        subscription, usage = await asyncio.gather(
            run_in_threadpool(
                subscription_repo.get_active_subscription, firebase_uid
            ),
            run_in_threadpool(
                subscription_repo.get_usage, firebase_uid, current_month
            ),
        )
        export_count = usage["exportCount"] if usage else 0

        # Check if user has exceeded free tier limit
        if not subscription or subscription.get("status") != "active":
            # Free tier user - check limit
            if export_count >= FREE_TIER_LIMIT:
                logger.warning(
                    f"User {firebase_uid} exceeded free tier limit: {export_count}/{FREE_TIER_LIMIT}"
                )
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "error": "quota_exceeded",
                        "message": f"You've reached your monthly limit of {FREE_TIER_LIMIT} exports. "
                                   "Upgrade to Pro for unlimited exports.",
                        "usage": {
                            "current": export_count,
                            "limit": FREE_TIER_LIMIT,
                        },
                    },
                )

        # Create job in Firestore with user authentication
        job_id = await run_in_threadpool(
            export_service.create_job,
            frames=request.frames,
            figma_file_id=request.figma_file_id,
            figma_file_name=request.figma_file_name,
            output_format=request.output_format,
            fonts=request.fonts,
            user=user,  # Pass user info for authentication
        )

        # Increment usage counter
        await run_in_threadpool(
            subscription_repo.increment_usage, firebase_uid, current_month
        )

        # Queue background processing
        enqueue_export_job(job_id)

        logger.info(
            f"Export job {job_id} created for user {firebase_uid} "
            f"(usage: {export_count + 1}, tier: {subscription.get('tier', 'free') if subscription else 'free'})"
        )

        return ExportResponse(
            job_id=job_id,
            status=ExportStatus.QUEUED.value,
            message=f"Export job created with {len(request.frames)} frame(s)",
        )

    except HTTPException:
        # Re-raise HTTP exceptions (e.g., 402 Payment Required)
        raise
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
