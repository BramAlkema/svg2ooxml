"""Export service for managing SVG to PPTX/Slides conversion jobs."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

from google.cloud import firestore, storage

from ..caching import job_status_cache
from ..models import RequestedFont, SVGFrame
from .converter import ConversionArtifacts, FontDiagnostics, render_pptx_for_frames
from svg2ooxml.services.fonts import FontFetcher, FontSource

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

    def __init__(self) -> None:
        self.project_id = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")

        # Firestore handles job metadata and font cache mapping.
        self.db = firestore.Client(project=self.project_id)
        self.jobs_collection = self.db.collection("exports")
        self.font_cache_collection = self.db.collection("font_cache")

        # Cloud Storage contains generated PPTX files and cached font binaries.
        self.storage_client = storage.Client(project=self.project_id)
        self.bucket_name = f"{self.project_id}-exports"
        self._ensure_bucket_exists()

        font_cache_root = Path(tempfile.gettempdir()) / "svg2ooxml-font-cache"
        self.font_fetcher = FontFetcher(cache_directory=font_cache_root)

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
        figma_file_id: Optional[str],
        figma_file_name: Optional[str],
        output_format: str,
        fonts: Optional[Sequence[RequestedFont]],
    ) -> str:
        """Register a new export job."""

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

        self.jobs_collection.document(job_id).set(job_data)
        logger.info("Created job %s with %d frame(s)", job_id, len(frames))

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

    def process_job(self, job_id: str) -> None:
        """Execute the conversion pipeline for a job."""

        try:
            self.update_job_status(
                job_id=job_id,
                status=ExportStatus.PROCESSING,
                message="Preparing conversion pipeline",
                progress=10.0,
            )

            job_data = self.get_job_status(job_id)
            requested_fonts = self._load_requested_fonts(job_data)
            frames = self._load_svg_frames(job_id, job_data)

            font_prep = self._prepare_fonts(job_id, requested_fonts)

            tmp_dir = Path(tempfile.mkdtemp(prefix=f"svg2ooxml-job-{job_id}-"))
            pptx_path = tmp_dir / "presentation.pptx"

            conversion = render_pptx_for_frames(
                frames,
                pptx_path,
                requested_fonts=requested_fonts,
                extra_font_directories=font_prep.directories,
            )

            self.update_job_status(
                job_id=job_id,
                status=ExportStatus.UPLOADING,
                message="Uploading presentation artefacts",
                progress=80.0,
            )

            pptx_url = self._upload_pptx(job_id, conversion.pptx_path)

            slides_url = None
            thumbnail_urls = None

            summary = self._build_conversion_summary(conversion, font_prep, requested_fonts)

            self.update_job_status(
                job_id=job_id,
                status=ExportStatus.COMPLETED,
                message="Export completed successfully",
                progress=100.0,
                pptx_url=pptx_url,
                slides_url=slides_url,
                thumbnail_urls=thumbnail_urls,
                conversion_summary=summary["conversion"],
                font_summary=summary["font"],
                packaging_totals=summary["packaging"],
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

        bucket = self.storage_client.bucket(self.bucket_name)
        blob_name = f"exports/{job_id}/presentation.pptx"
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(
            str(pptx_path),
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        logger.info("Uploaded PPTX for job %s to gs://%s/%s", job_id, self.bucket_name, blob_name)

        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=604800,  # 7 days
            method="GET",
        )
        return signed_url


__all__ = ["ExportService", "ExportStatus", "JobNotFoundError"]
