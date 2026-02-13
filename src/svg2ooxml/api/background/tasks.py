"""Cloud Tasks integration for background job processing."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

try:  # pragma: no cover - optional dependency
    from google.cloud import tasks_v2
    from google.protobuf import timestamp_pb2
except ImportError:  # pragma: no cover - allows local fallback without GCP SDK
    tasks_v2 = None  # type: ignore[assignment]
    timestamp_pb2 = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class CloudTasksQueue:
    """Wrapper for Google Cloud Tasks queue operations with local fallbacks."""

    def __init__(self) -> None:
        """Initialize Cloud Tasks client and queue configuration."""
        self.project_id = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("CLOUD_TASKS_LOCATION", "europe-west1")
        self.queue_name = os.getenv("CLOUD_TASKS_QUEUE", "svg2ooxml-jobs")
        self.service_url = os.getenv("SERVICE_URL")

        self.enabled = bool(self.project_id and self.service_url)
        self.client: Any | None = None
        self.queue_path: str | None = None

        if not self.enabled:
            logger.info(
                "Cloud Tasks disabled (missing configuration). Jobs will run inline."
            )
            return

        if tasks_v2 is None:
            logger.warning(
                "google-cloud-tasks not installed; processing jobs inline instead."
            )
            self.enabled = False
            return

        self.client = tasks_v2.CloudTasksClient()
        self.queue_path = self.client.queue_path(
            self.project_id, self.location, self.queue_name
        )

    def enqueue_job(
        self,
        job_id: str,
        task_path: str = "/api/v1/tasks/process-export",
        schedule_delay_seconds: int = 0,
    ) -> str:
        """
        Enqueue a job for background processing.

        Args:
            job_id: Unique identifier for the export job
            task_path: URL path on the service to handle the task
            schedule_delay_seconds: Delay before executing the task

        Returns:
            Task name/ID from Cloud Tasks
        """
        if not self.enabled:
            logger.debug("Processing job %s inline (Cloud Tasks disabled)", job_id)
            self._process_inline(job_id)
            return f"inline:{job_id}"

        if self.client is None or self.queue_path is None:
            raise RuntimeError("Cloud Tasks client not initialised")

        # Fetch job data to check for encrypted token
        try:
            from google.cloud import firestore
            db = firestore.Client(project=self.project_id)
            job_doc = db.collection("exports").document(job_id).get()
            job_data = job_doc.to_dict() if job_doc.exists else {}
        except Exception as e:
            logger.warning(f"Could not fetch job data for {job_id}: {e}")
            job_data = {}

        # Build task payload
        task_payload = {"job_id": job_id}

        # Include encrypted token if present
        if "auth_token_encrypted" in job_data:
            task_payload["auth_token_encrypted"] = job_data["auth_token_encrypted"]
            logger.debug(f"Including encrypted auth token in Cloud Task for job {job_id}")

        # Construct the task
        task: dict[str, Any] = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{self.service_url}{task_path}",
                "headers": {
                    "Content-Type": "application/json",
                },
                "body": json.dumps(task_payload).encode(),
                "oidc_token": {
                    # Use the service account for authentication
                    "service_account_email": f"svg2ooxml-runner@{self.project_id}.iam.gserviceaccount.com",
                },
            }
        }

        # Add schedule delay if specified
        if schedule_delay_seconds > 0 and timestamp_pb2 is not None:
            schedule_time = timestamp_pb2.Timestamp()
            schedule_time.FromDatetime(
                datetime.now(UTC) + timedelta(seconds=schedule_delay_seconds)
            )
            task["schedule_time"] = schedule_time

        try:
            # Create the task
            response = self.client.create_task(
                request={"parent": self.queue_path, "task": task}
            )

            logger.info(
                f"Created Cloud Task for job {job_id}: {response.name}"
            )
            return response.name

        except Exception as e:
            logger.error(f"Failed to create Cloud Task for job {job_id}: {e}")
            raise

    def _process_inline(self, job_id: str) -> None:
        """Fallback execution when Cloud Tasks is unavailable."""

        try:
            from ..services.export_service import ExportService

            export_service = ExportService()
            export_service.process_job(job_id)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Inline processing for job %s failed: %s", job_id, exc, exc_info=True)
            raise


def enqueue_export_job(job_id: str) -> str:
    """
    Enqueue an export job for background processing via Cloud Tasks.

    Args:
        job_id: Unique identifier for the export job

    Returns:
        Task name from Cloud Tasks
    """
    queue = CloudTasksQueue()
    return queue.enqueue_job(job_id)
