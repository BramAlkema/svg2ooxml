"""Dependency wiring for API services."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from svg2ooxml.services.fonts import FontFetcher

from .fakes import FakeFirestoreClient, FakeStorageClient, OfflineFontFetcher

try:  # pragma: no cover - optional dependency
    from google.cloud import firestore as _firestore_module
except ImportError:  # pragma: no cover - environment without GCP SDK
    _firestore_module = None

try:  # pragma: no cover - optional dependency
    from google.cloud import storage as _storage_module
except ImportError:  # pragma: no cover - environment without GCP SDK
    _storage_module = None


@dataclass(slots=True)
class ExportServiceDependencies:
    """Bundle of services required by :class:`ExportService`."""

    firestore_client: object
    storage_client: object
    font_fetcher: FontFetcher

    def with_overrides(
        self,
        *,
        firestore_client: object | None = None,
        storage_client: object | None = None,
        font_fetcher: FontFetcher | None = None,
    ) -> ExportServiceDependencies:
        return ExportServiceDependencies(
            firestore_client=firestore_client or self.firestore_client,
            storage_client=storage_client or self.storage_client,
            font_fetcher=font_fetcher or self.font_fetcher,
        )


def build_export_service_dependencies(project_id: str | None) -> ExportServiceDependencies:
    """Resolve production or fake dependencies depending on availability."""

    if _firestore_module is not None:
        firestore_client = _firestore_module.Client(project=project_id)
    else:
        firestore_client = FakeFirestoreClient(project=project_id)

    if _storage_module is not None:
        storage_client = _storage_module.Client(project=project_id)
    else:
        storage_client = FakeStorageClient(project=project_id)

    font_fetcher: FontFetcher
    if isinstance(storage_client, FakeStorageClient):
        font_fetcher = OfflineFontFetcher()
    else:
        cache_override = (
            os.getenv("SVG2OOXML_FONT_CACHE_DIR")
            or os.getenv("SVG2OOXML_WEB_FONT_CACHE")
        )
        if cache_override:
            font_cache_root = Path(cache_override).expanduser()
        else:
            font_cache_root = Path(tempfile.gettempdir()) / "svg2ooxml-font-cache"
        font_fetcher = FontFetcher(cache_directory=font_cache_root)

    return ExportServiceDependencies(
        firestore_client=firestore_client,
        storage_client=storage_client,
        font_fetcher=font_fetcher,
    )


__all__ = ["ExportServiceDependencies", "build_export_service_dependencies"]
