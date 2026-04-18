"""Font/cache/summary helpers used by :class:`ExportService`."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from svg2ooxml.services.fonts import FontSource

from svg2ooxml.export import ConversionArtifacts, FontDiagnostics, RequestedFont, SVGFrame
from .export_service_types import FontPreparationResult

logger = logging.getLogger(__name__)


class ExportServiceAssetsMixin:
    """Mixin containing font handling and conversion cache helpers."""

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
            "created_at": datetime.now(UTC).isoformat(),
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
            doc_ref.update({"last_used_at": datetime.now(UTC).isoformat()})
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
        timestamp = datetime.now(UTC).isoformat()
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


__all__ = ["ExportServiceAssetsMixin"]
