from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from svg2ooxml.api.background.tasks import CloudTasksQueue, tasks_v2


@pytest.fixture
def mock_cloud_tasks(monkeypatch: pytest.MonkeyPatch):
    """Mocks the Cloud Tasks client and returns the mock object."""
    mock_client = (
        MagicMock()
    )  # Directly creating a MagicMock for simplicity
    monkeypatch.setattr(tasks_v2, "CloudTasksClient", lambda: mock_client)
    return mock_client


def test_enqueue_job_cloud_tasks(
    mock_cloud_tasks: MagicMock, monkeypatch: pytest.MonkeyPatch
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
