"""Cloud Tasks integration for background job processing."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from google.cloud import tasks_v2
from google.protobuf import duration_pb2

logger = logging.getLogger(__name__)


class CloudTasksQueue:
    """Wrapper for Google Cloud Tasks queue operations."""

    def __init__(self) -> None:
        """Initialize Cloud Tasks client and queue configuration."""
        self.project_id = os.getenv("GCP_PROJECT")
        self.location = os.getenv("CLOUD_TASKS_LOCATION", "europe-west1")
        self.queue_name = os.getenv("CLOUD_TASKS_QUEUE", "svg2ooxml-jobs")
        self.service_url = os.getenv("SERVICE_URL")

        if not self.project_id:
            raise ValueError("GCP_PROJECT environment variable is required")

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
        # Construct the task
        task: Dict[str, Any] = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{self.service_url}{task_path}",
                "headers": {
                    "Content-Type": "application/json",
                },
                "body": json.dumps({"job_id": job_id}).encode(),
                "oidc_token": {
                    # Use the service account for authentication
                    "service_account_email": f"svg2ooxml-runner@{self.project_id}.iam.gserviceaccount.com",
                },
            }
        }

        # Add schedule delay if specified
        if schedule_delay_seconds > 0:
            task["schedule_time"] = duration_pb2.Duration(
                seconds=schedule_delay_seconds
            )

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
