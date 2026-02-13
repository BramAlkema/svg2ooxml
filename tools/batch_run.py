#!/usr/bin/env python3
"""Run parallel batch conversion (split → stitch → audit)."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

from svg2ooxml.core.parser.batch.coordinator import convert_svg_batch_parallel
from svg2ooxml.core.parser.batch.monitoring import collect_bundle_metrics, queue_metrics


def _load_inputs(
    *,
    inputs: list[Path],
    input_dir: Path | None,
    glob: str,
    metadata: Path | None,
    corpus_dir: Path | None,
    sample_size: int | None,
    sample_seed: int | None,
) -> list[dict[str, str]]:
    files: list[Path] = []
    if metadata:
        if corpus_dir is None:
            raise ValueError("--metadata requires --corpus-dir")
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        decks = payload.get("decks", [])
        if sample_size:
            ordered = sorted(decks, key=lambda d: d.get("deck_name", ""))
            rng = random.Random(sample_seed or 0)
            rng.shuffle(ordered)
            decks = ordered[: min(sample_size, len(ordered))]
        for deck in decks:
            svg_file = deck.get("svg_file")
            if not svg_file:
                continue
            files.append(corpus_dir / svg_file)
    else:
        files.extend(inputs)
        if input_dir:
            files.extend(sorted(input_dir.glob(glob)))

    if not files:
        raise ValueError("No SVG inputs provided.")

    file_list: list[dict[str, str]] = []
    for path in files:
        resolved = path.expanduser().resolve()
        svg_text = resolved.read_text(encoding="utf-8")
        file_list.append(
            {
                "filename": resolved.name,
                "content": svg_text,
                "source_path": str(resolved),
            }
        )
    return file_list


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path, help="SVG files to convert")
    parser.add_argument("--input-dir", type=Path, help="Directory of SVGs")
    parser.add_argument("--glob", default="*.svg", help="Glob pattern for input-dir (default: *.svg)")
    parser.add_argument("--metadata", type=Path, help="W3C metadata JSON")
    parser.add_argument("--corpus-dir", type=Path, help="Corpus directory for metadata inputs")
    parser.add_argument("--sample-size", type=int, default=None, help="Sample size for metadata")
    parser.add_argument("--sample-seed", type=int, default=None, help="Sample seed for metadata")
    parser.add_argument("--output", type=Path, required=True, help="Output PPTX path")
    parser.add_argument("--bundle-dir", type=Path, default=None, help="Bundle root directory")
    parser.add_argument("--job-id", type=str, default=None, help="Optional job id")
    parser.add_argument("--openxml-validator", type=str, default=None, help="OpenXML validator path")
    parser.add_argument("--openxml-policy", type=str, default="strict", help="OpenXML policy")
    parser.add_argument("--openxml-required", action="store_true", help="Fail if audit unavailable/fails")
    parser.add_argument("--timeout", type=float, default=None, help="Timeout for slide tasks")
    parser.add_argument("--bail", action="store_true", help="Stop on first failure")
    parser.add_argument("--inline", action="store_true", help="Force inline execution (no Huey)")
    parser.add_argument("--report", type=Path, help="Write JSON report")
    parser.add_argument("--queue-metrics", action="store_true", help="Print queue metrics")
    args = parser.parse_args(argv)

    try:
        file_list = _load_inputs(
            inputs=args.inputs,
            input_dir=args.input_dir,
            glob=args.glob,
            metadata=args.metadata,
            corpus_dir=args.corpus_dir,
            sample_size=args.sample_size,
            sample_seed=args.sample_seed,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.queue_metrics:
        print("Queue metrics (before):", queue_metrics())

    result = convert_svg_batch_parallel(
        file_list,
        args.output,
        conversion_options={"bundle_dir": str(args.bundle_dir)} if args.bundle_dir else None,
        job_id=args.job_id,
        wait=True,
        timeout_s=args.timeout,
        bail=args.bail,
        force_inline=args.inline,
        bundle_dir=args.bundle_dir,
        openxml_validator=args.openxml_validator,
        openxml_policy=args.openxml_policy,
        openxml_required=args.openxml_required,
    )

    if args.queue_metrics:
        print("Queue metrics (after):", queue_metrics())

    bundle_metrics: list[dict[str, Any]] = []
    job_id = result.get("job_id")
    if job_id and args.bundle_dir:
        bundle_metrics = collect_bundle_metrics(job_id, base_dir=args.bundle_dir)

    report = {
        "result": result,
        "bundle_metrics": bundle_metrics,
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if result.get("success"):
        print(f"✓ Wrote {result.get('output_path')}")
        if result.get("openxml_valid") is False:
            print("OpenXML audit failed")
            return 1
        return 0
    print("Conversion failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
