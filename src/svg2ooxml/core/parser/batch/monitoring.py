"""Monitoring helpers for batch queues and bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .bundles import job_dir

try:  # pragma: no cover - optional dependency
    from .huey_app import huey
except Exception:  # pragma: no cover - huey unavailable
    huey = None


def queue_metrics() -> dict[str, Any]:
    """Return basic queue depth metrics when Huey is available."""

    if huey is None:
        return {"available": False}

    metrics: dict[str, Any] = {"available": True}
    for name in ("pending_count", "scheduled_count", "result_count"):
        fn = getattr(huey, name, None)
        if callable(fn):
            try:
                metrics[name] = fn()
            except Exception:  # pragma: no cover - best effort
                metrics[name] = None
    return metrics


def collect_bundle_metrics(job_id: str, *, base_dir: Path | None = None) -> list[dict[str, Any]]:
    """Collect per-slide metrics from bundle metadata."""

    root = job_dir(job_id, base_dir)
    results: list[dict[str, Any]] = []
    for bundle in sorted(root.glob("slide_*")):
        metadata_path = bundle / "metadata.json"
        if not metadata_path.exists():
            continue
        try:
            data = __import__("json").loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        metrics = data.get("metrics") or {}
        results.append(
            {
                "slide_index": data.get("slide_index"),
                "bundle_dir": str(bundle),
                **metrics,
            }
        )
    return results


__all__ = ["queue_metrics", "collect_bundle_metrics"]
