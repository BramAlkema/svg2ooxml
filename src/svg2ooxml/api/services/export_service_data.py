"""Data-loading helpers used by :class:`ExportService`."""

from __future__ import annotations

import logging
from typing import Any

from ..models import RequestedFont, SVGFrame

logger = logging.getLogger(__name__)


class ExportServiceDataMixin:
    """Mixin containing Firestore payload reconstruction helpers."""

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


__all__ = ["ExportServiceDataMixin"]
