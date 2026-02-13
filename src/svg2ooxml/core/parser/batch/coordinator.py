"""Coordinator helpers for parallel batch conversion and stitching."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from .bundles import new_job_id
from .tasks import (
    process_svg_batch_to_bundles,
    render_slide_bundle_task,
    stitch_svg_job,
)


def enqueue_slide_bundles(
    file_list: Iterable[dict[str, Any]],
    *,
    conversion_options: dict[str, Any] | None = None,
    job_id: str | None = None,
    wait: bool = True,
    timeout_s: float | None = None,
    bail: bool = False,
    force_inline: bool = False,
) -> dict[str, Any]:
    """Enqueue slide bundle tasks and optionally wait for completion."""

    items = list(file_list)
    assigned_job_id = job_id or new_job_id()

    if force_inline or render_slide_bundle_task is None:
        result = process_svg_batch_to_bundles(
            items,
            conversion_options=conversion_options,
            job_id=assigned_job_id,
        )
        result["mode"] = "inline"
        return result

    tasks = []
    for index, file_data in enumerate(items, start=1):
        tasks.append(
            render_slide_bundle_task(
                file_data,
                job_id=assigned_job_id,
                slide_index=index,
                conversion_options=conversion_options,
            )
        )

    if not wait:
        return {
            "success": True,
            "job_id": assigned_job_id,
            "task_count": len(tasks),
            "tasks": tasks,
            "mode": "async",
        }

    results: list[dict[str, Any]] = []
    for task in tasks:
        try:
            if hasattr(task, "get"):
                result = task.get(blocking=True, timeout=timeout_s)
            else:
                result = task()
        except Exception as exc:  # pragma: no cover - defensive
            result = {
                "success": False,
                "error_message": str(exc),
                "error_type": "queue_error",
                "failed_at": time.time(),
            }
        results.append(result)
        if bail and not result.get("success"):
            break

    success = all(item.get("success") for item in results) if results else False
    return {
        "success": success,
        "job_id": assigned_job_id,
        "results": results,
        "mode": "async",
        "completed_at": time.time(),
    }


def stitch_and_audit_job(
    job_id: str,
    output_path: str | Path,
    *,
    bundle_dir: str | Path | None = None,
    slide_size_mode: str | None = None,
    openxml_validator: str | None = None,
    openxml_timeout_s: float | None = 60.0,
    openxml_policy: str = "strict",
    openxml_required: bool = False,
) -> dict[str, Any]:
    """Stitch bundles into a PPTX and run OpenXML audit if configured."""

    stitch_result = stitch_svg_job(
        job_id,
        output_path,
        bundle_dir=bundle_dir,
        slide_size_mode=slide_size_mode,
    )
    pptx_path = stitch_result.get("output_path")

    openxml_cmd = _resolve_openxml_validator(
        openxml_validator or os.getenv("OPENXML_VALIDATOR")
    )
    openxml_valid: bool | None = None
    openxml_messages: list[str] | None = None
    if openxml_cmd is not None and pptx_path:
        openxml_valid, openxml_messages = _run_openxml_audit(
            Path(pptx_path),
            openxml_cmd,
            timeout_s=openxml_timeout_s,
            policy=openxml_policy,
        )
    elif openxml_required:
        return {
            **stitch_result,
            "success": False,
            "openxml_valid": None,
            "openxml_messages": ["OpenXML audit required but validator not found."],
        }

    return {
        **stitch_result,
        "openxml_valid": openxml_valid,
        "openxml_messages": openxml_messages,
    }


def convert_svg_batch_parallel(
    file_list: Iterable[dict[str, Any]],
    output_path: str | Path,
    *,
    conversion_options: dict[str, Any] | None = None,
    job_id: str | None = None,
    wait: bool = True,
    timeout_s: float | None = None,
    bail: bool = False,
    force_inline: bool = False,
    bundle_dir: str | Path | None = None,
    slide_size_mode: str | None = None,
    openxml_validator: str | None = None,
    openxml_timeout_s: float | None = 60.0,
    openxml_policy: str = "strict",
    openxml_required: bool = False,
) -> dict[str, Any]:
    """End-to-end helper: enqueue slide bundles, stitch, and audit."""

    bundle_result = enqueue_slide_bundles(
        file_list,
        conversion_options=conversion_options,
        job_id=job_id,
        wait=wait,
        timeout_s=timeout_s,
        bail=bail,
        force_inline=force_inline,
    )
    if not bundle_result.get("success"):
        return bundle_result

    assigned_job_id = bundle_result.get("job_id")
    return stitch_and_audit_job(
        assigned_job_id,
        output_path,
        bundle_dir=bundle_dir or (conversion_options or {}).get("bundle_dir"),
        slide_size_mode=slide_size_mode,
        openxml_validator=openxml_validator,
        openxml_timeout_s=openxml_timeout_s,
        openxml_policy=openxml_policy,
        openxml_required=openxml_required,
    )


def _resolve_openxml_validator(path_value: str | None) -> list[str] | None:
    if not path_value:
        return None
    candidate = Path(path_value).expanduser()
    if candidate.is_dir():
        for name in ("openxml-validator", "openxml-validator.py", "openxml-audit", "openxml-audit.py"):
            path = candidate / name
            if path.exists():
                candidate = path
                break
    if not candidate.exists():
        return None
    if candidate.suffix == ".py":
        return [sys.executable, str(candidate)]
    return [str(candidate)]


def _run_openxml_audit(
    pptx_path: Path,
    validator_cmd: list[str],
    *,
    timeout_s: float | None,
    policy: str = "strict",
) -> tuple[bool | None, list[str] | None]:
    try:
        result = subprocess.run(
            [*validator_cmd, "--policy", policy, str(pptx_path)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return False, [str(exc)]
    output = "\n".join([result.stdout.strip(), result.stderr.strip()]).strip()
    messages = [line for line in output.splitlines() if line.strip()]
    if len(messages) > 25:
        messages = messages[:25]
    return result.returncode == 0, messages or None


__all__ = [
    "enqueue_slide_bundles",
    "stitch_and_audit_job",
    "convert_svg_batch_parallel",
]
