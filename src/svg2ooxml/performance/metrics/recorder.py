"""Lightweight metric recorder used throughout svg2ooxml."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BUFFER: list[dict[str, Any]] = []
_LOCK = threading.Lock()

_DEFAULT_METRICS_PATH = Path("reports/metrics.jsonl")


def _serialize_value(value: Any) -> Any:
    """Best-effort serializer for JSON output."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _serialize_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_value(item) for item in value]
    if hasattr(value, "__dict__"):
        return {k: _serialize_value(v) for k, v in vars(value).items()}
    return repr(value)


def _default_metrics_path() -> Path:
    override = os.environ.get("SVG2OOXML_METRICS_PATH")
    if override:
        return Path(override)
    reports_dir = os.environ.get("SVG2OOXML_REPORTS_DIR")
    if reports_dir:
        return Path(reports_dir).expanduser() / "metrics.jsonl"
    return _DEFAULT_METRICS_PATH


def record_metric(
    name: str,
    payload: Mapping[str, Any] | None = None,
    *,
    tags: Mapping[str, Any] | None = None,
    timestamp: datetime | None = None,
    persist: bool | None = None,
) -> dict[str, Any]:
    """Record a metrics event.

    Parameters
    ----------
    name:
        Event name (e.g. ``"parser.run"``).
    payload:
        Arbitrary mapping that can be serialized to JSON.
    tags:
        Optional labels used by dashboards (environment, subsystem, etc.).
    timestamp:
        Override event timestamp. Defaults to ``datetime.now(timezone.utc)``.
    persist:
        When true, append the event to ``reports/metrics.jsonl`` (or the path
        supplied via ``SVG2OOXML_METRICS_PATH``). Defaults to persisting only
        when the environment variable is explicitly provided.

    Returns
    -------
    dict
        The recorded metrics entry.
    """

    event: dict[str, Any] = {
        "name": name,
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "tags": dict(tags or {}),
        "payload": _serialize_value(dict(payload or {})),
    }

    with _LOCK:
        _BUFFER.append(event)

    should_persist = persist
    metrics_path = _default_metrics_path()
    if should_persist is None:
        should_persist = bool(os.environ.get("SVG2OOXML_METRICS_PATH"))

    if should_persist:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        with metrics_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    return event


def get_buffered_metrics() -> list[dict[str, Any]]:
    """Return a snapshot of all metrics recorded during this process."""

    with _LOCK:
        return list(_BUFFER)


def clear_metrics() -> None:
    """Clear the in-memory metrics buffer."""

    with _LOCK:
        _BUFFER.clear()


__all__ = ["record_metric", "get_buffered_metrics", "clear_metrics"]
