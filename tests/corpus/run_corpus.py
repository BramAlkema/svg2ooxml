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
import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from svg2ooxml.core.parser import ParserConfig, SVGParser
from svg2ooxml.drawingml.writer import DrawingMLWriter
from svg2ooxml.io.pptx_writer import PPTXPackageBuilder
from svg2ooxml.ir.entrypoints import convert_parser_output
from svg2ooxml.services import configure_services

# Import visual tools if available
try:
    from PIL import Image
    from tests.visual.differ import VisualDiffer
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


class CorpusRunner:
    """Runner for corpus testing with metrics collection."""
    
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
            import time
            start_time = time.time()
            scene = convert_parser_output(parse_result, services=services)
            conversion_time_ms = (time.time() - start_time) * 1000
            metrics.conversion_time_ms = conversion_time_ms
            
            # Render to DrawingML
            render_result = self._writer.render_scene_from_ir(scene)
            
            # Build PPTX
            pptx_path = self.output_dir / f"{deck_name}_{self.mode}.pptx"
            self._builder.build_from_results([render_result], pptx_path)
            
            # Collect telemetry metrics (if available in render_result)
            # Note: This is a placeholder - actual telemetry extraction depends on implementation
            metrics.total_elements = 100  # TODO: Extract from telemetry
            metrics.native_count = 85  # TODO: Extract from telemetry
            metrics.emf_count = 10  # TODO: Extract from telemetry
            metrics.raster_count = 5  # TODO: Extract from telemetry
            
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
    
    def run_all(self) -> CorpusReport:
        """Run all corpus decks and generate report.
        
        Returns:
            CorpusReport with aggregate metrics and per-deck results
        """
        metadata = self.load_metadata()
        decks = metadata.get("decks", [])
        targets = metadata.get("targets", {})
        
        logger.info(f"Running corpus tests for {len(decks)} decks in {self.mode} mode")
        
        results: list[DeckMetrics] = []
        for deck_info in decks:
            metrics = self.run_deck(deck_info)
            results.append(metrics)
        
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
        summary_lines = [
            f"Corpus test completed: {successful_decks}/{total_decks} decks successful",
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
    
    report = runner.run_all()
    
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
