"""Access-control helpers shared by export routes."""

from __future__ import annotations

import logging

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def job_owner_uid(job_data: dict[str, object]) -> str | None:
    """Return the owning Firebase UID embedded in a job payload."""

    user_payload = job_data.get("user")
    if not isinstance(user_payload, dict):
        return None
    owner_uid = user_payload.get("uid")
    if isinstance(owner_uid, str) and owner_uid:
        return owner_uid
    return None


def ensure_job_access(job_id: str, job_data: dict[str, object], user: dict[str, object]) -> None:
    """Ensure the caller can access the requested job."""

    requester_uid = user.get("uid")
    requester_uid = requester_uid if isinstance(requester_uid, str) else None
    requester_is_admin = bool(user.get("admin") or user.get("is_admin"))
    owner_uid = job_owner_uid(job_data)

    if requester_is_admin:
        return

    if requester_uid and owner_uid and requester_uid == owner_uid:
        return

    logger.warning(
        "Rejected access to job %s (requester=%s owner=%s)",
        job_id,
        requester_uid or "unknown",
        owner_uid or "unknown",
    )
    # Return 404 to avoid leaking whether a job exists for another user.
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Job {job_id} not found",
    )


__all__ = ["ensure_job_access", "job_owner_uid"]
