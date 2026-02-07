from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_enqueue_export_job_huey(monkeypatch: pytest.MonkeyPatch):
    called: list[str] = []

    def fake_process_export_job(job_id: str) -> None:
        called.append(job_id)

    # Mock the firestore and storage clients before importing the queue module
    mock_firestore = MagicMock()
    monkeypatch.setattr(
        "svg2ooxml.api.services.dependencies._firestore_module.Client",
        lambda project: mock_firestore,
    )
    mock_storage = MagicMock()
    monkeypatch.setattr(
        "svg2ooxml.api.services.dependencies._storage_module.Client",
        lambda project: mock_storage,
    )

    from svg2ooxml.api.background import queue

    monkeypatch.setattr(
        queue, "process_export_job", fake_process_export_job
    )

    queue.enqueue_export_job("huey-job")

    assert called == ["huey-job"]
