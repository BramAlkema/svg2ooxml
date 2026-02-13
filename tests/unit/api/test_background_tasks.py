from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from svg2ooxml.api.background.tasks import CloudTasksQueue, tasks_v2


@pytest.fixture
def mock_cloud_tasks(monkeypatch: pytest.MonkeyPatch):
    """Mocks the Cloud Tasks client and returns the mock object."""
    if tasks_v2 is None:
        pytest.skip("google-cloud-tasks is not installed")
    mock_client = (
        MagicMock()
    )  # Directly creating a MagicMock for simplicity
    monkeypatch.setattr(tasks_v2, "CloudTasksClient", lambda: mock_client)
    return mock_client


@pytest.fixture
def mock_firestore(monkeypatch: pytest.MonkeyPatch):
    class _FakeDoc:
        exists = False

        def to_dict(self) -> dict[str, str]:
            return {}

    class _FakeDocument:
        def get(self) -> _FakeDoc:
            return _FakeDoc()

    class _FakeCollection:
        def document(self, _doc_id: str) -> _FakeDocument:
            return _FakeDocument()

    class _FakeFirestoreClient:
        def collection(self, _name: str) -> _FakeCollection:
            return _FakeCollection()

    fake_module = types.SimpleNamespace(
        Client=lambda *args, **kwargs: _FakeFirestoreClient()
    )
    try:
        import google.cloud as google_cloud  # type: ignore
    except Exception:  # pragma: no cover - defensive guard
        google_cloud = None  # type: ignore
    if google_cloud is not None:
        monkeypatch.setattr(google_cloud, "firestore", fake_module, raising=False)
    monkeypatch.setitem(sys.modules, "google.cloud.firestore", fake_module)
    return fake_module


def test_enqueue_job_cloud_tasks(
    mock_cloud_tasks: MagicMock,
    mock_firestore: types.SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("GCP_PROJECT", "demo-project")
    monkeypatch.setenv("SERVICE_URL", "https://example.com")

    queue = CloudTasksQueue()
    task_name = queue.enqueue_job("cloud-job")

    mock_cloud_tasks.create_task.assert_called_once()
    # To keep the test simple, we won't assert the full task dictionary
    # We'll just check that the job_id is in the body
    _, call_kwargs = mock_cloud_tasks.create_task.call_args
    request_dict = call_kwargs["request"]
    assert '"job_id": "cloud-job"' in str(request_dict)
    assert task_name is not None


def test_enqueue_job_inline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GCP_PROJECT", "demo-project")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("SERVICE_URL", raising=False)

    called: list[str] = []

    def fake_inline(self, job_id: str) -> None:  # noqa: ARG001
        called.append(job_id)

    monkeypatch.setattr(
        "svg2ooxml.api.background.tasks.CloudTasksQueue._process_inline",
        fake_inline,
    )

    queue = CloudTasksQueue()
    task_name = queue.enqueue_job("inline-job")

    assert task_name == "inline:inline-job"
    assert called == ["inline-job"]
