#!/usr/bin/env python3
"""Test script for Google Slides export via svg2ooxml API.

This tests the end-to-end flow of creating a Google Slides presentation
from SVG content via the Cloud Run API.

Usage:
    python test_slides_api.py [SERVICE_URL]
"""

import json
import sys
import time
from typing import Any, Dict

import requests


DEFAULT_SERVICE_URL = "https://svg2ooxml-export-sghya3t5ya-ew.a.run.app"


def create_slides_export_job(base_url: str) -> str:
    """Create a test export job for Google Slides."""
    print("Creating Google Slides export job...")

    request_data = {
        "frames": [
            {
                "name": "Title Slide",
                "svg_content": (
                    '<svg width="1920" height="1080">'
                    '<rect fill="#8b5cf6" width="1920" height="1080"/>'
                    '<text x="960" y="450" text-anchor="middle" fill="white" '
                    'font-size="120" font-family="Arial" font-weight="bold">'
                    'Google Slides Test</text>'
                    '<text x="960" y="600" text-anchor="middle" fill="white" '
                    'font-size="60" font-family="Arial">'
                    'Created via svg2ooxml API</text>'
                    '</svg>'
                ),
                "width": 1920,
                "height": 1080
            },
            {
                "name": "Content Slide",
                "svg_content": (
                    '<svg width="1920" height="1080">'
                    '<rect fill="#06b6d4" width="1920" height="1080"/>'
                    '<text x="960" y="300" text-anchor="middle" fill="white" '
                    'font-size="96" font-family="Arial" font-weight="bold">'
                    'Features</text>'
                    '<text x="200" y="500" fill="white" font-size="48" font-family="Arial">'
                    '✓ SVG to Google Slides</text>'
                    '<text x="200" y="600" fill="white" font-size="48" font-family="Arial">'
                    '✓ Cloud Run Deployment</text>'
                    '<text x="200" y="700" fill="white" font-size="48" font-family="Arial">'
                    '✓ Async Processing</text>'
                    '</svg>'
                ),
                "width": 1920,
                "height": 1080
            }
        ],
        "figma_file_id": "test-slides-export",
        "figma_file_name": "Google Slides API Test",
        "output_format": "slides"  # This is the key difference!
    }

    response = requests.post(
        f"{base_url}/api/v1/export",
        json=request_data,
        headers={"Content-Type": "application/json"}
    )
    response.raise_for_status()

    data = response.json()
    job_id = data["job_id"]

    print(f"✅ Slides export job created")
    print(f"   Job ID: {job_id}")
    print(f"   Status: {data['status']}")
    print(f"   Message: {data['message']}")
    print()

    return job_id


def poll_job_status(base_url: str, job_id: str, max_wait: int = 180) -> Dict[str, Any]:
    """Poll job status until complete or timeout."""
    print(f"Polling job status (max {max_wait}s)...")

    start_time = time.time()
    while time.time() - start_time < max_wait:
        response = requests.get(f"{base_url}/api/v1/export/{job_id}")
        response.raise_for_status()

        data = response.json()
        status = data["status"]
        progress = data.get("progress", 0)

        print(f"   Status: {status} ({progress:.1f}%)", end="\r")

        if status in ["completed", "failed"]:
            print()
            return data

        time.sleep(3)

    print()
    raise TimeoutError(f"Job did not complete within {max_wait} seconds")


def print_slides_result(data: Dict[str, Any]) -> None:
    """Print the final job result for Slides export."""
    status = data["status"]

    if status == "completed":
        print("✅ Google Slides export completed successfully!")
        print()

        slides_url = data.get("slides_url")
        pptx_url = data.get("pptx_url")
        thumbnails = data.get("thumbnail_urls", [])

        if slides_url:
            print(f"   🎉 Google Slides URL:")
            print(f"   {slides_url}")
            print()
            print(f"   View/Edit: {slides_url.replace('/pub', '/edit')}")
            print(f"   Present: {slides_url.replace('/pub', '/present')}")
        else:
            print("   ⚠️  No Slides URL returned")

        if pptx_url:
            print()
            print(f"   PPTX Backup: {pptx_url}")

        if thumbnails:
            print()
            print(f"   Thumbnails ({len(thumbnails)}):")
            for i, thumb in enumerate(thumbnails, 1):
                print(f"   [{i}] {thumb}")

        if data.get("conversion_summary"):
            print()
            print("   Conversion summary:")
            summary = data['conversion_summary']
            print(f"   - Slides: {summary.get('slide_count', 0)}")

        if data.get("error"):
            print()
            print(f"   ⚠️  Warning: {data['error']}")

    elif status == "failed":
        print("❌ Google Slides export failed")
        print(f"   Error: {data.get('error', 'Unknown error')}")

    else:
        print(f"⚠️  Unexpected status: {status}")

    print()


def main() -> None:
    """Run the Google Slides API test."""
    service_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SERVICE_URL

    print("=" * 70)
    print("Google Slides Export Test")
    print(f"Service URL: {service_url}")
    print("=" * 70)
    print()
    print("⚠️  Note: This requires the Cloud Run service account to have")
    print("   Google Drive/Slides API permissions configured.")
    print()

    try:
        # Create slides export job
        job_id = create_slides_export_job(service_url)

        # Poll until complete
        result = poll_job_status(service_url, job_id, max_wait=180)

        # Print result
        print_slides_result(result)

        print("=" * 70)
        if result["status"] == "completed" and result.get("slides_url"):
            print("✅ Google Slides integration working!")
        else:
            print("⚠️  Export completed but check for errors above")
        print("=" * 70)

    except Exception as e:
        print()
        print("=" * 70)
        print(f"❌ Test failed: {e}")
        print("=" * 70)
        print()
        print("Common issues:")
        print("1. Service account needs Drive/Slides API access")
        print("2. OAuth scopes not configured")
        print("3. google-api-python-client not installed")
        sys.exit(1)


if __name__ == "__main__":
    main()
