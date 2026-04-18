"""Storage and Slides publishing helpers for ``ExportService``."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .slides_publisher import upload_to_google_slides
from .slides_types import SlidesPublishResult, SlidesPublishingError


class ExportServiceStorageMixin:
    """Mixin containing bucket setup and artefact publishing helpers."""

    def _ensure_bucket_exists(self) -> None:
        bucket = self.storage_client.bucket(self.bucket_name)
        if not bucket.exists():
            location = os.getenv("SVG2OOXML_GCS_LOCATION", "europe-west4")
            self.storage_client.create_bucket(self.bucket_name, location=location)

    def _upload_pptx(self, job_id: str, pptx_path: Path) -> str:
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(f"exports/{job_id}/presentation.pptx")
        blob.upload_from_filename(
            str(pptx_path),
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        return blob.generate_signed_url(version="v4", expiration=timedelta(hours=1), method="GET")

    def _publish_to_slides(
        self,
        pptx_path: Path,
        *,
        job_id: str,
        job_data: dict,
        cache_key: str,
        user_token: str | None = None,
        user_refresh_token: str | None = None,
    ) -> SlidesPublishResult:
        del user_refresh_token
        access_token = user_token or job_data.get("provider_token")
        if not access_token:
            raise SlidesPublishingError("No Google access token available for Slides publishing")

        title = job_data.get("figma_file_name") or f"export-{job_id}"
        published_url = upload_to_google_slides(
            pptx_path.read_bytes(),
            access_token,
            title=title,
        )
        file_id = published_url.rstrip("/").split("/")[-2]
        result = SlidesPublishResult(
            file_id=file_id,
            web_view_link=published_url,
            published_url=published_url,
            embed_url=published_url.replace("/edit", "/embed"),
            thumbnail_urls=(),
        )

        payload = {
            "slides_file_id": result.file_id,
            "slides_web_view_link": result.web_view_link,
            "slides_published_url": result.published_url,
            "slides_embed_url": result.embed_url,
            "slides_thumbnails": list(result.thumbnail_urls),
            "slides_cached_at": datetime.now(UTC).isoformat(),
        }
        self.conversion_cache_collection.document(cache_key).set(payload, merge=True)
        return result
