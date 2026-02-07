"""Batch task helpers that drive the parser, IR converter, and PPTX writer."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from svg2ooxml.common.tempfiles import project_temp_dir
from svg2ooxml.io.pptx_writer import write_pptx

from ..preprocess.services import build_parser_services
from ..svg_parser import SVGParser

try:  # pragma: no cover - optional dependency
    from .huey_app import huey
except Exception:  # pragma: no cover - huey unavailable
    huey = None

logger = logging.getLogger(__name__)


def _convert_single_svg_impl(
    file_data: dict[str, Any],
    conversion_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal helper that runs the parser + IR converter."""

    filename = file_data.get("filename", "unknown.svg")
    content = file_data.get("content", b"")

    logger.info("Starting conversion for %s", filename)

    if isinstance(content, bytes):
        try:
            svg_text = content.decode("utf-8")
        except UnicodeDecodeError:
            logger.error("Failed to decode SVG content for %s", filename)
            return {
                "success": False,
                "input_filename": filename,
                "error_message": "SVG content is not valid UTF-8",
                "error_type": "decode_error",
                "failed_at": datetime.utcnow().isoformat(),
            }
    else:
        svg_text = str(content)

    parser_services = build_parser_services()
    parser = SVGParser(services=parser_services)

    start = time.perf_counter()
    result = parser.parse(svg_text, source_path=str(filename))
    elapsed = time.perf_counter() - start

    response: dict[str, Any] = {
        "success": result.success,
        "input_filename": filename,
        "processing_time": elapsed,
        "element_count": result.element_count,
        "namespace_count": result.namespace_count,
        "completed_at": datetime.utcnow().isoformat(),
        "conversion_options": conversion_options or {},
        "metadata": result.metadata.copy(),
        "services_registered": list(result.services.services.keys()) if result.services else [],
    }

    if not result.success:
        logger.warning("Parser failed for %s: %s", filename, result.error)
        response.update(
            {
                "error_message": result.error,
                "error_type": "parse_error",
            }
        )
        return response

    logger.info(
        "Conversion completed for %s in %.3fs (elements=%d)",
        filename,
        elapsed,
        result.element_count,
    )

    ir_scene = result.metadata.get("ir_scene")
    response.update(
        {
            "width_px": result.width_px,
            "height_px": result.height_px,
            "viewbox_scale": result.viewbox_scale,
        }
    )

    output_path = None
    output_size = 0
    if ir_scene is not None:
        target_path = _resolve_output_path(filename, conversion_options)
        pptx_path = write_pptx(ir_scene, target_path)
        output_path = str(pptx_path)
        try:
            output_size = pptx_path.stat().st_size
        except OSError:
            output_size = 0

    response["output_path"] = output_path
    response["output_size"] = output_size
    response["pptx_slide_count"] = 1 if output_path else 0

    return response


def convert_single_svg(
    file_data: dict[str, Any],
    conversion_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert a single SVG payload using the parser pipeline."""

    return _convert_single_svg_impl(file_data, conversion_options)


if huey is not None:  # pragma: no cover

    @huey.task(retries=1, retry_delay=10)
    def convert_single_svg_task(
        file_data: dict[str, Any],
        conversion_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _convert_single_svg_impl(file_data, conversion_options)

else:  # pragma: no cover
    convert_single_svg_task = None


def process_svg_batch(
    file_list: Iterable[dict[str, Any]],
    conversion_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Process multiple SVG payloads sequentially."""

    items = list(file_list)
    logger.info("Processing batch of %d SVGs", len(items))
    results = [
        _convert_single_svg_impl(file_data, conversion_options)
        for file_data in items
    ]
    success = all(item.get("success") for item in results)
    logger.info("Batch completed: success=%s", success)
    return {
        "success": success,
        "results": results,
        "completed_at": datetime.utcnow().isoformat(),
    }


def enqueue_svg_conversion(content: str | bytes) -> Any:
    """Convenience helper for tests/examples (Huey optional)."""

    file_data = {"filename": "inline.svg", "content": content}
    if convert_single_svg_task is None:
        logger.info("Huey unavailable – running parser inline")
        return _convert_single_svg_impl(file_data)

    return convert_single_svg_task(file_data)


__all__ = [
    "convert_single_svg",
    "convert_single_svg_task",
    "process_svg_batch",
    "enqueue_svg_conversion",
]


def _resolve_output_path(
    input_filename: str,
    conversion_options: dict[str, Any] | None,
) -> Path:
    """Determine the PPTX output location for a conversion run."""

    base_name = Path(input_filename).stem or "slide"
    if conversion_options:
        target = conversion_options.get("output_path")
        if target:
            return Path(target)
        directory = conversion_options.get("output_dir")
        if directory:
            directory_path = Path(directory)
            directory_path.mkdir(parents=True, exist_ok=True)
            return directory_path / f"{base_name}.pptx"

    temp_dir = project_temp_dir()
    unique = uuid4().hex[:8]
    return temp_dir / f"{base_name}-{unique}.pptx"
