#!/usr/bin/env python3
"""Corpus test runner for comprehensive rendering metrics.

This script runs all corpus SVG files through the svg2ooxml pipeline and collects
detailed metrics on rendering decisions (native/EMF/raster rates) and visual fidelity.

Usage:
    python tests/corpus/run_corpus.py
    python tests/corpus/run_corpus.py --mode resvg
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
import queue
import time
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
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


@dataclass
class DeckMetrics:
    """Metrics for a single corpus deck."""
    deck_name: str
    source: str
    mode: str  # "legacy" or "resvg"
    
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
    
    # Status
    success: bool = True
    error_message: str | None = None


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


def _run_deck_worker(payload: dict[str, Any]) -> DeckMetrics:
    """Worker entry point for parallel deck processing."""
    deck_info = payload["deck"]
    corpus_dir = Path(payload["corpus_dir"])
    output_dir = Path(payload["output_dir"])
    mode = payload.get("mode", "resvg")
    enable_visual = bool(payload.get("enable_visual", False))

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

        parse_result = parser.parse(svg_text)
        if not parse_result.success or parse_result.svg_root is None:
            raise ValueError(f"SVG parsing failed: {parse_result.error_message}")

        filter_strategy = mode if mode in ["legacy", "resvg"] else "resvg"
        services = parse_result.services
        if services is None:
            services = configure_services(filter_strategy=filter_strategy)
        elif services.filter_service is not None:
            services.filter_service.set_strategy(filter_strategy)

        from svg2ooxml.core.tracing.conversion import ConversionTracer
        tracer = ConversionTracer()

        import time
        start_time = time.time()
        scene = convert_parser_output(parse_result, services=services, tracer=tracer)
        metrics.conversion_time_ms = (time.time() - start_time) * 1000

        render_result = writer.render_scene_from_ir(scene, tracer=tracer)
        pptx_path = output_dir / f"{deck_name}_{mode}.pptx"
        builder.build_from_results([render_result], pptx_path)

        report = tracer.report()
        geom_totals = report.geometry_totals
        paint_totals = report.paint_totals

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

        if enable_visual and VISUAL_AVAILABLE:
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
    ):
        """Initialize corpus runner.

        Args:
            corpus_dir: Directory containing corpus SVG files and metadata
            output_dir: Directory for output PPTX files and reports
            mode: Rendering mode ("legacy" or "resvg")
            metadata_file: Path to metadata file (default: corpus_dir/corpus_metadata.json)
        """
        self.corpus_dir = corpus_dir
        self.output_dir = output_dir
        self.mode = mode
        self.metadata_file = metadata_file
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize SVG2OOXML pipeline
        self._parser = SVGParser(ParserConfig())
        self._writer = DrawingMLWriter()
        self._builder = PPTXPackageBuilder()
        
        # Initialize visual tools if available
        self._renderer = None
        self._differ = None
        if VISUAL_AVAILABLE:
            self._renderer = LibreOfficeRenderer()
            self._differ = VisualDiffer(threshold=0.90)
    
    def load_metadata(self) -> dict[str, Any]:
        """Load corpus metadata from JSON file."""
        metadata_path = self.metadata_file or (self.corpus_dir / "corpus_metadata.json")
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

        with open(metadata_path) as f:
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
            parse_result = self._parser.parse(svg_text)
            if not parse_result.success or parse_result.svg_root is None:
                raise ValueError(f"SVG parsing failed: {parse_result.error_message}")
            
            # Configure services with appropriate mode
            filter_strategy = self.mode if self.mode in ["legacy", "resvg"] else "resvg"
            services = parse_result.services
            if services is None:
                services = configure_services(filter_strategy=filter_strategy)
            elif services.filter_service is not None:
                services.filter_service.set_strategy(filter_strategy)
            
            # Convert to IR
            from svg2ooxml.core.tracing.conversion import ConversionTracer
            tracer = ConversionTracer()
            
            import time
            start_time = time.time()
            scene = convert_parser_output(parse_result, services=services, tracer=tracer)
            conversion_time_ms = (time.time() - start_time) * 1000
            metrics.conversion_time_ms = conversion_time_ms
            
            # Render to DrawingML
            render_result = self._writer.render_scene_from_ir(scene, tracer=tracer)
            
            # Build PPTX
            pptx_path = self.output_dir / f"{deck_name}_{self.mode}.pptx"
            self._builder.build_from_results([render_result], pptx_path)
            
            # Collect telemetry metrics from tracer
            report = tracer.report()
            geom_totals = report.geometry_totals
            paint_totals = report.paint_totals
            
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
            if self._renderer and self._renderer.available and self._differ:
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

            parse_result = self._parser.parse(svg_text)
            if not parse_result.success or parse_result.svg_root is None:
                raise ValueError(f"SVG parsing failed: {parse_result.error_message}")

            filter_strategy = self.mode if self.mode in ["legacy", "resvg"] else "resvg"
            services = parse_result.services
            if services is None:
                services = configure_services(filter_strategy=filter_strategy)
            elif services.filter_service is not None:
                services.filter_service.set_strategy(filter_strategy)

            from svg2ooxml.core.tracing.conversion import ConversionTracer
            tracer = ConversionTracer()

            import time
            start_time = time.time()
            scene = convert_parser_output(parse_result, services=services, tracer=tracer)
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
        targets = metadata.get("targets", {})
        
        planned_total = len(decks)
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
                            "enable_visual": bool(self._renderer and self._renderer.available),
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
        summary = "\n".join(summary_lines)
        
        report = CorpusReport(
            timestamp=datetime.utcnow().isoformat(),
            mode=self.mode,
            total_decks=total_decks,
            successful_decks=successful_decks,
            failed_decks=failed_decks,
            avg_native_rate=avg_native,
            avg_emf_rate=avg_emf,
            avg_raster_rate=avg_raster,
            avg_ssim_score=avg_ssim,
            decks=[asdict(r) for r in results],
            targets_met=targets_met,
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
        choices=["legacy", "resvg"],
        default="resvg",
        help="Rendering mode (default: resvg)",
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
    
    # Run corpus tests
    runner = CorpusRunner(
        corpus_dir=args.corpus_dir,
        output_dir=args.output_dir,
        mode=args.mode,
        metadata_file=args.metadata,
    )
    
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
    with open(args.report, "w") as f:
        json.dump(report_dict, f, indent=2)
    
    logger.info(f"\nReport saved to: {args.report}")
    
    # Exit with appropriate code
    all_targets_met = all(report.targets_met.values())
    sys.exit(0 if all_targets_met and report.failed_decks == 0 else 1)


if __name__ == "__main__":
    main()
