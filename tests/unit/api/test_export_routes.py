from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

@pytest.fixture()
def client_with_service(monkeypatch):
    from fastapi import FastAPI
    from svg2ooxml.api.services.dependencies import ExportServiceDependencies
    from svg2ooxml.api.services.fakes import (
        FakeFirestoreClient,
        FakeStorageClient,
        OfflineFontFetcher,
    )

    def fake_dependencies(project_id):  # noqa: ARG001
        return ExportServiceDependencies(
            firestore_client=FakeFirestoreClient(project="test"),
            storage_client=FakeStorageClient(project="test"),
            font_fetcher=OfflineFontFetcher(),
        )

    monkeypatch.setattr(
        "svg2ooxml.api.services.export_service.build_export_service_dependencies",
        fake_dependencies,
    )

    from svg2ooxml.api.routes import export as export_routes

    class DummyService:
        def __init__(self) -> None:
            self.jobs: dict[str, dict[str, object]] = {}

        def create_job(self, frames, figma_file_id, figma_file_name, output_format, fonts):  # noqa: ARG002
            job_id = "job123"
            now = datetime.utcnow().isoformat()
            self.jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "message": "Queued",
                "progress": 0.0,
                "created_at": now,
                "updated_at": now,
            }
            return job_id

        def get_job_status(self, job_id: str):
            return self.jobs[job_id]

        def delete_job(self, job_id: str) -> None:
            self.jobs.pop(job_id, None)

    service = DummyService()
    monkeypatch.setattr(export_routes, "export_service", service)
    monkeypatch.setattr(export_routes, "enqueue_export_job", lambda job_id: None)

    app = FastAPI()
    app.include_router(export_routes.router, prefix="/api/v1")

    return TestClient(app), service


def test_create_export_job_route(client_with_service):
    client, service = client_with_service

    payload = {
        "frames": [
            {
                "name": "Sample",
                "svg_content": "<svg width='1' height='1'></svg>",
                "width": 1,
                "height": 1,
            }
        ],
        "figma_file_id": "file-id",
        "figma_file_name": "Deck",
        "output_format": "pptx",
        "fonts": ["Inter"],
    }

    response = client.post("/api/v1/export", json=payload)

    assert response.status_code == 202
    data = response.json()
    assert data["job_id"] == "job123"
    assert data["status"] == "queued"
    assert "message" in data
    assert "job123" in service.jobs


def test_get_export_job_status_route(client_with_service):
    client, service = client_with_service
    now = datetime.utcnow().isoformat()
    service.jobs["abc"] = {
        "job_id": "abc",
        "status": "completed",
        "message": "Done",
        "progress": 100.0,
        "pptx_url": "https://example.com/pptx",
        "slides_url": "https://example.com/slides",
        "slides_embed_url": "https://example.com/embed",
        "slides_presentation_id": "slides123",
        "thumbnail_urls": ["https://example.com/thumb.png"],
        "slides_error": None,
        "created_at": now,
        "updated_at": now,
    }

    response = client.get("/api/v1/export/abc")

    assert response.status_code == 200
    payload = response.json()
    assert payload["slides_url"] == "https://example.com/slides"
    assert payload["pptx_url"] == "https://example.com/pptx"
    assert payload["slides_embed_url"] == "https://example.com/embed"
