#!/usr/bin/env python3
"""Script to add W3C SVG test suite files to corpus metadata.

This script scans the tests/svg/ directory for W3C SVG test files (excluding
animation tests) and generates a corpus_metadata.json file for use with the
corpus test runner.

Usage:
    python tests/corpus/add_w3c_corpus.py
    python tests/corpus/add_w3c_corpus.py --limit 20
    python tests/corpus/add_w3c_corpus.py --category pservers-grad
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def extract_test_description(svg_path: Path) -> dict[str, Any]:
    """Extract metadata from W3C SVG test file.

    Args:
        svg_path: Path to SVG file

    Returns:
        Dict with test metadata (description, features, status)
    """
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()

        # Find SVGTestCase element
        ns = {"d": "http://www.w3.org/2000/02/svg/testsuite/description/"}
        test_case = root.find(".//d:SVGTestCase", ns)

        if test_case is None:
            return {}

        # Extract attributes
        status = test_case.get("status", "unknown")
        reviewer = test_case.get("reviewer", "unknown")

        # Extract description
        desc_elem = test_case.find(".//d:testDescription", ns)
        description = ""
        if desc_elem is not None:
            # Get text content, stripping whitespace
            desc_text = ET.tostring(desc_elem, encoding="unicode", method="text")
            description = " ".join(desc_text.split())

        return {
            "status": status,
            "reviewer": reviewer,
            "description": description[:200] + "..." if len(description) > 200 else description,
        }
    except Exception as e:
        print(f"Warning: Failed to parse {svg_path.name}: {e}")
        return {}


def categorize_test(filename: str) -> dict[str, Any]:
    """Categorize test based on filename.

    Args:
        filename: Test filename (e.g., "pservers-grad-17-b.svg")

    Returns:
        Dict with category, features, expected rates, complexity
    """
    # Extract category from filename (e.g., "pservers-grad")
    match = re.match(r"([a-z-]+)-", filename)
    category = match.group(1) if match else "unknown"

    # Map categories to features and expected metrics
    category_info = {
        "pservers-grad": {
            "features": ["linear_gradients", "radial_gradients", "gradient_transforms"],
            "expected_native_rate": 0.80,
            "expected_emf_rate": 0.15,
            "expected_raster_rate": 0.05,
            "complexity": "medium",
        },
        "pservers-pattern": {
            "features": ["patterns", "pattern_transforms"],
            "expected_native_rate": 0.70,
            "expected_emf_rate": 0.25,
            "expected_raster_rate": 0.05,
            "complexity": "high",
        },
        "shapes": {
            "features": ["basic_shapes", "stroke", "fill"],
            "expected_native_rate": 0.95,
            "expected_emf_rate": 0.05,
            "expected_raster_rate": 0.00,
            "complexity": "low",
        },
        "painting-fill": {
            "features": ["fill", "fill_rule"],
            "expected_native_rate": 0.95,
            "expected_emf_rate": 0.05,
            "expected_raster_rate": 0.00,
            "complexity": "low",
        },
        "painting-stroke": {
            "features": ["stroke", "stroke_dasharray", "stroke_linecap"],
            "expected_native_rate": 0.90,
            "expected_emf_rate": 0.10,
            "expected_raster_rate": 0.00,
            "complexity": "low",
        },
        "painting-marker": {
            "features": ["markers", "stroke"],
            "expected_native_rate": 0.60,
            "expected_emf_rate": 0.35,
            "expected_raster_rate": 0.05,
            "complexity": "high",
        },
        "paths-data": {
            "features": ["complex_paths", "bezier_curves"],
            "expected_native_rate": 0.90,
            "expected_emf_rate": 0.10,
            "expected_raster_rate": 0.00,
            "complexity": "medium",
        },
        "masking": {
            "features": ["masks", "clip_paths"],
            "expected_native_rate": 0.75,
            "expected_emf_rate": 0.20,
            "expected_raster_rate": 0.05,
            "complexity": "high",
        },
        "coords-trans": {
            "features": ["transforms", "coordinate_systems"],
            "expected_native_rate": 0.85,
            "expected_emf_rate": 0.15,
            "expected_raster_rate": 0.00,
            "complexity": "medium",
        },
        "text": {
            "features": ["text", "fonts"],
            "expected_native_rate": 0.80,
            "expected_emf_rate": 0.15,
            "expected_raster_rate": 0.05,
            "complexity": "medium",
        },
        "filters": {
            "features": ["filters", "blend_modes"],
            "expected_native_rate": 0.50,
            "expected_emf_rate": 0.40,
            "expected_raster_rate": 0.10,
            "complexity": "high",
        },
        "struct-image": {
            "features": ["embedded_images"],
            "expected_native_rate": 0.85,
            "expected_emf_rate": 0.10,
            "expected_raster_rate": 0.05,
            "complexity": "medium",
        },
    }

    # Find matching category
    for cat_prefix, info in category_info.items():
        if category.startswith(cat_prefix):
            return info

    # Default for unknown categories
    return {
        "features": ["unknown"],
        "expected_native_rate": 0.75,
        "expected_emf_rate": 0.20,
        "expected_raster_rate": 0.05,
        "complexity": "medium",
    }


def scan_w3c_tests(
    tests_dir: Path,
    category_filter: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Scan tests/svg/ directory for W3C test files.

    Args:
        tests_dir: Path to tests/svg directory
        category_filter: Optional category filter (e.g., "pservers-grad")
        limit: Optional limit on number of tests to include

    Returns:
        List of deck metadata dictionaries
    """
    svg_files = sorted(tests_dir.glob("*.svg"))

    # Filter out animation tests
    svg_files = [f for f in svg_files if "animate" not in f.name.lower()]

    # Apply category filter if specified
    if category_filter:
        svg_files = [f for f in svg_files if f.name.startswith(category_filter)]

    # Apply limit if specified
    if limit:
        svg_files = svg_files[:limit]

    print(f"Found {len(svg_files)} W3C test files")

    decks = []
    for svg_file in svg_files:
        # Extract metadata from file
        test_meta = extract_test_description(svg_file)
        category_info = categorize_test(svg_file.name)

        # Create deck entry
        # Use relative path from corpus/w3c/ back to tests/svg/
        svg_file_path = f"../../svg/{svg_file.name}"

        deck = {
            "deck_name": svg_file.stem,
            "source": "W3C SVG Test Suite",
            "svg_file": svg_file_path,
            "description": test_meta.get("description", f"W3C test: {svg_file.stem}"),
            "expected_native_rate": category_info["expected_native_rate"],
            "expected_emf_rate": category_info["expected_emf_rate"],
            "expected_raster_rate": category_info["expected_raster_rate"],
            "features": category_info["features"],
            "complexity": category_info["complexity"],
            "created_date": "2009",  # W3C SVG 1.1 2nd Edition
            "license": "W3C Test Suite License",
            "notes": f"Status: {test_meta.get('status', 'unknown')}",
        }

        decks.append(deck)

    return decks


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Add W3C SVG test suite files to corpus metadata"
    )
    parser.add_argument(
        "--tests-dir",
        type=Path,
        default=Path(__file__).parents[1] / "svg",
        help="Path to tests/svg directory (default: tests/svg)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "w3c_corpus_metadata.json",
        help="Output metadata file (default: tests/corpus/w3c_corpus_metadata.json)",
    )
    parser.add_argument(
        "--category",
        type=str,
        help="Filter by category prefix (e.g., 'pservers-grad', 'shapes')",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of tests to include",
    )

    args = parser.parse_args()

    if not args.tests_dir.exists():
        print(f"Error: Directory not found: {args.tests_dir}")
        return 1

    # Scan W3C tests
    decks = scan_w3c_tests(args.tests_dir, args.category, args.limit)

    # Create metadata structure
    metadata = {
        "$schema": "https://json-schema.org/draft-07/schema#",
        "title": "SVG2OOXML W3C Corpus Metadata",
        "description": "W3C SVG Test Suite corpus for svg2ooxml testing",
        "version": "1.0.0",
        "decks": decks,
        "targets": {
            "native_rate": 0.80,
            "emf_rate_max": 0.15,
            "raster_rate_max": 0.05,
            "visual_fidelity_min": 0.90,
        },
        "notes": [
            "W3C SVG Test Suite files from tests/svg/",
            "Animation tests excluded (animate-* files)",
            "Expected rates are estimates based on feature complexity",
            "Actual rates will vary based on implementation support",
        ],
    }

    # Write metadata file
    with open(args.output, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nGenerated corpus metadata with {len(decks)} decks")
    print(f"Output: {args.output}")

    # Print summary by category
    categories = {}
    for deck in decks:
        cat = deck["deck_name"].split("-")[0]
        categories[cat] = categories.get(cat, 0) + 1

    print("\nTests by category:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1])[:10]:
        print(f"  {cat}: {count}")

    return 0


if __name__ == "__main__":
    exit(main())
