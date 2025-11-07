"""Export API routes for Figma SVG to PPTX/Slides conversion."""

from __future__ import annotations

import logging
import os

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
subscription_repo = None  # Lazy initialized on first use

# Free tier limit
FREE_TIER_LIMIT = 5


def get_subscription_repo() -> SubscriptionRepository:
    """Get or create the subscription repository instance."""
    global subscription_repo
    if subscription_repo is None:
        subscription_repo = SubscriptionRepository()
    return subscription_repo


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

        # Check subscription and usage limits (unless disabled for testing or user is admin)
        disable_quota = os.getenv("DISABLE_EXPORT_QUOTA", "false").lower() == "true"

        # Check if user has admin/unlimited flag in Firestore
        user_has_unlimited = False
        if not disable_quota:
            try:
                from ..auth.firebase import get_firestore_client

                def check_unlimited_flag():
                    logger.info(f"Checking unlimited flag for user {firebase_uid}")
                    firestore_client = get_firestore_client()
                    logger.info(f"Got Firestore client, checking users/{firebase_uid}")
                    user_doc = firestore_client.collection("users").document(firebase_uid).get()
                    logger.info(f"User doc exists: {user_doc.exists}")
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        logger.info(f"User data: {user_data}")
                        has_flag = user_data.get("unlimited_exports", False) or user_data.get("admin", False)
                        logger.info(f"Has unlimited flag: {has_flag}")
                        return has_flag
                    return False

                user_has_unlimited = await run_in_threadpool(check_unlimited_flag)
                if user_has_unlimited:
                    logger.info(f"✅ User {firebase_uid} has unlimited quota flag - bypassing quota check")
                else:
                    logger.info(f"❌ User {firebase_uid} does not have unlimited flag - checking quota limits")
            except Exception as e:
                logger.error(f"❌ ERROR checking user unlimited flag: {e}", exc_info=True)

        if not disable_quota and not user_has_unlimited:
            from datetime import datetime

            current_month = datetime.now().strftime("%Y-%m")

            # Get subscription and usage (synchronous Firestore calls)
            repo = get_subscription_repo()
            subscription = await run_in_threadpool(
                repo.get_active_subscription, firebase_uid
            )
            usage = await run_in_threadpool(
                repo.get_usage, firebase_uid, current_month
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
        elif user_has_unlimited:
            logger.info(f"Export quota checking bypassed for user {firebase_uid} (user has unlimited_exports flag)")
        else:
            logger.info(f"Export quota checking disabled globally (DISABLE_EXPORT_QUOTA=true)")

        # Create job in Firestore with user authentication
        job_id = await run_in_threadpool(
            export_service.create_job,
            frames=request.frames,
            figma_file_id=request.figma_file_id,
            figma_file_name=request.figma_file_name,
            output_format=request.output_format,
            fonts=request.fonts,
            user=user,  # Pass user info for authentication
            parent_folder_id=request.parent_folder_id,
            user_refresh_token=request.user_refresh_token,  # Pass refresh token for OAuth
        )

        # Increment usage counter (unless quota is disabled or user has unlimited)
        if not disable_quota and not user_has_unlimited:
            await run_in_threadpool(
                repo.increment_usage, firebase_uid, current_month
            )
            tier = subscription.get('tier', 'free') if subscription else 'free'
            usage_info = f"(usage: {export_count + 1}, tier: {tier})"
        else:
            usage_info = "(quota disabled)"

        # Queue background processing
        enqueue_export_job(job_id)

        logger.info(
            f"Export job {job_id} created for user {firebase_uid} {usage_info}"
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
