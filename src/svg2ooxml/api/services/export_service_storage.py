"""Storage and Slides publishing helpers used by :class:`ExportService`."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from ..caching.status import job_status_cache
from .export_service_exceptions import JobNotFoundError
from .slides_publisher import (
    SlidesPublishingError,
    SlidesPublishResult,
    upload_pptx_to_slides,
)

logger = logging.getLogger(__name__)


class ExportServiceStorageMixin:
    """Mixin containing storage/publishing helpers."""

    def _ensure_bucket_exists(self) -> None:
        """Ensure the Cloud Storage bucket exists with retention policy."""

        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            if bucket.exists():
                return
            logger.info("Creating Cloud Storage bucket: %s", self.bucket_name)
            bucket = self.storage_client.create_bucket(self.bucket_name, location="europe-west1")
            bucket.add_lifecycle_delete_rule(age=7)
            bucket.patch()
            logger.info("Bucket created with 7-day retention policy.")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Unable to verify/create bucket %s: %s", self.bucket_name, exc)

    def delete_job(self, job_id: str) -> None:
        """Remove job metadata and artefacts."""

        doc_ref = self.jobs_collection.document(job_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise JobNotFoundError(f"Job {job_id} not found")

        # Remove stored SVG payloads.
        svgs_ref = doc_ref.collection("svgs")
        for svg_doc in svgs_ref.stream():
            svg_doc.reference.delete()

        # Remove generated assets from Cloud Storage.
        bucket = self.storage_client.bucket(self.bucket_name)
        for blob in bucket.list_blobs(prefix=f"exports/{job_id}/"):
            blob.delete()
            logger.info("Deleted artefact %s for job %s", blob.name, job_id)

        # Finally delete the job document.
        doc_ref.delete()
        job_status_cache.invalidate(job_id)
        logger.info("Deleted job %s", job_id)

    def _upload_pptx(self, job_id: str, pptx_path: Path) -> str:
        """Upload PPTX artefact to Cloud Storage and return a signed URL."""

        bucket = self.storage_client.bucket(self.bucket_name)
        blob_name = f"exports/{job_id}/presentation.pptx"
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(
            str(pptx_path),
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        logger.info("Uploaded PPTX for job %s to gs://%s/%s", job_id, self.bucket_name, blob_name)

        # Use IAM signBlob API for Cloud Run (no key file needed)
        try:
            service_account_email = f"svg2ooxml-runner@{self.project_id}.iam.gserviceaccount.com"

            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(days=7),
                method="GET",
                service_account_email=service_account_email,
            )
            return signed_url
        except Exception as e:
            logger.warning(f"Failed to generate signed URL: {e}. Using public URL.")
            # Fallback: make blob publicly readable and return public URL
            blob.make_public()
            return blob.public_url

    def _publish_to_slides(
        self,
        pptx_path: Path,
        *,
        job_id: str,
        job_data: dict[str, Any],
        cache_key: str,
        user_token: str | None = None,
        user_refresh_token: str | None = None,
    ) -> SlidesPublishResult:
        """Upload ``pptx_path`` to Google Slides and return sharing metadata."""

        presentation_title = job_data.get("figma_file_name") or job_data.get("figma_file_id") or f"Export {job_id}"
        # When publishing with user credentials, respect per-job folder only.
        # Using the shared service folder causes Drive 400 errors because the
        # user account typically lacks access to the service account folder.
        parent_folder = job_data.get("parent_folder_id")
        if not parent_folder and not user_token:
            parent_folder = self.slides_folder_id

        # Extract user_uid from job_data for OAuth token retrieval
        user_uid = None
        if job_data.get("user"):
            user_uid = job_data["user"].get("uid")

        try:
            result = upload_pptx_to_slides(
                pptx_path,
                presentation_title=presentation_title,
                parent_folder_id=parent_folder,
                user_token=user_token,
                user_refresh_token=user_refresh_token,
                user_uid=user_uid,
            )
        except SlidesPublishingError as exc:
            logger.error("Publishing job %s to Slides failed: %s", job_id, exc)
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Unexpected error publishing job %s to Slides: %s", job_id, exc)
            raise SlidesPublishingError(str(exc)) from exc
        try:
            self.conversion_cache_collection.document(cache_key).update(
                {
                    "slides_file_id": result.file_id,
                    "slides_web_view_link": result.web_view_link,
                    "slides_published_url": result.published_url,
                    "slides_embed_url": result.embed_url,
                    "slides_thumbnails": list(result.thumbnail_urls),
                }
            )
        except Exception:  # pragma: no cover - cache is best-effort
            logger.debug("Skipping cache update for Slides metadata on cache_key=%s", cache_key)
        return result


__all__ = ["ExportServiceStorageMixin"]
