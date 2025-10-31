from __future__ import annotations

import os

import pytest

from svg2ooxml.api.background.tasks import CloudTasksQueue


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
