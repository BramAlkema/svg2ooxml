from __future__ import annotations

import pytest

from svg2ooxml.api.services import dependencies
from svg2ooxml.api.services.dependencies import ExportServiceDependencies
from svg2ooxml.api.services.export_service import ExportService
from svg2ooxml.api.services.fakes import (
    FakeFirestoreClient,
    FakeStorageClient,
    OfflineFontFetcher,
)


def test_dependencies_fall_back_to_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dependencies, "_firestore_module", None, raising=False)
    monkeypatch.setattr(dependencies, "_storage_module", None, raising=False)

    resolved = dependencies.build_export_service_dependencies("demo-project")

    assert isinstance(resolved.firestore_client, FakeFirestoreClient)
    assert isinstance(resolved.storage_client, FakeStorageClient)
    assert isinstance(resolved.font_fetcher, OfflineFontFetcher)


def test_dependency_overrides_return_new_instance() -> None:
    baseline = ExportServiceDependencies(
        firestore_client=FakeFirestoreClient(),
        storage_client=FakeStorageClient(),
        font_fetcher=OfflineFontFetcher(),
    )

    overridden = baseline.with_overrides(firestore_client="db", storage_client="storage")

    assert overridden.firestore_client == "db"
    assert overridden.storage_client == "storage"
    assert overridden.font_fetcher is baseline.font_fetcher
    # Baseline remains untouched
    assert isinstance(baseline.firestore_client, FakeFirestoreClient)


def test_export_service_uses_fakes_when_no_gcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dependencies, "_firestore_module", None, raising=False)
    monkeypatch.setattr(dependencies, "_storage_module", None, raising=False)
    monkeypatch.setenv("GCP_PROJECT", "unit-test")

    service = ExportService()

    assert isinstance(service.db, FakeFirestoreClient)
    assert isinstance(service.storage_client, FakeStorageClient)
