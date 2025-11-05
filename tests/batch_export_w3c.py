#!/usr/bin/env python3
"""
Batch export W3C SVG test files to Google Slides via the Cloud Run API.

This script:
1. Reads all W3C SVG test files from tests/svg/
2. Submits each as an export job to the API (Slides format)
3. Monitors job progress and collects results
4. Generates a comprehensive test report

Prerequisites:
- Share your Google Drive folder with: svg2ooxml-runner@powerful-layout-467812-p1.iam.gserviceaccount.com
- Set FIREBASE_TOKEN environment variable
- Set DRIVE_FOLDER_ID environment variable (from the Drive URL)

Usage:
    export FIREBASE_TOKEN="$(gcloud auth print-identity-token)"
    export DRIVE_FOLDER_ID="1LsnrNyo8nnBCG0gWC8F8T2T2JQzJpP5a"  # From Drive URL
    python tests/batch_export_w3c.py [--limit N] [--batch-size N] [--delay SECONDS]
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import requests

# Configuration
BASE_URL = os.environ.get("SVG2OOXML_BASE_URL", "https://svg2ooxml-export-sghya3t5ya-ew.a.run.app")
TIMEOUT_SECONDS = 300  # 5 minutes per job
POLL_INTERVAL = 5  # Check status every 5 seconds
SVG_DIR = Path(__file__).parent.parent / "tests" / "svg"


@dataclass
class JobResult:
    """Result of a single export job."""
    svg_file: str
    job_id: Optional[str] = None
    status: str = "pending"
    message: str = ""
    slides_url: Optional[str] = None
    slides_presentation_id: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None


@dataclass
class BatchReport:
    """Overall batch export report."""
    started_at: str
    completed_at: Optional[str] = None
    total_files: int = 0
    submitted: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    results: List[Dict] = None

    def __post_init__(self):
        if self.results is None:
            self.results = []


def get_auth_headers() -> Dict[str, str]:
    """Get authentication headers from environment."""
    token = os.environ.get("FIREBASE_TOKEN")
    if not token:
        print("❌ FIREBASE_TOKEN not set. Run:")
        print('  export FIREBASE_TOKEN="$(gcloud auth print-identity-token)"')
        sys.exit(1)

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "svg2ooxml-w3c-batch-export"
    }


def submit_export_job(svg_path: Path, headers: Dict[str, str], parent_folder_id: Optional[str] = None) -> JobResult:
    """Submit a single SVG file for export."""
    result = JobResult(svg_file=svg_path.name)

    try:
        # Read SVG content
        svg_content = svg_path.read_text(encoding="utf-8")

        # Prepare payload
        payload = {
            "frames": [
                {
                    "name": svg_path.stem,
                    "svg_content": svg_content,
                    "width": 800,
                    "height": 600,
                }
            ],
            "figma_file_id": f"w3c-{svg_path.stem}",
            "figma_file_name": f"W3C Test: {svg_path.stem}",
            "output_format": "slides",
            "fonts": [],
        }

        # Add parent folder if specified
        if parent_folder_id:
            payload["parent_folder_id"] = parent_folder_id

        # Submit job
        response = requests.post(
            f"{BASE_URL}/api/v1/export",
            json=payload,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        result.job_id = data["job_id"]
        result.status = data["status"]
        result.message = data.get("message", "")
        result.created_at = datetime.now().isoformat()

        print(f"  ✅ Submitted: {svg_path.name} → Job {result.job_id}")

    except Exception as e:
        result.status = "failed"
        result.error = str(e)
        print(f"  ❌ Failed to submit {svg_path.name}: {e}")

    return result


def poll_job_status(job_id: str, headers: Dict[str, str], timeout: int = TIMEOUT_SECONDS) -> Dict:
    """Poll job status until completion or timeout."""
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            response = requests.get(
                f"{BASE_URL}/api/v1/export/{job_id}",
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            status_data = response.json()

            if status_data["status"] in {"completed", "failed", "cancelled"}:
                return status_data

            time.sleep(POLL_INTERVAL)

        except Exception as e:
            print(f"    ⚠️  Error polling job {job_id}: {e}")
            time.sleep(POLL_INTERVAL)

    # Timeout
    return {
        "job_id": job_id,
        "status": "timeout",
        "error": f"Job did not complete within {timeout} seconds"
    }


def process_batch(
    svg_files: List[Path],
    headers: Dict[str, str],
    batch_size: int = 5,
    delay_between_batches: float = 10.0,
    parent_folder_id: Optional[str] = None
) -> BatchReport:
    """Process SVG files in batches."""
    report = BatchReport(
        started_at=datetime.now().isoformat(),
        total_files=len(svg_files)
    )

    print(f"\n🚀 Starting batch export of {len(svg_files)} files")
    print(f"   Batch size: {batch_size}, Delay: {delay_between_batches}s")
    if parent_folder_id:
        print(f"   Target folder: {parent_folder_id}")
    print()

    # Process in batches
    for i in range(0, len(svg_files), batch_size):
        batch = svg_files[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(svg_files) + batch_size - 1) // batch_size

        print(f"📦 Batch {batch_num}/{total_batches} ({len(batch)} files)")

        # Submit batch
        batch_results = []
        for svg_path in batch:
            result = submit_export_job(svg_path, headers, parent_folder_id)
            batch_results.append(result)
            report.submitted += 1

        # Wait for batch completion
        print(f"   ⏳ Waiting for batch to complete...")
        for result in batch_results:
            if result.job_id:
                status_data = poll_job_status(result.job_id, headers)

                # Update result
                result.status = status_data["status"]
                result.message = status_data.get("message", "")
                result.slides_url = status_data.get("slides_url")
                result.slides_presentation_id = status_data.get("slides_presentation_id")
                result.error = status_data.get("error")
                result.completed_at = datetime.now().isoformat()

                if result.created_at:
                    created = datetime.fromisoformat(result.created_at)
                    completed = datetime.fromisoformat(result.completed_at)
                    result.duration_seconds = (completed - created).total_seconds()

                if result.status == "completed":
                    report.completed += 1
                    print(f"   ✅ {result.svg_file}: {result.slides_url}")
                else:
                    report.failed += 1
                    print(f"   ❌ {result.svg_file}: {result.status} - {result.error}")
            else:
                report.failed += 1

            report.results.append(asdict(result))

        # Delay between batches
        if i + batch_size < len(svg_files):
            print(f"   💤 Waiting {delay_between_batches}s before next batch...\n")
            time.sleep(delay_between_batches)

    report.completed_at = datetime.now().isoformat()
    return report


def save_report(report: BatchReport, output_path: Path):
    """Save batch report to JSON file."""
    with open(output_path, "w") as f:
        json.dump(asdict(report), f, indent=2)
    print(f"\n📄 Report saved to: {output_path}")


def print_summary(report: BatchReport):
    """Print batch export summary."""
    print("\n" + "=" * 60)
    print("📊 BATCH EXPORT SUMMARY")
    print("=" * 60)
    print(f"Total files:     {report.total_files}")
    print(f"Submitted:       {report.submitted}")
    print(f"✅ Completed:    {report.completed}")
    print(f"❌ Failed:       {report.failed}")
    print(f"⏭️  Skipped:      {report.skipped}")
    print(f"Success rate:    {report.completed / report.submitted * 100:.1f}%" if report.submitted > 0 else "N/A")
    print(f"Started:         {report.started_at}")
    print(f"Completed:       {report.completed_at}")

    if report.started_at and report.completed_at:
        started = datetime.fromisoformat(report.started_at)
        completed = datetime.fromisoformat(report.completed_at)
        duration = (completed - started).total_seconds()
        print(f"Duration:        {duration:.1f}s ({duration / 60:.1f} minutes)")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Batch export W3C SVG test files to Google Slides"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of files to process (for testing)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Number of files to process in parallel (default: 5)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=10.0,
        help="Delay in seconds between batches (default: 10)"
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.svg",
        help="File pattern to match (default: *.svg)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("w3c_batch_report.json"),
        help="Output report file (default: w3c_batch_report.json)"
    )

    args = parser.parse_args()

    # Check prerequisites
    if not os.environ.get("FIREBASE_TOKEN"):
        print("❌ FIREBASE_TOKEN not set. Run:")
        print('  export FIREBASE_TOKEN="$(gcloud auth print-identity-token)"')
        sys.exit(1)

    # Get Drive folder ID (optional)
    parent_folder_id = os.environ.get("DRIVE_FOLDER_ID")
    if parent_folder_id:
        print(f"📁 Using Drive folder: {parent_folder_id}")
    else:
        print("ℹ️  No DRIVE_FOLDER_ID set - files will be created in user's root Drive")

    # Find SVG files
    svg_files = sorted(SVG_DIR.glob(args.pattern))

    if not svg_files:
        print(f"❌ No SVG files found in {SVG_DIR}")
        sys.exit(1)

    print(f"📁 Found {len(svg_files)} SVG files in {SVG_DIR}")

    # Apply limit if specified
    if args.limit:
        svg_files = svg_files[:args.limit]
        print(f"🔢 Limited to first {args.limit} files")

    # Get auth headers
    headers = get_auth_headers()

    # Process batch
    report = process_batch(
        svg_files,
        headers,
        batch_size=args.batch_size,
        delay_between_batches=args.delay,
        parent_folder_id=parent_folder_id
    )

    # Save report
    save_report(report, args.output)

    # Print summary
    print_summary(report)

    # Exit with appropriate code
    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
