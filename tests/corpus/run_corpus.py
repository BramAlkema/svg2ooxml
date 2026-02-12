#!/usr/bin/env python3
"""Corpus test runner for comprehensive rendering metrics.

This script runs all corpus SVG files through the svg2ooxml pipeline and collects
detailed metrics on rendering decisions (native/EMF/raster rates) and visual fidelity.

Usage:
    python tests/corpus/run_corpus.py
    python tests/corpus/run_corpus.py --output reports/corpus_report.json

Requirements:
    - LibreOffice (soffice) for PPTX rendering
    - Visual testing dependencies: pip install svg2ooxml[visual-testing]

Output:
    Generates corpus_report.json with detailed metrics for each deck.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import functools
import json
import logging
import multiprocessing as mp
import os
import queue
import random
import subprocess
import time
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path for imports (e.g., tools.visual)
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

# Add src to path for imports
sys.path.insert(0, str(project_root / "src"))

from svg2ooxml.core.parser import ParserConfig, SVGParser  # noqa: E402
from svg2ooxml.drawingml.writer import DrawingMLWriter  # noqa: E402
from svg2ooxml.io.pptx_writer import PPTXPackageBuilder  # noqa: E402
from svg2ooxml.ir.entrypoints import convert_parser_output  # noqa: E402
from svg2ooxml.services import configure_services  # noqa: E402

# Import visual tools if available
try:
    from PIL import Image
    from tools.visual.diff import VisualDiffer
    from tools.visual.renderer import LibreOfficeRenderer
    VISUAL_AVAILABLE = True
except ImportError:
    VISUAL_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


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
    validator_cmd: list[str] | None,
    timeout_s: float | None,
) -> tuple[bool | None, list[str] | None]:
    if validator_cmd is None:
        return None, None
    try:
        result = subprocess.run(
            [*validator_cmd, str(pptx_path)],
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


def _extract_resvg_only_misses(report) -> dict[str, int]:
    misses: dict[str, int] = {}
    for event in getattr(report, "geometry_events", []) or []:
        if getattr(event, "decision", None) != "resvg_only_skip":
            continue
        tag = getattr(event, "tag", None) or "unknown"
        misses[tag] = misses.get(tag, 0) + 1
    return misses


def _merge_policy_overrides(*overrides: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for override in overrides:
        if not isinstance(override, dict):
            continue
        for target, values in override.items():
            if not isinstance(values, dict):
                continue
            bucket = merged.setdefault(str(target), {})
            for key, value in values.items():
                bucket[str(key)] = value
    return merged


def _normalize_policy_overrides(
    overrides: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]] | None:
    if not overrides:
        return None
    normalized: dict[str, dict[str, Any]] = {}
    for target, values in overrides.items():
        if not isinstance(values, dict):
            continue
        bucket = normalized.setdefault(str(target), {})
        for key, value in values.items():
            if not isinstance(key, str):
                continue
            if "." in key:
                bucket[key] = value
            else:
                bucket[f"{target}.{key}"] = value
    return normalized or None


@dataclass
class DeckMetrics:
    """Metrics for a single corpus deck."""
    deck_name: str
    source: str
    mode: str  # "resvg"
    
    # Rendering decision metrics
    total_elements: int = 0
    native_count: int = 0
    emf_count: int = 0
    raster_count: int = 0
    
    # Rates (percentages)
    native_rate: float = 0.0
    emf_rate: float = 0.0
    raster_rate: float = 0.0
    
    # Visual fidelity (SSIM if baseline available)
    has_baseline: bool = False
    ssim_score: float | None = None
    visual_fidelity_passed: bool | None = None
    
    # Performance
    conversion_time_ms: float = 0.0

    # OpenXML audit (optional)
    openxml_valid: bool | None = None
    openxml_messages: list[str] | None = None
    
    # Status
    success: bool = True
    error_message: str | None = None

    # Resvg-only geometry misses
    resvg_only_total: int = 0
    resvg_only_misses: dict[str, int] | None = None


@dataclass
class CorpusReport:
    """Complete corpus test report."""
    timestamp: str
    mode: str
    total_decks: int
    successful_decks: int
    failed_decks: int
    
    # Aggregate metrics
    avg_native_rate: float
    avg_emf_rate: float
    avg_raster_rate: float
    avg_ssim_score: float | None
    
    # Per-deck results
    decks: list[dict[str, Any]]
    
    # Target comparison
    targets_met: dict[str, bool]

    # Summary
    summary: str

    # Resvg-only geometry misses (aggregated)
    resvg_only_total: int = 0
    resvg_only_misses: dict[str, int] | None = None

    # Sampling metadata
    available_decks: int | None = None
    sample_size: int | None = None
    sample_seed: int | None = None
    sampled_decks: list[str] | None = None

    # OpenXML audit (aggregate)
    openxml_pass_rate: float | None = None
    openxml_min_pass_rate: float | None = None
    openxml_required: bool = False


def _run_deck_worker(payload: dict[str, Any]) -> DeckMetrics:
    """Worker entry point for parallel deck processing."""
    deck_info = payload["deck"]
    corpus_dir = Path(payload["corpus_dir"])
    output_dir = Path(payload["output_dir"])
    mode = payload.get("mode", "resvg")
    enable_visual = bool(payload.get("enable_visual", False))
    openxml_validator = payload.get("openxml_validator")
    openxml_audit = bool(payload.get("openxml_audit", False))
    openxml_timeout_s = payload.get("openxml_timeout_s")
    write_pptx = bool(payload.get("write_pptx", True))

    deck_name = deck_info["deck_name"]
    svg_file = deck_info["svg_file"]

    logger.info("Processing deck: %s (mode: %s)", deck_name, mode)

    metrics = DeckMetrics(
        deck_name=deck_name,
        source=deck_info.get("source", "Unknown"),
        mode=mode,
    )

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        svg_path = corpus_dir / svg_file
        if not svg_path.exists():
            raise FileNotFoundError(f"SVG file not found: {svg_path}")

        svg_text = svg_path.read_text(encoding="utf-8")

        parser = SVGParser(ParserConfig())
        writer = DrawingMLWriter()
        builder = PPTXPackageBuilder()

        parse_result = parser.parse(svg_text, source_path=str(svg_path))
        if not parse_result.success or parse_result.svg_root is None:
            raise ValueError(f"SVG parsing failed: {parse_result.error_message}")

        filter_strategy = mode
        services = parse_result.services
        if services is None:
            services = configure_services(filter_strategy=filter_strategy)
        elif services.filter_service is not None:
            services.filter_service.set_strategy(filter_strategy)
        if hasattr(writer, "set_image_service"):
            writer.set_image_service(getattr(services, "image_service", None))

        from svg2ooxml.core.tracing.conversion import ConversionTracer
        tracer = ConversionTracer()

        import time
        start_time = time.time()
        policy_overrides = _normalize_policy_overrides(deck_info.get("policy_overrides"))
        scene = convert_parser_output(
            parse_result,
            services=services,
            tracer=tracer,
            overrides=policy_overrides,
        )
        metrics.conversion_time_ms = (time.time() - start_time) * 1000

        render_result = writer.render_scene_from_ir(scene, tracer=tracer)
        pptx_path: Path | None = None
        if write_pptx:
            pptx_path = output_dir / f"{deck_name}_{mode}.pptx"
            builder.build_from_results([render_result], pptx_path)

            if openxml_audit:
                validator_cmd = _resolve_openxml_validator(openxml_validator)
                openxml_valid, openxml_messages = _run_openxml_audit(
                    pptx_path,
                    validator_cmd,
                    openxml_timeout_s,
                )
                metrics.openxml_valid = openxml_valid
                metrics.openxml_messages = openxml_messages

        report = tracer.report()
        geom_totals = report.geometry_totals
        paint_totals = report.paint_totals

        misses = _extract_resvg_only_misses(report)
        if misses:
            metrics.resvg_only_misses = misses
            metrics.resvg_only_total = sum(misses.values())

        metrics.native_count = (
            geom_totals.get("native", 0) +
            geom_totals.get("resvg", 0) +
            geom_totals.get("wordart", 0)
        )
        metrics.emf_count = (
            geom_totals.get("emf", 0) +
            geom_totals.get("policy_emf", 0) +
            paint_totals.get("emf", 0)
        )
        metrics.raster_count = (
            geom_totals.get("bitmap", 0) +
            geom_totals.get("raster", 0) +
            geom_totals.get("policy_raster", 0) +
            paint_totals.get("bitmap", 0)
        )
        metrics.total_elements = metrics.native_count + metrics.emf_count + metrics.raster_count
        if metrics.total_elements == 0:
            metrics.total_elements = len(report.geometry_events) or 1

        if metrics.total_elements > 0:
            metrics.native_rate = metrics.native_count / metrics.total_elements
            metrics.emf_rate = metrics.emf_count / metrics.total_elements
            metrics.raster_rate = metrics.raster_count / metrics.total_elements

        if write_pptx and enable_visual and VISUAL_AVAILABLE:
            renderer = LibreOfficeRenderer()
            differ = VisualDiffer(threshold=0.90)
            if renderer.available:
                try:
                    baseline_path = corpus_dir / "baselines" / deck_name / "slide_1.png"
                    if baseline_path.exists():
                        metrics.has_baseline = True
                        render_dir = output_dir / f"{deck_name}_render"
                        render_dir.mkdir(exist_ok=True)
                        slide_set = renderer.render(pptx_path, render_dir)
                        if slide_set.images:
                            actual_path = slide_set.images[0]
                            baseline_img = Image.open(baseline_path)
                            actual_img = Image.open(actual_path)
                            result = differ.compare(baseline_img, actual_img)
                            metrics.ssim_score = result.ssim_score
                            metrics.visual_fidelity_passed = result.passed
                            logger.info("  SSIM score: %.4f", result.ssim_score)
                except Exception as exc:
                    logger.warning("  Visual fidelity check failed: %s", exc)

        metrics.success = True
        logger.info(
            "  ✓ Success (native: %.1f%%, EMF: %.1f%%, raster: %.1f%%)",
            metrics.native_rate * 100.0,
            metrics.emf_rate * 100.0,
            metrics.raster_rate * 100.0,
        )
    except Exception as exc:
        metrics.success = False
        metrics.error_message = str(exc)
        logger.error("  ✗ Failed: %s", exc)

    return metrics


def _run_deck_process_target(result_queue: mp.Queue, payload: dict[str, Any]) -> None:
    """Top-level process target for timeout wrapper."""
    deck_info = payload.get("deck", {})
    deck_name = deck_info.get("deck_name", "unknown")
    mode = payload.get("mode", "resvg")
    source = deck_info.get("source", "Unknown")
    try:
        result_queue.put(_run_deck_worker(payload))
    except Exception as exc:  # pragma: no cover - defensive
        result_queue.put(
            DeckMetrics(
                deck_name=deck_name,
                source=source,
                mode=mode,
                success=False,
                error_message=str(exc),
            )
        )


def _run_deck_with_timeout(payload: dict[str, Any], timeout_s: float) -> DeckMetrics:
    """Run a deck in a child process with a hard timeout."""
    deck_info = payload["deck"]
    deck_name = deck_info.get("deck_name", "unknown")
    mode = payload.get("mode", "resvg")
    source = deck_info.get("source", "Unknown")

    ctx = mp.get_context("spawn")
    result_queue: mp.Queue = ctx.Queue()

    proc = ctx.Process(target=_run_deck_process_target, args=(result_queue, payload))
    proc.start()
    proc.join(timeout_s)
    if proc.is_alive():
        proc.terminate()
        proc.join(2.0)
        return DeckMetrics(
            deck_name=deck_name,
            source=source,
            mode=mode,
            success=False,
            error_message=f"timeout after {timeout_s:.1f}s",
        )
    try:
        return result_queue.get_nowait()
    except queue.Empty:
        return DeckMetrics(
            deck_name=deck_name,
            source=source,
            mode=mode,
            success=False,
            error_message="worker exited without result",
        )


class CorpusRunner:
    """Runner for corpus testing with metrics collection."""

    @staticmethod
    def _progress_bar(current: int, total: int, width: int = 30) -> str:
        if total <= 0:
            return "[" + ("?" * width) + "]"
        filled = int(width * current / total)
        filled = max(0, min(width, filled))
        return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"
    
    def __init__(
        self,
        corpus_dir: Path,
        output_dir: Path,
        mode: str = "resvg",
        metadata_file: Path | None = None,
        *,
        sample_size: int | None = None,
        sample_seed: int | None = None,
        openxml_validator: str | None = None,
        openxml_timeout_s: float | None = None,
        openxml_audit: bool = False,
        openxml_min_pass_rate: float | None = None,
        openxml_required: bool = False,
        write_pptx: bool = True,
    ):
        """Initialize corpus runner.

        Args:
            corpus_dir: Directory containing corpus SVG files and metadata
            output_dir: Directory for output PPTX files and reports
            mode: Rendering mode ("resvg")
            metadata_file: Path to metadata file (default: corpus_dir/corpus_metadata.json)
            write_pptx: Whether to write PPTX outputs (metrics-only when False)
        """
        self.corpus_dir = corpus_dir
        self.output_dir = output_dir
        self.mode = mode
        self.metadata_file = metadata_file
        self._sample_size = sample_size
        self._sample_seed = sample_seed
        self._openxml_validator = openxml_validator
        self._openxml_timeout_s = openxml_timeout_s
        self._openxml_audit = openxml_audit
        self._openxml_min_pass_rate = openxml_min_pass_rate
        self._openxml_required = openxml_required
        self._write_pptx = write_pptx
        if self._openxml_audit and not self._write_pptx:
            logger.warning("OpenXML audit disabled because PPTX output is disabled.")
            self._openxml_audit = False
        self._openxml_cmd = _resolve_openxml_validator(openxml_validator) if self._openxml_audit else None
        if self._openxml_audit and self._openxml_cmd is None:
            message = f"OpenXML audit enabled but validator not found: {openxml_validator}"
            if self._openxml_required:
                raise RuntimeError(message)
            logger.warning(message)
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize SVG2OOXML pipeline
        self._parser = SVGParser(ParserConfig())
        self._writer = DrawingMLWriter()
        self._builder = PPTXPackageBuilder()
        
        # Initialize visual tools if available
        self._renderer = None
        self._differ = None
        if VISUAL_AVAILABLE and self._write_pptx:
            self._renderer = LibreOfficeRenderer()
            self._differ = VisualDiffer(threshold=0.90)
    
    def load_metadata(self) -> dict[str, Any]:
        """Load corpus metadata from JSON file."""
        metadata_path = self.metadata_file or (self.corpus_dir / "corpus_metadata.json")
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

        with open(metadata_path, encoding="utf-8") as f:
            return json.load(f)
    
    def run_deck(self, deck_info: dict[str, Any]) -> DeckMetrics:
        """Run a single corpus deck through the pipeline.
        
        Args:
            deck_info: Deck metadata from corpus_metadata.json
            
        Returns:
            DeckMetrics with collected metrics
        """
        deck_name = deck_info["deck_name"]
        svg_file = deck_info["svg_file"]
        
        logger.info(f"Processing deck: {deck_name} (mode: {self.mode})")
        
        metrics = DeckMetrics(
            deck_name=deck_name,
            source=deck_info.get("source", "Unknown"),
            mode=self.mode,
        )
        
        try:
            # Read SVG file
            svg_path = self.corpus_dir / svg_file
            if not svg_path.exists():
                raise FileNotFoundError(f"SVG file not found: {svg_path}")
            
            svg_text = svg_path.read_text(encoding="utf-8")
            
            # Parse SVG
            parse_result = self._parser.parse(svg_text, source_path=str(svg_path))
            if not parse_result.success or parse_result.svg_root is None:
                raise ValueError(f"SVG parsing failed: {parse_result.error_message}")
            
            # Configure services with appropriate mode
            filter_strategy = self.mode
            services = parse_result.services
            if services is None:
                services = configure_services(filter_strategy=filter_strategy)
            elif services.filter_service is not None:
                services.filter_service.set_strategy(filter_strategy)
            if hasattr(self._writer, "set_image_service"):
                self._writer.set_image_service(getattr(services, "image_service", None))
            
            # Convert to IR
            from svg2ooxml.core.tracing.conversion import ConversionTracer
            tracer = ConversionTracer()
            
            import time
            start_time = time.time()
            policy_overrides = _normalize_policy_overrides(deck_info.get("policy_overrides"))
            scene = convert_parser_output(
                parse_result,
                services=services,
                tracer=tracer,
                overrides=policy_overrides,
            )
            conversion_time_ms = (time.time() - start_time) * 1000
            metrics.conversion_time_ms = conversion_time_ms
            
            # Render to DrawingML
            render_result = self._writer.render_scene_from_ir(scene, tracer=tracer)
            
            # Build PPTX (optional)
            pptx_path: Path | None = None
            if self._write_pptx:
                pptx_path = self.output_dir / f"{deck_name}_{self.mode}.pptx"
                self._builder.build_from_results([render_result], pptx_path)

                if self._openxml_cmd is not None:
                    openxml_valid, openxml_messages = _run_openxml_audit(
                        pptx_path,
                        self._openxml_cmd,
                        self._openxml_timeout_s,
                    )
                    metrics.openxml_valid = openxml_valid
                    metrics.openxml_messages = openxml_messages
            
            # Collect telemetry metrics from tracer
            report = tracer.report()
            geom_totals = report.geometry_totals
            paint_totals = report.paint_totals

            misses = _extract_resvg_only_misses(report)
            if misses:
                metrics.resvg_only_misses = misses
                metrics.resvg_only_total = sum(misses.values())

            misses = _extract_resvg_only_misses(report)
            if misses:
                metrics.resvg_only_misses = misses
                metrics.resvg_only_total = sum(misses.values())
            
            # Basic counting logic:
            # Native: 'native', 'resvg' (if resvg produced vector), 'wordart'
            # EMF: 'emf', 'policy_emf'
            # Raster: 'bitmap', 'raster', 'policy_raster'
            
            metrics.native_count = (
                geom_totals.get("native", 0) + 
                geom_totals.get("resvg", 0) + 
                geom_totals.get("wordart", 0)
            )
            metrics.emf_count = (
                geom_totals.get("emf", 0) + 
                geom_totals.get("policy_emf", 0) +
                paint_totals.get("emf", 0)
            )
            metrics.raster_count = (
                geom_totals.get("bitmap", 0) + 
                geom_totals.get("raster", 0) + 
                geom_totals.get("policy_raster", 0) +
                paint_totals.get("bitmap", 0)
            )
            metrics.total_elements = metrics.native_count + metrics.emf_count + metrics.raster_count
            
            # Handle text runs if they are recorded separately in paint decisions
            # (In some modes, text runs might add to native count)
            if metrics.total_elements == 0:
                 # Fallback to total events if no decisions recorded (unlikely but safe)
                 metrics.total_elements = len(report.geometry_events) or 1
            
            # Calculate rates
            if metrics.total_elements > 0:
                metrics.native_rate = metrics.native_count / metrics.total_elements
                metrics.emf_rate = metrics.emf_count / metrics.total_elements
                metrics.raster_rate = metrics.raster_count / metrics.total_elements
            
            # Visual fidelity check (if renderer available)
            if self._write_pptx and self._renderer and self._renderer.available and self._differ:
                try:
                    baseline_path = self.corpus_dir / "baselines" / deck_name / "slide_1.png"
                    if baseline_path.exists():
                        metrics.has_baseline = True
                        
                        # Render PPTX to PNG
                        render_dir = self.output_dir / f"{deck_name}_render"
                        render_dir.mkdir(exist_ok=True)
                        slide_set = self._renderer.render(pptx_path, render_dir)
                        
                        if slide_set.images:
                            actual_path = slide_set.images[0]
                            baseline_img = Image.open(baseline_path)
                            actual_img = Image.open(actual_path)
                            
                            result = self._differ.compare(baseline_img, actual_img)
                            metrics.ssim_score = result.ssim_score
                            metrics.visual_fidelity_passed = result.passed
                            
                            logger.info(f"  SSIM score: {result.ssim_score:.4f}")
                except Exception as e:
                    logger.warning(f"  Visual fidelity check failed: {e}")
            
            metrics.success = True
            logger.info(f"  ✓ Success (native: {metrics.native_rate:.1%}, EMF: {metrics.emf_rate:.1%}, raster: {metrics.raster_rate:.1%})")
            
        except Exception as e:
            metrics.success = False
            metrics.error_message = str(e)
            logger.error(f"  ✗ Failed: {e}")
        
        return metrics

    def run_deck_to_stream(
        self,
        deck_info: dict[str, Any],
        stream: Any,
    ) -> DeckMetrics:
        """Run a single corpus deck and add the rendered slide to a streaming writer."""
        if not self._write_pptx:
            raise RuntimeError("Streaming output requires PPTX output to be enabled.")
        deck_name = deck_info["deck_name"]
        svg_file = deck_info["svg_file"]

        logger.info(f"Processing deck: {deck_name} (mode: {self.mode})")

        metrics = DeckMetrics(
            deck_name=deck_name,
            source=deck_info.get("source", "Unknown"),
            mode=self.mode,
        )

        try:
            svg_path = self.corpus_dir / svg_file
            if not svg_path.exists():
                raise FileNotFoundError(f"SVG file not found: {svg_path}")

            svg_text = svg_path.read_text(encoding="utf-8")

            parse_result = self._parser.parse(svg_text, source_path=str(svg_path))
            if not parse_result.success or parse_result.svg_root is None:
                raise ValueError(f"SVG parsing failed: {parse_result.error_message}")

            filter_strategy = self.mode
            services = parse_result.services
            if services is None:
                services = configure_services(filter_strategy=filter_strategy)
            elif services.filter_service is not None:
                services.filter_service.set_strategy(filter_strategy)

            from svg2ooxml.core.tracing.conversion import ConversionTracer
            tracer = ConversionTracer()

            import time
            start_time = time.time()
            policy_overrides = _normalize_policy_overrides(deck_info.get("policy_overrides"))
            scene = convert_parser_output(
                parse_result,
                services=services,
                tracer=tracer,
                overrides=policy_overrides,
            )
            conversion_time_ms = (time.time() - start_time) * 1000
            metrics.conversion_time_ms = conversion_time_ms

            render_result = self._writer.render_scene_from_ir(scene, tracer=tracer)
            stream.add_slide(render_result)

            report = tracer.report()
            geom_totals = report.geometry_totals
            paint_totals = report.paint_totals

            metrics.native_count = (
                geom_totals.get("native", 0)
                + geom_totals.get("resvg", 0)
                + geom_totals.get("wordart", 0)
            )
            metrics.emf_count = (
                geom_totals.get("emf", 0)
                + geom_totals.get("policy_emf", 0)
                + paint_totals.get("emf", 0)
            )
            metrics.raster_count = (
                geom_totals.get("bitmap", 0)
                + geom_totals.get("raster", 0)
                + geom_totals.get("policy_raster", 0)
                + paint_totals.get("bitmap", 0)
            )
            metrics.total_elements = metrics.native_count + metrics.emf_count + metrics.raster_count
            if metrics.total_elements == 0:
                metrics.total_elements = len(report.geometry_events) or 1

            if metrics.total_elements > 0:
                metrics.native_rate = metrics.native_count / metrics.total_elements
                metrics.emf_rate = metrics.emf_count / metrics.total_elements
                metrics.raster_rate = metrics.raster_count / metrics.total_elements

            metrics.success = True
            logger.info(
                "  ✓ Success (native: %.1f%%, EMF: %.1f%%, raster: %.1f%%)",
                metrics.native_rate * 100.0,
                metrics.emf_rate * 100.0,
                metrics.raster_rate * 100.0,
            )
        except Exception as e:
            metrics.success = False
            metrics.error_message = str(e)
            logger.error(f"  ✗ Failed: {e}")

        return metrics
    
    def run_all(
        self,
        *,
        workers: int = 1,
        buffer: int | None = None,
        timeout_s: float | None = None,
        bail: bool = False,
        single_deck: bool = False,
        single_deck_output: Path | None = None,
    ) -> CorpusReport:
        """Run all corpus decks and generate report.
        
        Returns:
            CorpusReport with aggregate metrics and per-deck results
        """
        metadata = self.load_metadata()
        decks = metadata.get("decks", [])
        available_total = len(decks)
        sample_config = metadata.get("sample", {}) if isinstance(metadata.get("sample"), dict) else {}
        sample_size = self._sample_size if self._sample_size is not None else sample_config.get("size")
        sample_seed = self._sample_seed if self._sample_seed is not None else sample_config.get("seed")
        sampled_decks: list[str] | None = None

        if sample_size is not None:
            sample_size = int(sample_size)
            if sample_size < 0:
                raise ValueError("sample-size must be a positive integer")
        if sample_seed is not None:
            sample_seed = int(sample_seed)

        if sample_size and sample_size > 0:
            ordered = sorted(decks, key=lambda d: d.get("deck_name", ""))
            effective_seed = sample_seed if sample_seed is not None else 0
            rng = random.Random(effective_seed)
            rng.shuffle(ordered)
            decks = ordered[: min(sample_size, len(ordered))]
            sampled_decks = [deck.get("deck_name", "") for deck in decks]
        global_overrides = metadata.get("policy_overrides")
        if global_overrides:
            decks = [
                dict(deck, policy_overrides=_merge_policy_overrides(global_overrides, deck.get("policy_overrides")))
                for deck in decks
            ]
        targets = metadata.get("targets", {})
        
        planned_total = len(decks)
        if not self._write_pptx and single_deck:
            raise ValueError("Single-deck output requires PPTX output to be enabled.")
        if single_deck and timeout_s is not None:
            logger.warning(
                "Per-deck timeouts are not supported in single-deck streaming mode; disabling timeout."
            )
            timeout_s = None
        if single_deck and workers > 1:
            logger.info("Single-deck output requested; forcing sequential execution.")
            workers = 1
        if bail and workers > 1:
            logger.info("Bail enabled; forcing sequential execution.")
            workers = 1

        logger.info(f"Running corpus tests for {planned_total} decks in {self.mode} mode")
        
        results: list[DeckMetrics] = []
        total = planned_total

        if timeout_s is not None:
            logger.info("Per-deck timeout enabled: %.1fs", timeout_s)

        if workers <= 1:
            if single_deck:
                output_path = single_deck_output or (self.output_dir / f"corpus_{self.mode}.pptx")
                slides_added = 0
                with self._builder.begin_streaming() as stream:
                    for index, deck_info in enumerate(decks, start=1):
                        bar = self._progress_bar(index, total)
                        percent = (index / total * 100.0) if total else 0.0
                        logger.info("Progress %s %d/%d (%.1f%%)", bar, index, total, percent)
                        metrics = self.run_deck_to_stream(deck_info, stream)
                        if metrics.success:
                            slides_added += 1
                        results.append(metrics)
                        if bail and not metrics.success:
                            logger.warning(
                                "Bailing after failure in deck: %s",
                                metrics.deck_name,
                            )
                            break
                    if slides_added > 0:
                        stream.finalize(output_path)
                        logger.info("Single-deck PPTX saved to: %s", output_path)
                        if self._openxml_cmd is not None:
                            openxml_valid, openxml_messages = _run_openxml_audit(
                                output_path,
                                self._openxml_cmd,
                                self._openxml_timeout_s,
                            )
                            status = "PASS" if openxml_valid else "FAIL"
                            logger.info("OpenXML audit (%s): %s", status, output_path)
                            if openxml_messages:
                                for line in openxml_messages:
                                    logger.info("  %s", line)
            else:
                for index, deck_info in enumerate(decks, start=1):
                    bar = self._progress_bar(index, total)
                    percent = (index / total * 100.0) if total else 0.0
                    logger.info("Progress %s %d/%d (%.1f%%)", bar, index, total, percent)
                    if timeout_s is None:
                        metrics = self.run_deck(deck_info)
                    else:
                        payload = {
                            "deck": deck_info,
                            "corpus_dir": str(self.corpus_dir),
                            "output_dir": str(self.output_dir),
                            "mode": self.mode,
                            "enable_visual": bool(self._renderer and self._renderer.available and self._write_pptx),
                            "openxml_audit": self._openxml_audit,
                            "openxml_validator": self._openxml_validator,
                            "openxml_timeout_s": self._openxml_timeout_s,
                            "write_pptx": self._write_pptx,
                        }
                        metrics = _run_deck_with_timeout(payload, timeout_s)
                    results.append(metrics)
                    if bail and not metrics.success:
                        logger.warning(
                            "Bailing after failure in deck: %s",
                            metrics.deck_name,
                        )
                        break
        else:
            if self._renderer is not None and self._renderer.available:
                logger.warning("Visual fidelity checks are disabled in parallel mode.")

            max_workers = max(1, workers)
            buffer_size = buffer if buffer and buffer > 0 else max_workers * 2
            logger.info(
                "Parallel mode enabled (workers=%d, buffer=%d)",
                max_workers,
                buffer_size,
            )

            ctx = mp.get_context("spawn")
            completed = 0
            deck_iter = iter(decks)
            pending: dict[concurrent.futures.Future[DeckMetrics], None] = {}

            def create_executor(force_thread: bool) -> tuple[concurrent.futures.Executor, str]:
                if force_thread:
                    return (
                        concurrent.futures.ThreadPoolExecutor(max_workers=max_workers),
                        "thread",
                    )
                try:
                    return (
                        concurrent.futures.ProcessPoolExecutor(
                            max_workers=max_workers,
                            mp_context=ctx,
                        ),
                        "process",
                    )
                except PermissionError as exc:
                    logger.warning(
                        "Process pool unavailable (%s); falling back to ThreadPoolExecutor.",
                        exc,
                    )
                    return (
                        concurrent.futures.ThreadPoolExecutor(max_workers=max_workers),
                        "thread",
                    )
                except OSError as exc:
                    logger.warning(
                        "Process pool unavailable (%s); falling back to ThreadPoolExecutor.",
                        exc,
                    )
                    return (
                        concurrent.futures.ThreadPoolExecutor(max_workers=max_workers),
                        "thread",
                    )

            if timeout_s is None:
                worker_fn: Any = _run_deck_worker
            else:
                worker_fn = functools.partial(_run_deck_with_timeout, timeout_s=timeout_s)

            def submit_next(executor: concurrent.futures.Executor) -> None:
                nonlocal pending
                try:
                    deck_info = next(deck_iter)
                except StopIteration:
                    return
                payload = {
                    "deck": deck_info,
                    "corpus_dir": str(self.corpus_dir),
                    "output_dir": str(self.output_dir),
                    "mode": self.mode,
                    "enable_visual": False,
                    "openxml_audit": self._openxml_audit,
                    "openxml_validator": self._openxml_validator,
                    "openxml_timeout_s": self._openxml_timeout_s,
                    "write_pptx": self._write_pptx,
                }
                pending[executor.submit(worker_fn, payload)] = None

            if timeout_s is not None:
                if buffer is not None and buffer_size != max_workers:
                    logger.info("Buffer ignored for timeout runs; using workers=%d.", max_workers)

                active: list[dict[str, Any]] = []

                def start_next_process() -> bool:
                    nonlocal completed
                    try:
                        deck_info = next(deck_iter)
                    except StopIteration:
                        return False
                    payload = {
                        "deck": deck_info,
                        "corpus_dir": str(self.corpus_dir),
                        "output_dir": str(self.output_dir),
                        "mode": self.mode,
                        "enable_visual": False,
                        "openxml_audit": self._openxml_audit,
                        "openxml_validator": self._openxml_validator,
                        "openxml_timeout_s": self._openxml_timeout_s,
                        "write_pptx": self._write_pptx,
                    }
                    result_queue: mp.Queue = ctx.Queue()
                    proc = ctx.Process(
                        target=_run_deck_process_target,
                        args=(result_queue, payload),
                    )
                    try:
                        proc.start()
                    except Exception as exc:
                        logger.error("Failed to start deck %s: %s", deck_info.get("deck_name", "unknown"), exc)
                        metrics = DeckMetrics(
                            deck_name=deck_info.get("deck_name", "unknown"),
                            source=deck_info.get("source", "Unknown"),
                            mode=self.mode,
                            success=False,
                            error_message=str(exc),
                        )
                        results.append(metrics)
                        completed += 1
                        bar = self._progress_bar(completed, total)
                        percent = (completed / total * 100.0) if total else 0.0
                        logger.info(
                            "Progress %s %d/%d (%.1f%%)",
                            bar,
                            completed,
                            total,
                            percent,
                        )
                        return True
                    active.append(
                        {
                            "proc": proc,
                            "queue": result_queue,
                            "start": time.monotonic(),
                            "deck": deck_info,
                        }
                    )
                    logger.info("Started deck: %s", deck_info.get("deck_name", "unknown"))
                    return True

                while len(active) < max_workers and start_next_process():
                    pass

                while active:
                    progress_made = False
                    now = time.monotonic()
                    for entry in list(active):
                        proc = entry["proc"]
                        deck_info = entry["deck"]
                        deck_name = deck_info.get("deck_name", "unknown")
                        elapsed = now - entry["start"]
                        if not proc.is_alive():
                            proc.join()
                            try:
                                metrics = entry["queue"].get_nowait()
                            except queue.Empty:
                                metrics = DeckMetrics(
                                    deck_name=deck_name,
                                    source=deck_info.get("source", "Unknown"),
                                    mode=self.mode,
                                    success=False,
                                    error_message="worker exited without result",
                                )
                            results.append(metrics)
                            completed += 1
                            logger.info(
                                "Completed deck: %s (status=%s, elapsed=%.1fs)",
                                metrics.deck_name,
                                "ok" if metrics.success else "fail",
                                elapsed,
                            )
                            bar = self._progress_bar(completed, total)
                            percent = (completed / total * 100.0) if total else 0.0
                            logger.info(
                                "Progress %s %d/%d (%.1f%%)",
                                bar,
                                completed,
                                total,
                                percent,
                            )
                            active.remove(entry)
                            progress_made = True
                            if bail and not metrics.success:
                                logger.warning(
                                    "Bailing after failure in deck: %s",
                                    metrics.deck_name,
                                )
                                for remaining in list(active):
                                    remaining["proc"].terminate()
                                    remaining["proc"].join(2.0)
                                active.clear()
                                break
                        elif timeout_s is not None and elapsed > timeout_s:
                            logger.warning("Timeout deck: %s after %.1fs", deck_name, elapsed)
                            proc.terminate()
                            proc.join(2.0)
                            metrics = DeckMetrics(
                                deck_name=deck_name,
                                source=deck_info.get("source", "Unknown"),
                                mode=self.mode,
                                success=False,
                                error_message=f"timeout after {timeout_s:.1f}s",
                            )
                            results.append(metrics)
                            completed += 1
                            logger.info(
                                "Completed deck: %s (status=timeout, elapsed=%.1fs)",
                                deck_name,
                                elapsed,
                            )
                            bar = self._progress_bar(completed, total)
                            percent = (completed / total * 100.0) if total else 0.0
                            logger.info(
                                "Progress %s %d/%d (%.1f%%)",
                                bar,
                                completed,
                                total,
                                percent,
                            )
                            active.remove(entry)
                            progress_made = True
                            if bail:
                                logger.warning(
                                    "Bailing after timeout in deck: %s",
                                    deck_name,
                                )
                                for remaining in list(active):
                                    remaining["proc"].terminate()
                                    remaining["proc"].join(2.0)
                                active.clear()
                                break

                    while len(active) < max_workers and start_next_process():
                        progress_made = True

                    if not progress_made:
                        time.sleep(0.05)
            else:
                executor, executor_kind = create_executor(timeout_s is not None)
                logger.info("Parallel executor: %s", executor_kind)
                with executor:
                    while len(pending) < buffer_size:
                        before = len(pending)
                        submit_next(executor)
                        if len(pending) == before:
                            break

                    while pending:
                        done, _ = concurrent.futures.wait(
                            pending,
                            return_when=concurrent.futures.FIRST_COMPLETED,
                        )
                        for fut in done:
                            pending.pop(fut, None)
                            try:
                                metrics = fut.result()
                            except Exception as exc:  # pragma: no cover - defensive
                                metrics = DeckMetrics(
                                    deck_name="unknown",
                                    source="Unknown",
                                    mode=self.mode,
                                    success=False,
                                    error_message=str(exc),
                                )
                                logger.error("Worker failed: %s", exc)
                            results.append(metrics)
                            completed += 1
                            logger.info(
                                "Completed deck: %s (status=%s)",
                                metrics.deck_name,
                                "ok" if metrics.success else "fail",
                            )
                            bar = self._progress_bar(completed, total)
                            percent = (completed / total * 100.0) if total else 0.0
                            logger.info(
                                "Progress %s %d/%d (%.1f%%)",
                                bar,
                                completed,
                                total,
                                percent,
                            )
                            while len(pending) < buffer_size:
                                before = len(pending)
                                submit_next(executor)
                                if len(pending) == before:
                                    break
                            if bail and not metrics.success:
                                logger.warning(
                                    "Bailing after failure in deck: %s",
                                    metrics.deck_name,
                                )
                                for remaining in list(pending):
                                    remaining.cancel()
                                pending.clear()
                                break
        
        # Calculate aggregate metrics
        successful = [r for r in results if r.success]
        total_decks = len(results)
        successful_decks = len(successful)
        failed_decks = total_decks - successful_decks
        
        avg_native = sum(r.native_rate for r in successful) / len(successful) if successful else 0.0
        avg_emf = sum(r.emf_rate for r in successful) / len(successful) if successful else 0.0
        avg_raster = sum(r.raster_rate for r in successful) / len(successful) if successful else 0.0
        
        ssim_scores = [r.ssim_score for r in successful if r.ssim_score is not None]
        avg_ssim = sum(ssim_scores) / len(ssim_scores) if ssim_scores else None
        
        # Check targets
        targets_met = {
            "native_rate": avg_native >= targets.get("native_rate", 0.80),
            "emf_rate": avg_emf <= targets.get("emf_rate_max", 0.15),
            "raster_rate": avg_raster <= targets.get("raster_rate_max", 0.05),
        }
        if avg_ssim is not None:
            targets_met["visual_fidelity"] = avg_ssim >= targets.get("visual_fidelity_min", 0.90)

        resvg_only_misses: dict[str, int] = {}
        for result in results:
            if result.resvg_only_misses:
                for tag, count in result.resvg_only_misses.items():
                    resvg_only_misses[tag] = resvg_only_misses.get(tag, 0) + int(count)
        resvg_only_total = sum(resvg_only_misses.values())
        
        # Generate summary
        if total_decks < planned_total:
            header = (
                f"Corpus test completed (partial): {successful_decks}/{total_decks} "
                f"decks successful (planned {planned_total})"
            )
        else:
            header = f"Corpus test completed: {successful_decks}/{total_decks} decks successful"

        summary_lines = [
            header,
            f"Native rate: {avg_native:.1%} (target: >{targets.get('native_rate', 0.80):.0%}) - {'✓ PASS' if targets_met['native_rate'] else '✗ FAIL'}",
            f"EMF rate: {avg_emf:.1%} (target: <{targets.get('emf_rate_max', 0.15):.0%}) - {'✓ PASS' if targets_met['emf_rate'] else '✗ FAIL'}",
            f"Raster rate: {avg_raster:.1%} (target: <{targets.get('raster_rate_max', 0.05):.0%}) - {'✓ PASS' if targets_met['raster_rate'] else '✗ FAIL'}",
        ]
        if avg_ssim is not None:
            summary_lines.append(
                f"Visual fidelity (SSIM): {avg_ssim:.4f} (target: >{targets.get('visual_fidelity_min', 0.90)}) - "
                f"{'✓ PASS' if targets_met.get('visual_fidelity', False) else '✗ FAIL'}"
            )
        openxml_results = [r.openxml_valid for r in successful if r.openxml_valid is not None]
        openxml_pass_rate: float | None = None
        if openxml_results:
            passed = sum(1 for value in openxml_results if value)
            openxml_pass_rate = passed / len(openxml_results)
            summary_lines.append(
                f"OpenXML audit pass rate: {openxml_pass_rate:.1%} ({passed}/{len(openxml_results)})"
            )
        if self._openxml_min_pass_rate is not None:
            openxml_target_met = (
                openxml_pass_rate is not None
                and openxml_pass_rate >= self._openxml_min_pass_rate
            )
            targets_met["openxml_pass_rate"] = openxml_target_met
            if openxml_pass_rate is None:
                summary_lines.append(
                    "OpenXML audit pass rate target: missing results - ✗ FAIL"
                )
            else:
                summary_lines.append(
                    f"OpenXML audit target: >= {self._openxml_min_pass_rate:.1%} - "
                    f"{'✓ PASS' if openxml_target_met else '✗ FAIL'}"
                )
        if self._openxml_required and openxml_pass_rate is None:
            targets_met["openxml_required"] = False
            summary_lines.append("OpenXML audit required but not executed - ✗ FAIL")
        if resvg_only_total:
            top_tags = sorted(resvg_only_misses.items(), key=lambda item: item[1], reverse=True)[:8]
            top_tags_str = ", ".join(f"{tag}={count}" for tag, count in top_tags)
            summary_lines.append(
                f"Resvg-only geometry skips: {resvg_only_total} (top: {top_tags_str})"
            )
        if sample_size:
            summary_lines.insert(
                1,
                f"Sampled {planned_total}/{available_total} decks (seed={sample_seed or 0})",
            )
        summary = "\n".join(summary_lines)
        
        report = CorpusReport(
            timestamp=datetime.now(UTC).isoformat(),
            mode=self.mode,
            total_decks=total_decks,
            successful_decks=successful_decks,
            failed_decks=failed_decks,
            available_decks=available_total,
            sample_size=int(sample_size) if sample_size else None,
            sample_seed=int(sample_seed) if sample_seed is not None else None,
            sampled_decks=sampled_decks,
            avg_native_rate=avg_native,
            avg_emf_rate=avg_emf,
            avg_raster_rate=avg_raster,
            avg_ssim_score=avg_ssim,
            openxml_pass_rate=openxml_pass_rate,
            openxml_min_pass_rate=self._openxml_min_pass_rate,
            openxml_required=self._openxml_required,
            decks=[asdict(r) for r in results],
            targets_met=targets_met,
            resvg_only_total=resvg_only_total,
            resvg_only_misses=resvg_only_misses or None,
            summary=summary,
        )
        
        logger.info("\n" + "="*60)
        logger.info("CORPUS REPORT")
        logger.info("="*60)
        logger.info(summary)
        logger.info("="*60)
        
        return report


def main():
    """Main entry point for corpus runner."""
    parser = argparse.ArgumentParser(
        description="Run corpus tests and generate metrics report"
    )
    parser.add_argument(
        "--mode",
        choices=["resvg"],
        default="resvg",
        help="Rendering mode (resvg only)",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path(__file__).parent / "real_world",
        help="Corpus directory (default: tests/corpus/real_world)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "output",
        help="Output directory (default: tests/corpus/output)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(__file__).parent / "corpus_report.json",
        help="Report output path (default: tests/corpus/corpus_report.json)",
    )
    parser.add_argument(
        "--skip-pptx",
        action="store_true",
        help="Skip writing PPTX files (metrics only; disables visual/OpenXML checks)",
    )
    parser.add_argument(
        "--openxml-audit",
        action="store_true",
        help="Run OpenXML validator against generated PPTX files",
    )
    parser.add_argument(
        "--openxml-validator",
        type=str,
        help="Path to OpenXML validator executable or directory (default: ../openxml-validator if present)",
    )
    parser.add_argument(
        "--openxml-timeout",
        type=float,
        default=60.0,
        help="Timeout (seconds) for OpenXML validation (default: 60)",
    )
    parser.add_argument(
        "--openxml-min-pass-rate",
        type=float,
        default=None,
        help="Minimum OpenXML audit pass rate required to pass (0.0-1.0).",
    )
    parser.add_argument(
        "--openxml-required",
        action="store_true",
        help="Fail if OpenXML audit cannot be executed (missing validator).",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        help="Path to metadata file (default: corpus-dir/corpus_metadata.json)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes for parallel rendering (default: 1)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Deterministically sample N decks from metadata (optional).",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=None,
        help="Random seed for deterministic sampling (default: 0 when sampling).",
    )
    parser.add_argument(
        "--buffer",
        type=int,
        default=None,
        help="Max in-flight tasks for parallel rendering (default: 2x workers)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Per-deck timeout in seconds (default: disabled)",
    )
    parser.add_argument(
        "--bail",
        action="store_true",
        help="Stop after the first failure or timeout (forces sequential execution)",
    )
    parser.add_argument(
        "--single-deck",
        action="store_true",
        help="Write all slides into a single PPTX instead of per-deck outputs",
    )
    parser.add_argument(
        "--single-deck-output",
        type=Path,
        help="Output path for single-deck PPTX (default: output-dir/corpus_<mode>.pptx)",
    )

    args = parser.parse_args()
    
    if not VISUAL_AVAILABLE:
        logger.warning("Visual testing dependencies not available. SSIM metrics will be skipped.")
        logger.warning("Install with: pip install svg2ooxml[visual-testing]")

    openxml_validator = args.openxml_validator or os.getenv("OPENXML_VALIDATOR")
    openxml_audit = args.openxml_audit or bool(openxml_validator)
    if openxml_audit and openxml_validator is None:
        default_validator_dir = project_root.parent / "openxml-validator"
        if default_validator_dir.exists():
            openxml_validator = str(default_validator_dir)
    if args.skip_pptx:
        if openxml_audit:
            logger.warning("OpenXML audit disabled because --skip-pptx is set.")
            openxml_audit = False
        if args.single_deck:
            logger.warning("Single-deck output disabled because --skip-pptx is set.")
            args.single_deck = False
            args.single_deck_output = None
    if args.openxml_required and not openxml_audit:
        logger.error("OpenXML audit required but not enabled. Provide --openxml-audit or OPENXML_VALIDATOR.")
        sys.exit(2)

    # Run corpus tests
    try:
        runner = CorpusRunner(
            corpus_dir=args.corpus_dir,
            output_dir=args.output_dir,
            mode=args.mode,
            metadata_file=args.metadata,
            sample_size=args.sample_size,
            sample_seed=args.sample_seed,
            openxml_validator=openxml_validator,
            openxml_timeout_s=args.openxml_timeout,
            openxml_audit=openxml_audit,
            openxml_min_pass_rate=args.openxml_min_pass_rate,
            openxml_required=args.openxml_required,
            write_pptx=not args.skip_pptx,
        )
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(2)
    
    report = runner.run_all(
        workers=args.workers,
        buffer=args.buffer,
        timeout_s=args.timeout,
        bail=args.bail,
        single_deck=args.single_deck,
        single_deck_output=args.single_deck_output,
    )
    
    # Save report
    report_dict = asdict(report)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)
    
    logger.info(f"\nReport saved to: {args.report}")
    
    # Exit with appropriate code
    all_targets_met = all(report.targets_met.values())
    sys.exit(0 if all_targets_met and report.failed_decks == 0 else 1)


if __name__ == "__main__":
    main()
