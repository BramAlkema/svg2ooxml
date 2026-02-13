from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


def _client_with_tasks_route(monkeypatch):
    from svg2ooxml.api.services.dependencies import ExportServiceDependencies
    from svg2ooxml.api.services.fakes import (
        FakeFirestoreClient,
        FakeStorageClient,
        OfflineFontFetcher,
    )

    # Avoid ADC lookups when the route module imports and instantiates ExportService.
    monkeypatch.setattr("google.auth.default", lambda scopes=None: (None, None))

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

    from svg2ooxml.api.routes import tasks as tasks_routes

    monkeypatch.setattr(
        tasks_routes,
        "export_service",
        SimpleNamespace(process_job=lambda job_id, user_token=None: None),
    )

    app = FastAPI()
    app.include_router(tasks_routes.router, prefix="/api/v1/tasks")
    return TestClient(app), tasks_routes


def test_process_export_task_requires_authorization(monkeypatch) -> None:
    client, _ = _client_with_tasks_route(monkeypatch)

    response = client.post("/api/v1/tasks/process-export", json={"job_id": "job-1"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing task authentication token"


def test_process_export_task_propagates_http_errors(monkeypatch) -> None:
    client, tasks_routes = _client_with_tasks_route(monkeypatch)

    def fake_verify(*_args, **_kwargs):
        raise HTTPException(status_code=403, detail="Forbidden task caller")

    monkeypatch.setattr(tasks_routes, "verify_cloud_tasks_bearer_token", fake_verify)

    response = client.post(
        "/api/v1/tasks/process-export",
        json={"job_id": "job-2"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden task caller"


def test_process_export_task_success(monkeypatch) -> None:
    client, tasks_routes = _client_with_tasks_route(monkeypatch)
    calls: list[tuple[str, str | None]] = []

    monkeypatch.setattr(
        tasks_routes,
        "verify_cloud_tasks_bearer_token",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        tasks_routes,
        "export_service",
        SimpleNamespace(
            process_job=lambda job_id, user_token=None: calls.append((job_id, user_token))
        ),
    )

    response = client.post(
        "/api/v1/tasks/process-export",
        json={"job_id": "job-3"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert calls == [("job-3", None)]
