#!/usr/bin/env python3
"""Test script for svg2ooxml Cloud Run API.

Usage:
    python test_api.py [SERVICE_URL]

If SERVICE_URL is not provided, uses the default Cloud Run URL.
"""

import json
import sys
import time
from typing import Any, Dict, Optional

import requests


DEFAULT_SERVICE_URL = "https://svg2ooxml-export-sghya3t5ya-ew.a.run.app"


def test_health_check(base_url: str) -> None:
    """Test the health check endpoint."""
    print("Testing health check...")
    response = requests.get(f"{base_url}/health")
    response.raise_for_status()
    data = response.json()
    print(f"✅ Health check passed: {data}")
    print()


def create_export_job(base_url: str) -> str:
    """Create a test export job and return the job_id."""
    print("Creating export job...")

    # Test data with 2 slides
    request_data = {
        "frames": [
            {
                "name": "Title Slide",
                "svg_content": (
                    '<svg width="1920" height="1080">'
                    '<rect fill="#3b82f6" width="1920" height="1080"/>'
                    '<text x="960" y="540" text-anchor="middle" fill="white" '
                    'font-size="96" font-family="Arial">svg2ooxml API Test</text>'
                    '</svg>'
                ),
                "width": 1920,
                "height": 1080
            },
            {
                "name": "Content Slide",
                "svg_content": (
                    '<svg width="1920" height="1080">'
                    '<rect fill="#10b981" width="1920" height="1080"/>'
                    '<text x="960" y="540" text-anchor="middle" fill="white" '
                    'font-size="72" font-family="Arial">Deployed on Cloud Run</text>'
                    '</svg>'
                ),
                "width": 1920,
                "height": 1080
            }
        ],
        "figma_file_id": "test-api-demo",
        "figma_file_name": "API Test Presentation",
        "output_format": "pptx"
    }

    response = requests.post(
        f"{base_url}/api/v1/export",
        json=request_data,
        headers={"Content-Type": "application/json"}
    )
    response.raise_for_status()

    data = response.json()
    job_id = data["job_id"]

    print(f"✅ Export job created")
    print(f"   Job ID: {job_id}")
    print(f"   Status: {data['status']}")
    print(f"   Message: {data['message']}")
    print()

    return job_id


def poll_job_status(base_url: str, job_id: str, max_wait: int = 120) -> Dict[str, Any]:
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
            print()  # New line after final status
            return data

        time.sleep(2)

    print()
    raise TimeoutError(f"Job did not complete within {max_wait} seconds")


def print_job_result(data: Dict[str, Any]) -> None:
    """Print the final job result."""
    status = data["status"]

    if status == "completed":
        print("✅ Export completed successfully!")
        print()
        print(f"   PPTX URL: {data.get('pptx_url', 'N/A')}")
        print(f"   Slides URL: {data.get('slides_url', 'N/A')}")

        if data.get("conversion_summary"):
            print()
            print("   Conversion summary:")
            print(f"   {json.dumps(data['conversion_summary'], indent=2)}")

        if data.get("font_summary"):
            print()
            print("   Font summary:")
            print(f"   {json.dumps(data['font_summary'], indent=2)}")

    elif status == "failed":
        print("❌ Export failed")
        print(f"   Error: {data.get('error', 'Unknown error')}")

    else:
        print(f"⚠️  Unexpected status: {status}")

    print()


def delete_job(base_url: str, job_id: str) -> None:
    """Delete the job and clean up resources."""
    print("Cleaning up job...")
    response = requests.delete(f"{base_url}/api/v1/export/{job_id}")
    response.raise_for_status()
    print("✅ Job deleted successfully")
    print()


def main() -> None:
    """Run the API test suite."""
    # Get service URL from args or use default
    service_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SERVICE_URL

    print("=" * 60)
    print(f"svg2ooxml API Test")
    print(f"Service URL: {service_url}")
    print("=" * 60)
    print()

    try:
        # Test health check
        test_health_check(service_url)

        # Create export job
        job_id = create_export_job(service_url)

        # Poll until complete
        result = poll_job_status(service_url, job_id)

        # Print result
        print_job_result(result)

        # Download URL if available
        if result.get("pptx_url"):
            print("To download the PPTX file:")
            print(f"  curl -o output.pptx '{result['pptx_url']}'")
            print()

        # Clean up
        delete_job(service_url, job_id)

        print("=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)

    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ Test failed: {e}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
