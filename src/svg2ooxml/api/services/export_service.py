"""Export service for managing SVG to PPTX/Slides conversion jobs."""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from google.cloud import firestore, storage

logger = logging.getLogger(__name__)


class ExportStatus(Enum):
    """Job status values."""

    QUEUED = "queued"
    PROCESSING = "processing"
    UPLOADING = "uploading"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobNotFoundError(Exception):
    """Raised when a job ID is not found in Firestore."""


class ExportService:
    """Service for managing export jobs."""

    def __init__(self):
        """Initialize Firestore and Cloud Storage clients."""
        self.project_id = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")

        # Initialize Firestore
        self.db = firestore.Client(project=self.project_id)
        self.jobs_collection = self.db.collection("exports")

        # Initialize Cloud Storage
        self.storage_client = storage.Client(project=self.project_id)
        self.bucket_name = f"{self.project_id}-exports"
        self._ensure_bucket_exists()

        logger.info(f"ExportService initialized for project: {self.project_id}")

    def _ensure_bucket_exists(self):
        """Ensure the Cloud Storage bucket exists."""
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            if not bucket.exists():
                logger.info(f"Creating Cloud Storage bucket: {self.bucket_name}")
                bucket = self.storage_client.create_bucket(
                    self.bucket_name,
                    location="europe-west1",
                )
                # Set lifecycle rule to delete old exports after 7 days
                bucket.add_lifecycle_delete_rule(age=7)
                bucket.patch()
                logger.info(f"Bucket created with 7-day retention policy")
        except Exception as e:
            logger.warning(f"Could not create/verify bucket: {e}")

    async def create_job(
        self,
        frames: list[Any],
        figma_file_id: Optional[str],
        figma_file_name: Optional[str],
        output_format: str,
        fonts: Optional[list[str]],
    ) -> str:
        """
        Create a new export job in Firestore.

        Args:
            frames: List of SVG frame data
            figma_file_id: Optional Figma file identifier
            figma_file_name: Optional Figma file name
            output_format: Either "pptx" or "slides"
            fonts: Optional list of font names

        Returns:
            job_id: Unique identifier for the created job
        """
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        job_data = {
            "job_id": job_id,
            "status": ExportStatus.QUEUED.value,
            "message": "Job queued for processing",
            "progress": 0.0,
            "frame_count": len(frames),
            "output_format": output_format,
            "figma_file_id": figma_file_id,
            "figma_file_name": figma_file_name,
            "fonts": fonts or [],
            "created_at": now,
            "updated_at": now,
            "frames": [
                {
                    "name": frame.name,
                    "width": frame.width,
                    "height": frame.height,
                    "svg_length": len(frame.svg_content),
                }
                for frame in frames
            ],
        }

        # Store in Firestore
        self.jobs_collection.document(job_id).set(job_data)
        logger.info(f"Created job {job_id} with {len(frames)} frames")

        # Store SVG content separately (can be large)
        for idx, frame in enumerate(frames):
            svg_doc = self.jobs_collection.document(job_id).collection("svgs").document(str(idx))
            svg_doc.set({
                "frame_index": idx,
                "svg_content": frame.svg_content,
            })

        return job_id

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """
        Retrieve job status from Firestore.

        Args:
            job_id: Unique job identifier

        Returns:
            Job data dictionary

        Raises:
            JobNotFoundError: If job_id is not found
        """
        doc = self.jobs_collection.document(job_id).get()

        if not doc.exists:
            raise JobNotFoundError(f"Job {job_id} not found")

        return doc.to_dict()

    async def update_job_status(
        self,
        job_id: str,
        status: ExportStatus,
        message: str,
        progress: float,
        **kwargs,
    ):
        """
        Update job status in Firestore.

        Args:
            job_id: Unique job identifier
            status: New status value
            message: Status message
            progress: Progress percentage (0-100)
            **kwargs: Additional fields to update
        """
        update_data = {
            "status": status.value,
            "message": message,
            "progress": progress,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        update_data.update(kwargs)

        self.jobs_collection.document(job_id).update(update_data)
        logger.info(f"Job {job_id}: {status.value} - {message} ({progress}%)")

    async def process_job(self, job_id: str):
        """
        Process an export job (background task).

        This is the main conversion pipeline:
        1. Retrieve SVG frames from Firestore
        2. Convert each SVG to a slide using svg2ooxml
        3. Create PPTX file
        4. Upload to Cloud Storage
        5. Optionally publish to Google Slides
        6. Update job status with URLs

        Args:
            job_id: Unique job identifier
        """
        try:
            await self.update_job_status(
                job_id=job_id,
                status=ExportStatus.PROCESSING,
                message="Converting SVG frames to slides",
                progress=10.0,
            )

            # Retrieve job data
            job_data = await self.get_job_status(job_id)

            # Retrieve SVG content
            svgs_ref = self.jobs_collection.document(job_id).collection("svgs")
            svg_docs = svgs_ref.order_by("frame_index").stream()
            svg_frames = [doc.to_dict() for doc in svg_docs]

            logger.info(f"Processing {len(svg_frames)} SVG frames for job {job_id}")

            # TODO: Implement actual conversion using svg2ooxml
            # For now, create a placeholder PPTX
            await self.update_job_status(
                job_id=job_id,
                status=ExportStatus.PROCESSING,
                message=f"Converting {len(svg_frames)} frames to PPTX",
                progress=50.0,
            )

            # Create a temporary PPTX file
            with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
                pptx_path = Path(tmp.name)
                # TODO: Replace with actual conversion
                tmp.write(b"PKZip placeholder")  # Minimal zip header for testing

            # Upload to Cloud Storage
            await self.update_job_status(
                job_id=job_id,
                status=ExportStatus.UPLOADING,
                message="Uploading PPTX to Cloud Storage",
                progress=75.0,
            )

            pptx_url = await self._upload_pptx(job_id, pptx_path)

            # Clean up temp file
            pptx_path.unlink()

            # If output format is "slides", publish to Google Slides
            slides_url = None
            thumbnail_urls = None

            if job_data["output_format"] == "slides":
                await self.update_job_status(
                    job_id=job_id,
                    status=ExportStatus.PUBLISHING,
                    message="Publishing to Google Slides",
                    progress=85.0,
                )
                # TODO: Implement Google Slides publishing
                # slides_url = await self._publish_to_slides(job_id, pptx_path)
                # thumbnail_urls = await self._get_slide_thumbnails(slides_url)

            # Mark as completed
            await self.update_job_status(
                job_id=job_id,
                status=ExportStatus.COMPLETED,
                message="Export completed successfully",
                progress=100.0,
                pptx_url=pptx_url,
                slides_url=slides_url,
                thumbnail_urls=thumbnail_urls,
            )

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            await self.update_job_status(
                job_id=job_id,
                status=ExportStatus.FAILED,
                message="Export failed",
                progress=0.0,
                error=str(e),
            )

    async def _upload_pptx(self, job_id: str, pptx_path: Path) -> str:
        """
        Upload PPTX file to Cloud Storage and return signed URL.

        Args:
            job_id: Job identifier
            pptx_path: Path to PPTX file

        Returns:
            Signed URL for downloading the PPTX
        """
        bucket = self.storage_client.bucket(self.bucket_name)
        blob_name = f"exports/{job_id}/presentation.pptx"
        blob = bucket.blob(blob_name)

        # Upload file
        blob.upload_from_filename(str(pptx_path), content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
        logger.info(f"Uploaded PPTX for job {job_id} to gs://{self.bucket_name}/{blob_name}")

        # Generate signed URL (valid for 7 days)
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=604800,  # 7 days in seconds
            method="GET",
        )

        return signed_url

    async def delete_job(self, job_id: str):
        """
        Delete job and associated resources.

        Args:
            job_id: Job identifier

        Raises:
            JobNotFoundError: If job doesn't exist
        """
        doc_ref = self.jobs_collection.document(job_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise JobNotFoundError(f"Job {job_id} not found")

        # Delete SVG subcollection
        svgs_ref = doc_ref.collection("svgs")
        for svg_doc in svgs_ref.stream():
            svg_doc.reference.delete()

        # Delete Cloud Storage objects
        bucket = self.storage_client.bucket(self.bucket_name)
        blobs = bucket.list_blobs(prefix=f"exports/{job_id}/")
        for blob in blobs:
            blob.delete()
            logger.info(f"Deleted {blob.name}")

        # Delete Firestore document
        doc_ref.delete()
        logger.info(f"Deleted job {job_id}")


__all__ = ["ExportService", "ExportStatus", "JobNotFoundError"]
