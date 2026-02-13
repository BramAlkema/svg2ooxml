from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("huey")

from datetime import UTC, datetime


@pytest.fixture()
def client_with_service(monkeypatch):
    from svg2ooxml.api.services import subscription_repository as repo_module
    from svg2ooxml.api.services.dependencies import ExportServiceDependencies
    from svg2ooxml.api.services.fakes import (
        FakeFirestoreClient,
        FakeStorageClient,
        OfflineFontFetcher,
    )

    # Mock google.auth.default()
    monkeypatch.setattr("google.auth.default", lambda scopes=None: (None, None))

    class _StubSubscriptionRepo:
        def __init__(self) -> None:
            self.usage: dict[tuple[str, str], dict[str, object]] = {}
            self.subscriptions: dict[str, dict[str, object]] = {}

        def get_active_subscription(self, firebase_uid: str):
            return self.subscriptions.get(firebase_uid)

        def get_usage(self, firebase_uid: str, period: str):
            return self.usage.get((firebase_uid, period))

        def increment_usage(self, firebase_uid: str, period: str):
            key = (firebase_uid, period)
            current = self.usage.setdefault(key, {"exportCount": 0})
            current["exportCount"] = int(current.get("exportCount", 0)) + 1
            return current

    monkeypatch.setattr(
        repo_module,
        "SubscriptionRepository",
        lambda: _StubSubscriptionRepo(),
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

        def create_job(
            self,
            frames,
            figma_file_id,
            figma_file_name,
            output_format,
            fonts,
            user,
            parent_folder_id=None,
            user_refresh_token=None,  # Add user_refresh_token here
        ):  # noqa: ARG002
            job_id = "job123"
            now = datetime.now(UTC).isoformat()
            self.jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "message": "Queued",
                "progress": 0.0,
                "created_at": now,
                "updated_at": now,
                "user": {"uid": user["uid"]},
            }
            return job_id

        def get_job_status(self, job_id: str):
            return self.jobs[job_id]

        def delete_job(self, job_id: str) -> None:
            self.jobs.pop(job_id, None)

    service = DummyService()
    monkeypatch.setattr(export_routes, "export_service", service)
    monkeypatch.setattr(export_routes, "enqueue_export_job", lambda job_id: None)
    stub_repo = _StubSubscriptionRepo()
    monkeypatch.setattr(export_routes, "subscription_repo", stub_repo)

    app = FastAPI()
    app.include_router(export_routes.router, prefix="/api/v1")

    current_user = {"uid": "firebase-user"}

    async def _fake_verify(credentials=None):
        return dict(current_user)

    app.dependency_overrides[export_routes.verify_firebase_token] = _fake_verify

    return TestClient(app), service, stub_repo, current_user


def test_create_export_job_route(client_with_service):
    client, service, stub_repo, _ = client_with_service

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
    assert stub_repo.usage
    assert next(iter(stub_repo.usage.values()))["exportCount"] == 1


def test_get_export_job_status_route(client_with_service):
    client, service, _, _ = client_with_service
    now = datetime.now(UTC).isoformat()
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
        "user": {"uid": "firebase-user"},
    }

    response = client.get("/api/v1/export/abc")

    assert response.status_code == 200
    payload = response.json()
    assert payload["slides_url"] == "https://example.com/slides"
    assert payload["pptx_url"] == "https://example.com/pptx"
    assert payload["slides_embed_url"] == "https://example.com/embed"


def test_get_export_job_status_route_rejects_other_owner(client_with_service):
    client, service, _, _ = client_with_service
    now = datetime.now(UTC).isoformat()
    service.jobs["abc"] = {
        "job_id": "abc",
        "status": "completed",
        "message": "Done",
        "progress": 100.0,
        "created_at": now,
        "updated_at": now,
        "user": {"uid": "different-user"},
    }

    response = client.get("/api/v1/export/abc")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job abc not found"


def test_delete_export_job_route_owner_only(client_with_service):
    client, service, _, _ = client_with_service
    now = datetime.now(UTC).isoformat()
    service.jobs["mine"] = {
        "job_id": "mine",
        "status": "queued",
        "message": "Queued",
        "progress": 0.0,
        "created_at": now,
        "updated_at": now,
        "user": {"uid": "firebase-user"},
    }
    service.jobs["theirs"] = {
        "job_id": "theirs",
        "status": "queued",
        "message": "Queued",
        "progress": 0.0,
        "created_at": now,
        "updated_at": now,
        "user": {"uid": "different-user"},
    }

    own_response = client.delete("/api/v1/export/mine")
    other_response = client.delete("/api/v1/export/theirs")

    assert own_response.status_code == 204
    assert "mine" not in service.jobs

    assert other_response.status_code == 404
    assert other_response.json()["detail"] == "Job theirs not found"
    assert "theirs" in service.jobs
