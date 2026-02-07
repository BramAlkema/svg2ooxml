"""Tests for the lightweight metrics recorder."""


from svg2ooxml.performance.metrics import recorder


def setup_function(_function) -> None:
    recorder.clear_metrics()


def test_record_metric_buffers_without_persist(tmp_path) -> None:
    metrics_file = tmp_path / "metrics.jsonl"

    # Ensure persistence only happens when requested explicitly.
    recorder.clear_metrics()
    entry = recorder.record_metric(
        "test.event",
        {"value": 42},
        persist=False,
    )

    buffered = recorder.get_buffered_metrics()
    assert buffered[-1]["name"] == "test.event"
    assert entry["payload"]["value"] == 42
    assert not metrics_file.exists()


def test_record_metric_persists_when_env_configured(tmp_path, monkeypatch) -> None:
    target_path = tmp_path / "custom.jsonl"
    monkeypatch.setenv("SVG2OOXML_METRICS_PATH", str(target_path))

    recorder.clear_metrics()
    recorder.record_metric(
        "test.custom",
        {"count": 5},
        tags={"env": "test"},
    )

    assert target_path.exists()
    content = target_path.read_text(encoding="utf-8").strip()
    assert "test.custom" in content


def test_clear_metrics_resets_buffer() -> None:
    recorder.clear_metrics()
    recorder.record_metric("test.event", {"tick": 1}, persist=False)
    assert recorder.get_buffered_metrics()
    recorder.clear_metrics()
    assert recorder.get_buffered_metrics() == []
