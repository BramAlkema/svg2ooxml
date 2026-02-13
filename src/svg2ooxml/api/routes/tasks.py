"""Cloud Tasks worker endpoints for background job processing."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from ..auth.cloud_tasks import verify_cloud_tasks_bearer_token
from ..services.export_service import ExportService

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize service
export_service = ExportService()


class TaskRequest(BaseModel):
    """Request payload from Cloud Tasks."""

    job_id: str
    auth_token_encrypted: str | None = None  # Optional encrypted OAuth token


@router.post("/process-export", status_code=status.HTTP_200_OK)
async def process_export_task(
    request: TaskRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    """
    Process an export job (called by Cloud Tasks).

    This endpoint is invoked by Google Cloud Tasks to process jobs
    asynchronously. It should only be accessible from Cloud Tasks.

    Args:
        request: Task request containing job_id and optional encrypted token

    Returns:
        Success status
    """
    job_id = request.job_id
    encrypted_token = request.auth_token_encrypted

    try:
        verify_cloud_tasks_bearer_token(authorization, task_path="/api/v1/tasks/process-export")
        logger.info(f"Processing export job from Cloud Tasks: {job_id}")

        # Decrypt user token if present
        user_token = None
        if encrypted_token:
            try:
                from ..auth.encryption import decrypt_token
                user_token = decrypt_token(encrypted_token)
                logger.debug(f"Decrypted user token for job {job_id}")
            except Exception as e:
                logger.warning(f"Failed to decrypt token for job {job_id}: {e}")
                # Continue without token (service account fallback)

        # Process the job synchronously (within this request)
        export_service.process_job(job_id, user_token=user_token)

        # Delete encrypted token from job document after successful processing
        if encrypted_token:
            try:
                from google.cloud import firestore
                db = firestore.Client()
                db.collection("exports").document(job_id).update({
                    "auth_token_encrypted": firestore.DELETE_FIELD
                })
                logger.debug(f"Deleted encrypted token for job {job_id}")
            except Exception as e:
                logger.warning(f"Could not delete encrypted token for job {job_id}: {e}")

        logger.info(f"Successfully processed export job: {job_id}")

        return {
            "status": "success",
            "job_id": job_id,
            "message": "Export job processed successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to process export job {job_id}: {e}", exc_info=True
        )

        # Return 500 so Cloud Tasks will retry
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process job: {str(e)}",
        ) from e


__all__ = ["router"]
