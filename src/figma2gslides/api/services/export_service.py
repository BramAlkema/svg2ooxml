"""Export service for managing SVG to PPTX/Slides conversion jobs."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from svg2ooxml.services.fonts import FontFetcher

from ..caching.status import job_status_cache
from svg2ooxml.export import (
    RequestedFont,
    SVGFrame,
    render_pptx_for_frames,
    render_pptx_for_frames_parallel,
)
from .dependencies import ExportServiceDependencies, build_export_service_dependencies
from .export_service_assets import ExportServiceAssetsMixin
from .export_service_data import ExportServiceDataMixin
from .export_service_exceptions import JobNotFoundError
from .export_service_storage import ExportServiceStorageMixin
from .export_service_types import FontPreparationResult
from .export_settings import ParallelExportSettings
from .slides_types import SlidesPublishingError

logger = logging.getLogger(__name__)


class ExportStatus(Enum):
    """Job status values."""

    QUEUED = "queued"
    PROCESSING = "processing"
    UPLOADING = "uploading"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportService(
    ExportServiceDataMixin,
    ExportServiceAssetsMixin,
    ExportServiceStorageMixin,
):
    """Service for managing export jobs end-to-end."""

    def __init__(
        self,
        *,
        dependencies: ExportServiceDependencies | None = None,
        db_client=None,
        storage_client=None,
        font_fetcher: FontFetcher | None = None,
    ) -> None:
        self.project_id = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.slides_folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

        base_dependencies = dependencies or build_export_service_dependencies(self.project_id)
        effective_dependencies = base_dependencies.with_overrides(
            firestore_client=db_client,
            storage_client=storage_client,
            font_fetcher=font_fetcher,
        )

        # Firestore handles job metadata and font cache mapping.
        self.db = effective_dependencies.firestore_client
        self.jobs_collection = self.db.collection("exports")
        self.font_cache_collection = self.db.collection("font_cache")
        self.conversion_cache_collection = self.db.collection("conversion_cache")

        # Cloud Storage contains generated PPTX files and cached font binaries.
        self.storage_client = effective_dependencies.storage_client
        self.bucket_name = f"{self.project_id}-exports"
        self._ensure_bucket_exists()

        self.font_fetcher = effective_dependencies.font_fetcher

        logger.info("ExportService initialised for project %s", self.project_id)

    def create_job(
        self,
        frames: Sequence[SVGFrame],
        figma_file_id: str | None,
        figma_file_name: str | None,
        output_format: str,
        fonts: Sequence[RequestedFont] | None,
        user: dict | None = None,
        parent_folder_id: str | None = None,
        user_refresh_token: str | None = None,
    ) -> str:
        """Register a new export job."""

        job_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        font_payload = [font.model_dump() for font in (fonts or [])]

        job_data = {
            "job_id": job_id,
            "status": ExportStatus.QUEUED.value,
            "message": "Job queued for processing",
            "progress": 0.0,
            "frame_count": len(frames),
            "output_format": output_format,
            "figma_file_id": figma_file_id,
            "figma_file_name": figma_file_name,
            "parent_folder_id": parent_folder_id,
            "fonts_detail": font_payload,
            "fonts_requested": [font["family"] for font in font_payload],
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

        # Add user authentication info if provided.
        if user:
            from ..auth.encryption import encrypt_token

            job_data["user"] = {
                "uid": user["uid"],
                "email": user.get("email"),
                "token_hash": user["token_hash"],
            }

            # Encrypt and store token for background processing.
            job_data["auth_token_encrypted"] = encrypt_token(user["token"])

            # Store refresh token if provided (needed for OAuth operations like Slides publishing).
            if user_refresh_token:
                job_data["auth_refresh_token_encrypted"] = encrypt_token(user_refresh_token)
                logger.info(
                    "Created job %s with %d frame(s) for user %s (with refresh token for OAuth)",
                    job_id,
                    len(frames),
                    user["uid"],
                )
            else:
                logger.info(
                    "Created job %s with %d frame(s) for user %s",
                    job_id,
                    len(frames),
                    user["uid"],
                )
        else:
            logger.info("Created job %s with %d frame(s)", job_id, len(frames))

        self.jobs_collection.document(job_id).set(job_data)

        svg_collection = self.jobs_collection.document(job_id).collection("svgs")
        for idx, frame in enumerate(frames):
            svg_collection.document(str(idx)).set(
                {
                    "frame_index": idx,
                    "svg_content": frame.svg_content,
                }
            )

        job_status_cache.invalidate(job_id)
        return job_id

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Fetch job metadata from Firestore."""

        cached = job_status_cache.get(job_id)
        if cached is not None:
            return cached

        doc = self.jobs_collection.document(job_id).get()
        if not doc.exists:
            raise JobNotFoundError(f"Job {job_id} not found")
        payload = doc.to_dict()
        job_status_cache.set(job_id, payload)
        return payload

    def update_job_status(
        self,
        job_id: str,
        status: ExportStatus,
        message: str,
        progress: float,
        **fields: Any,
    ) -> None:
        """Update job metadata in Firestore."""

        payload = {
            "status": status.value,
            "message": message,
            "progress": progress,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        payload.update(fields)

        self.jobs_collection.document(job_id).update(payload)
        job_status_cache.invalidate(job_id)
        logger.info("Job %s: %s (%.1f%%) - %s", job_id, status.value, progress, message)

    def process_job(self, job_id: str, user_token: str | None = None) -> None:
        """Execute the conversion pipeline for a job."""

        try:
            self.update_job_status(
                job_id=job_id,
                status=ExportStatus.PROCESSING,
                message="Preparing conversion pipeline",
                progress=10.0,
            )

            job_data = self.get_job_status(job_id)

            # Decrypt refresh token if available (needed for OAuth operations like Slides publishing).
            user_refresh_token = None
            if job_data.get("auth_refresh_token_encrypted"):
                from ..auth.encryption import decrypt_token

                try:
                    user_refresh_token = decrypt_token(job_data["auth_refresh_token_encrypted"])
                    logger.info("Job %s: Using refresh token for OAuth operations", job_id)
                except Exception as exc:
                    logger.warning("Job %s: Failed to decrypt refresh token: %s", job_id, exc)

            requested_fonts = self._load_requested_fonts(job_data)
            frames = self._load_svg_frames(job_id, job_data)

            font_prep = self._prepare_fonts(job_id, requested_fonts)

            tmp_dir = Path(tempfile.mkdtemp(prefix=f"svg2ooxml-job-{job_id}-"))
            pptx_path = tmp_dir / "presentation.pptx"

            cache_key = self._build_conversion_cache_key(frames, requested_fonts)
            cached_summary, cached_slides = self._maybe_load_cached_conversion(cache_key, pptx_path)

            if cached_summary is not None:
                summary = cached_summary
            else:
                parallel_settings = ParallelExportSettings.from_env(tmp_dir=tmp_dir)
                if parallel_settings.should_use_parallel(len(frames)):
                    conversion = render_pptx_for_frames_parallel(
                        frames,
                        pptx_path,
                        requested_fonts=requested_fonts,
                        extra_font_directories=font_prep.directories,
                        job_id=job_id,
                        bundle_dir=parallel_settings.bundle_dir,
                        openxml_validator=parallel_settings.openxml_validator,
                        openxml_policy=parallel_settings.openxml_policy,
                        openxml_required=parallel_settings.openxml_required,
                        timeout_s=parallel_settings.timeout_s,
                        bail=parallel_settings.bail,
                    )
                else:
                    conversion = render_pptx_for_frames(
                        frames,
                        pptx_path,
                        requested_fonts=requested_fonts,
                        extra_font_directories=font_prep.directories,
                    )
                summary = self._build_conversion_summary(conversion, font_prep, requested_fonts)
                self._store_conversion_cache(cache_key, summary, conversion.pptx_path)

            self.update_job_status(
                job_id=job_id,
                status=ExportStatus.UPLOADING,
                message="Uploading presentation artefacts",
                progress=80.0,
            )

            pptx_url = self._upload_pptx(job_id, pptx_path)

            slides_url = None
            thumbnail_urls: list[str] | None = None
            slides_embed_url = None
            slides_presentation_id = None
            slides_error = None

            if str(job_data.get("output_format", "pptx")).lower() == "slides":
                if cached_slides and cached_slides.get("web_view_link"):
                    logger.info("Reusing cached Slides presentation %s", cached_slides.get("file_id"))
                    slides_url = cached_slides.get("web_view_link") or cached_slides.get("published_url")
                    slides_embed_url = cached_slides.get("embed_url")
                    slides_presentation_id = cached_slides.get("file_id")
                    thumbnails = cached_slides.get("thumbnail_urls") or []
                    thumbnail_urls = list(thumbnails)
                else:
                    self.update_job_status(
                        job_id=job_id,
                        status=ExportStatus.PUBLISHING,
                        message="Publishing presentation to Google Slides",
                        progress=90.0,
                        pptx_url=pptx_url,
                    )
                    try:
                        slides_result = self._publish_to_slides(
                            pptx_path,
                            job_id=job_id,
                            job_data=job_data,
                            cache_key=cache_key,
                            user_token=user_token,
                            user_refresh_token=user_refresh_token,
                        )
                    except SlidesPublishingError as exc:
                        logger.warning("Job %s: Slides publishing failed (%s)", job_id, exc)
                        slides_error = str(exc)
                    else:
                        slides_url = slides_result.web_view_link or slides_result.published_url
                        slides_embed_url = slides_result.embed_url
                        slides_presentation_id = slides_result.file_id
                        thumbnail_urls = list(slides_result.thumbnail_urls)

            final_message = "Export completed successfully"
            if slides_error:
                final_message = "Export completed (Slides publishing unavailable)"

            self.update_job_status(
                job_id=job_id,
                status=ExportStatus.COMPLETED,
                message=final_message,
                progress=100.0,
                pptx_url=pptx_url,
                slides_url=slides_url,
                thumbnail_urls=thumbnail_urls,
                conversion_summary=summary["conversion"],
                font_summary=summary["font"],
                packaging_totals=summary["packaging"],
                slides_embed_url=slides_embed_url,
                slides_presentation_id=slides_presentation_id,
                slides_error=slides_error,
            )
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.error("Job %s failed: %s", job_id, exc, exc_info=True)
            self.update_job_status(
                job_id=job_id,
                status=ExportStatus.FAILED,
                message="Export failed",
                progress=0.0,
                error=str(exc),
            )
        finally:
            if "conversion" in locals():
                try:
                    conversion.pptx_path.unlink(missing_ok=True)
                except Exception:  # pragma: no cover - best effort
                    pass
            if "tmp_dir" in locals():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            if "font_prep" in locals() and isinstance(font_prep, FontPreparationResult) and font_prep.workspace:
                shutil.rmtree(font_prep.workspace, ignore_errors=True)
            if "slides_result" in locals():
                logger.info(
                    "Published Slides presentation %s for job %s",
                    slides_result.file_id,
                    job_id,
                )


__all__ = ["ExportService", "ExportStatus", "JobNotFoundError"]
