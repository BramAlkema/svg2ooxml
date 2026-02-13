"""Export service for managing SVG to PPTX/Slides conversion jobs."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from svg2ooxml.services.fonts import FontFetcher, FontSource

from ..caching.status import job_status_cache
from ..models import RequestedFont, SVGFrame
from .converter import (
    ConversionArtifacts,
    FontDiagnostics,
    render_pptx_for_frames,
    render_pptx_for_frames_parallel,
)
from .dependencies import ExportServiceDependencies, build_export_service_dependencies
from .export_settings import ParallelExportSettings
from .slides_publisher import (
    SlidesPublishingError,
    SlidesPublishResult,
    upload_pptx_to_slides,
)

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


@dataclass(slots=True)
class FontPreparationResult:
    """Information gathered when preparing fonts for a conversion."""

    workspace: Path | None
    directories: tuple[Path, ...]
    downloaded_fonts: list[dict[str, str]]
    missing_sources: list[str]


class ExportService:
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

    # ------------------------------------------------------------------ #
    # Firestore / Storage helpers
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    # Job lifecycle
    # ------------------------------------------------------------------ #

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
        """Register a new export job.

        Args:
            frames: SVG frames to convert
            figma_file_id: Figma file identifier
            figma_file_name: Figma file name
            output_format: Output format (pptx or slides)
            fonts: Optional fonts to download
            user: Optional user authentication info from Firebase (uid, email, token, token_hash)
            parent_folder_id: Optional Google Drive folder ID where Slides should be created
            user_refresh_token: Optional Firebase refresh token for OAuth operations
        """

        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

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

        # Add user authentication info if provided
        if user:
            from ..auth.encryption import encrypt_token

            job_data["user"] = {
                "uid": user["uid"],
                "email": user.get("email"),
                "token_hash": user["token_hash"],
            }

            # Encrypt and store token for background processing
            job_data["auth_token_encrypted"] = encrypt_token(user["token"])

            # Store refresh token if provided (needed for OAuth operations like Slides publishing)
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
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        payload.update(fields)

        self.jobs_collection.document(job_id).update(payload)
        job_status_cache.invalidate(job_id)
        logger.info("Job %s: %s (%.1f%%) - %s", job_id, status.value, progress, message)

    # ------------------------------------------------------------------ #
    # Conversion pipeline
    # ------------------------------------------------------------------ #

    def process_job(self, job_id: str, user_token: str | None = None) -> None:
        """Execute the conversion pipeline for a job.

        Args:
            job_id: Unique identifier for the export job
            user_token: Optional decrypted Firebase ID token for user authentication
        """

        try:
            self.update_job_status(
                job_id=job_id,
                status=ExportStatus.PROCESSING,
                message="Preparing conversion pipeline",
                progress=10.0,
            )

            job_data = self.get_job_status(job_id)

            # Decrypt refresh token if available (needed for OAuth operations like Slides publishing)
            user_refresh_token = None
            if job_data.get("auth_refresh_token_encrypted"):
                from ..auth.encryption import decrypt_token
                try:
                    user_refresh_token = decrypt_token(job_data["auth_refresh_token_encrypted"])
                    logger.info("Job %s: Using refresh token for OAuth operations", job_id)
                except Exception as e:
                    logger.warning("Job %s: Failed to decrypt refresh token: %s", job_id, e)

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
            if "font_prep" in locals() and font_prep.workspace:
                shutil.rmtree(font_prep.workspace, ignore_errors=True)
            if "slides_result" in locals():
                logger.info(
                    "Published Slides presentation %s for job %s",
                    slides_result.file_id,
                    job_id,
                )

    # ------------------------------------------------------------------ #
    # Data loading helpers
    # ------------------------------------------------------------------ #

    def _load_requested_fonts(self, job_data: dict[str, Any]) -> list[RequestedFont]:
        """Return fonts requested for the job."""

        fonts_payload = job_data.get("fonts_detail") or job_data.get("fonts") or []
        requested: list[RequestedFont] = []
        for entry in fonts_payload:
            try:
                requested.append(RequestedFont.model_validate(entry))
            except Exception:
                if isinstance(entry, str):
                    requested.append(RequestedFont.model_validate(entry))
        return requested

    def _load_svg_frames(self, job_id: str, job_data: dict[str, Any]) -> list[SVGFrame]:
        """Fetch SVG payloads and rebuild ``SVGFrame`` models."""

        frames_meta = job_data.get("frames", [])
        svg_collection = self.jobs_collection.document(job_id).collection("svgs")
        svg_docs = svg_collection.stream()

        payloads: list[tuple[int, str]] = []
        for doc in svg_docs:
            entry = doc.to_dict()
            payloads.append((entry.get("frame_index", 0), entry.get("svg_content", "")))

        payloads.sort(key=lambda item: item[0])

        frames: list[SVGFrame] = []
        for index, svg_content in payloads:
            summary = frames_meta[index] if index < len(frames_meta) else {}
            try:
                frames.append(
                    SVGFrame(
                        name=summary.get("name"),
                        svg_content=svg_content,
                        width=float(summary.get("width", 1.0) or 1.0),
                        height=float(summary.get("height", 1.0) or 1.0),
                    )
                )
            except Exception as exc:
                logger.warning("Failed to rebuild frame %s: %s", index, exc)
        return frames

    # ------------------------------------------------------------------ #
    # Font preparation
    # ------------------------------------------------------------------ #

    def _prepare_fonts(self, job_id: str, fonts: Sequence[RequestedFont]) -> FontPreparationResult:
        """Download and cache fonts required for conversion."""

        if not fonts:
            return FontPreparationResult(
                workspace=None,
                directories=(),
                downloaded_fonts=[],
                missing_sources=[],
            )

        workspace = Path(tempfile.mkdtemp(prefix=f"fonts-{job_id}-"))
        directories: set[Path] = set()
        downloaded: list[dict[str, str]] = []
        missing_sources: list[str] = []

        for font in fonts:
            try:
                local_path, source, gcs_path = self._fetch_font_asset(font, workspace)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to prepare font %s: %s", font.family, exc)
                local_path = None
                source = None
                gcs_path = None

            if local_path is None:
                if font.source_url:
                    missing_sources.append(font.family)
                continue

            directories.add(local_path.parent)
            downloaded.append(
                {
                    "family": font.family,
                    "path": str(local_path),
                    "source_url": str(font.source_url) if font.source_url else "",
                    "cache_source": source or "cache",
                    "gcs_path": gcs_path or "",
                }
            )

        return FontPreparationResult(
            workspace=workspace,
            directories=tuple(sorted(directories)),
            downloaded_fonts=downloaded,
            missing_sources=missing_sources,
        )

    def _build_conversion_cache_key(
        self,
        frames: Sequence[SVGFrame],
        fonts: Sequence[RequestedFont],
    ) -> str:
        """Return a hash representing the conversion inputs."""

        hasher = hashlib.sha256()
        version = os.getenv("SVG2OOXML_CACHE_VERSION", "v1")
        hasher.update(version.encode("utf-8"))
        for frame in frames:
            hasher.update((frame.name or "").encode("utf-8"))
            hasher.update(str(frame.width).encode("utf-8"))
            hasher.update(str(frame.height).encode("utf-8"))
            hasher.update(frame.svg_content.encode("utf-8"))
        for font in fonts:
            hasher.update(font.family.encode("utf-8"))
            if font.source_url:
                hasher.update(str(font.source_url).encode("utf-8"))
            hasher.update(str(font.weight or 0).encode("utf-8"))
            hasher.update(font.style.encode("utf-8"))
        return hasher.hexdigest()

    def _maybe_load_cached_conversion(
        self,
        cache_key: str,
        target_path: Path,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Download cached PPTX if available; return (summary, slides metadata)."""

        doc = self.conversion_cache_collection.document(cache_key).get()
        if not doc.exists:
            return None, None

        metadata = doc.to_dict()
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(f"exports/cache/{cache_key}.pptx")
        if not blob.exists():
            self.conversion_cache_collection.document(cache_key).delete()
            return None, None

        blob.download_to_filename(str(target_path))
        summary_json = metadata.get("summary")
        summary: dict[str, Any] | None
        if isinstance(summary_json, str):
            summary = json.loads(summary_json)
        elif isinstance(summary_json, dict):
            summary = summary_json
        else:
            summary = None

        slides_metadata: dict[str, Any] | None = None
        if summary is not None:
            slides_metadata = {
                "file_id": metadata.get("slides_file_id"),
                "web_view_link": metadata.get("slides_web_view_link"),
                "published_url": metadata.get("slides_published_url"),
                "embed_url": metadata.get("slides_embed_url"),
                "thumbnail_urls": metadata.get("slides_thumbnails") or [],
            }
            if not slides_metadata["file_id"]:
                slides_metadata = None

        return summary, slides_metadata

    def _store_conversion_cache(
        self,
        cache_key: str,
        summary: dict[str, Any],
        pptx_path: Path,
    ) -> None:
        """Persist conversion output for reuse."""

        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(f"exports/cache/{cache_key}.pptx")
        blob.upload_from_filename(
            str(pptx_path),
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        payload = {
            "summary": json.dumps(summary),
            "cache_key": cache_key,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": os.getenv("SVG2OOXML_CACHE_VERSION", "v1"),
        }
        self.conversion_cache_collection.document(cache_key).set(payload)

    def _fetch_font_asset(
        self,
        font: RequestedFont,
        workspace: Path,
    ) -> tuple[Path | None, str | None, str | None]:
        """Fetch a font from cache or remote source."""

        if font.source_url is None:
            return None, None, None

        url = str(font.source_url)
        cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        parsed = urlparse(url)
        ext = Path(parsed.path).suffix or ".ttf"
        filename = f"{cache_key}{ext}"
        blob_name = f"fonts/{filename}"
        target_path = workspace / filename

        doc_ref = self.font_cache_collection.document(cache_key)
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(blob_name)

        try:
            doc = doc_ref.get()
        except Exception:
            doc = None

        if doc and doc.exists and blob.exists():
            blob.download_to_filename(str(target_path))
            doc_ref.update({"last_used_at": datetime.now(timezone.utc).isoformat()})
            return target_path, "cache", blob_name

        font_source = FontSource(
            url=url,
            font_family=font.family,
            font_weight=str(font.weight or "regular"),
            font_style=font.style,
        )
        fetched_path = self.font_fetcher.fetch(font_source)
        if fetched_path is None or not fetched_path.exists():
            return None, None, None

        shutil.copy(fetched_path, target_path)
        blob.upload_from_filename(str(target_path), content_type="application/octet-stream")
        timestamp = datetime.now(timezone.utc).isoformat()
        doc_ref.set(
            {
                "family": font.family,
                "source_url": url,
                "gcs_path": blob_name,
                "uploaded_at": timestamp,
                "last_used_at": timestamp,
            }
        )
        return target_path, "downloaded", blob_name

    # ------------------------------------------------------------------ #
    # Packaging helpers
    # ------------------------------------------------------------------ #

    def _build_conversion_summary(
        self,
        conversion: ConversionArtifacts,
        font_prep: FontPreparationResult,
        requested_fonts: Sequence[RequestedFont],
    ) -> dict[str, dict[str, Any]]:
        """Prepare metadata written back to Firestore once complete."""

        stage_totals = conversion.aggregated_trace.get("stage_totals", {})
        geometry_totals = conversion.aggregated_trace.get("geometry_totals", {})
        paint_totals = conversion.aggregated_trace.get("paint_totals", {})
        resvg_metrics = conversion.aggregated_trace.get("resvg_metrics", {})

        font_diag: FontDiagnostics = conversion.font_diagnostics
        requested_names = [font.family for font in requested_fonts]
        font_summary = {
            "requested": requested_names,
            "embedded": font_diag.embedded_fonts,
            "missing": font_diag.missing_fonts,
            "missing_sources": font_prep.missing_sources,
            "downloaded": font_prep.downloaded_fonts,
        }

        conversion_summary = {
            "slide_count": conversion.slide_count,
            "stage_totals": stage_totals,
            "geometry_totals": geometry_totals,
            "paint_totals": paint_totals,
            "resvg_metrics": resvg_metrics,
            "page_titles": conversion.page_titles,
        }

        packaging_totals = conversion.packaging_report.get("stage_totals", {})

        return {
            "conversion": conversion_summary,
            "font": font_summary,
            "packaging": packaging_totals,
        }

    # ------------------------------------------------------------------ #
    # Storage helpers
    # ------------------------------------------------------------------ #

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
        from datetime import timedelta


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
        """Upload ``pptx_path`` to Google Slides and return sharing metadata.

        Args:
            pptx_path: Path to PPTX file to upload
            job_id: Job identifier
            job_data: Job metadata from Firestore
            cache_key: Cache key for the conversion
            user_token: Optional decrypted Firebase ID token for user authentication
            user_refresh_token: Optional decrypted Google OAuth refresh token
        """

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


__all__ = ["ExportService", "ExportStatus", "JobNotFoundError"]
