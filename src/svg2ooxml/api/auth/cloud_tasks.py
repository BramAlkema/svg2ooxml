"""Authentication helpers for Cloud Tasks callbacks."""

from __future__ import annotations

import logging
import os

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def _expected_task_audience(task_path: str) -> str | None:
    """Return expected OIDC audience for Cloud Tasks calls."""

    explicit_audience = os.getenv("CLOUD_TASKS_AUDIENCE")
    if explicit_audience:
        return explicit_audience

    service_url = os.getenv("SERVICE_URL")
    if not service_url:
        return None

    return f"{service_url.rstrip('/')}{task_path}"


def _expected_task_service_account_email() -> str | None:
    """Return expected service account email for Cloud Tasks calls."""

    configured = os.getenv("CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL")
    if configured:
        return configured

    project_id = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        return None

    return f"svg2ooxml-runner@{project_id}.iam.gserviceaccount.com"


def verify_cloud_tasks_bearer_token(authorization: str | None, *, task_path: str) -> None:
    """Validate the Cloud Tasks OIDC bearer token."""

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing task authentication token",
        )

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing task authentication token",
        )

    expected_audience = _expected_task_audience(task_path)
    if not expected_audience:
        logger.error("Cloud Tasks auth misconfigured: missing CLOUD_TASKS_AUDIENCE or SERVICE_URL")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Task authentication is not configured",
        )

    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2 import id_token

        claims = id_token.verify_oauth2_token(
            token,
            GoogleAuthRequest(),
            expected_audience,
        )
    except Exception as exc:
        logger.warning("Rejected Cloud Tasks request: invalid OIDC token (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid task authentication token",
        ) from exc

    expected_email = _expected_task_service_account_email()
    token_email = claims.get("email")
    if expected_email and token_email != expected_email:
        logger.warning(
            "Rejected Cloud Tasks request: email mismatch (expected=%s got=%s)",
            expected_email,
            token_email or "missing",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden task caller",
        )


__all__ = ["verify_cloud_tasks_bearer_token"]
