import os
import subprocess
import time
from urllib.parse import urlparse

import pytest
import requests
from requests import exceptions as request_exceptions

try:  # pragma: no cover - optional dependency
    import google.auth
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token
except ImportError:  # pragma: no cover
    google = None

BASE_URL = os.environ.get("SVG2OOXML_BASE_URL", "https://svg2ooxml-export-sghya3t5ya-ew.a.run.app")
SMOKE_STRICT = os.environ.get("SVG2OOXML_SMOKE_STRICT", "false").lower() == "true"
TIMEOUT_SECONDS = 60
POLL_INTERVAL = 2


def _validate_base_url() -> None:
    parsed = urlparse(BASE_URL)
    if not parsed.scheme or not parsed.netloc:
        pytest.skip(f"Invalid SVG2OOXML_BASE_URL: {BASE_URL!r}")


def _request(method: str, path: str, *, json: dict | None = None, headers: dict | None = None):
    _validate_base_url()
    merged_headers = {"User-Agent": "svg2ooxml-smoke-test"}
    merged_headers.update(headers or {})
    try:
        resp = requests.request(
            method,
            f"{BASE_URL}{path}",
            json=json,
            headers=merged_headers,
            timeout=30,
        )
        resp.raise_for_status()
    except request_exceptions.HTTPError:
        if not SMOKE_STRICT and resp.status_code == 404:
            pytest.skip(f"Smoke endpoint returned 404: {resp.url}")
        raise
    except (request_exceptions.ConnectionError, request_exceptions.Timeout) as exc:
        if SMOKE_STRICT:
            raise
        pytest.skip(f"Smoke endpoint unreachable: {exc}")
    return resp


def _post(path: str, json: dict, headers: dict | None = None):
    return _request("POST", path, json=json, headers=headers)


def _get(path: str, headers: dict | None = None):
    return _request("GET", path, headers=headers)


def _resolve_bearer_token() -> str | None:
    firebase_token = os.environ.get("FIREBASE_TOKEN")
    if firebase_token:
        return firebase_token

    audience = os.environ.get("SVG2OOXML_AUDIENCE", BASE_URL)

    if google is None:
        return None

    try:
        credentials, _ = google.auth.default()  # type: ignore[attr-defined]
        request = Request()
        token = id_token.fetch_id_token(request, audience)  # type: ignore[attr-defined]
        if token:
            return token
    except Exception:
        pass

    gcloud_bin = os.environ.get("GCLOUD_BIN", "gcloud")
    try:
        result = subprocess.run(
            [
                gcloud_bin,
                "auth",
                "print-identity-token",
                f"--audiences={audience}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        token = result.stdout.strip()
        return token or None
    except Exception:
        return None


@pytest.mark.smoke
@pytest.mark.requires_network
class TestExportEndpoints:
    def test_health_endpoint(self):
        resp = _get("/health")
        payload = resp.json()
        assert payload.get("status") == "healthy"

    @pytest.mark.parametrize("output_format", ["pptx", "slides"])
    def test_export_job_lifecycle(self, output_format):
        headers = {}
        token = _resolve_bearer_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif os.environ.get("SVG2OOXML_ANON_TEST", "false").lower() != "true":
            pytest.skip(
                "Authentication token missing. Provide FIREBASE_TOKEN, set SVG2OOXML_AUDIENCE and"
                " GOOGLE credentials for Cloud Run ID token, or export SVG2OOXML_ANON_TEST=true."
            )

        payload = {
            "frames": [
                {
                    "name": "SmokeCard",
                    "svg_content": "<svg xmlns='http://www.w3.org/2000/svg' width='200' height='120'><rect width='200' height='120' fill='#4285F4'/><text x='100' y='65' font-size='24' text-anchor='middle' fill='white'>Smoke</text></svg>",
                    "width": 200,
                    "height": 120,
                }
            ],
            "figma_file_id": "smoke-file",
            "figma_file_name": "Smoke Deck",
            "output_format": output_format,
            "fonts": ["Inter"],
        }

        response = _post("/api/v1/export", payload, headers=headers).json()
        assert response["status"] == "queued"
        job_id = response["job_id"]

        # Poll job status until it reaches a terminal state or timeout
        deadline = time.time() + TIMEOUT_SECONDS
        last_status = None
        while time.time() < deadline:
            status = _get(f"/api/v1/export/{job_id}", headers=headers if token else None).json()
            last_status = status
            if status["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(POLL_INTERVAL)

        assert last_status is not None, "No status received for export job"
        assert last_status["status"] in {"completed", "queued", "processing"}, last_status
        # Ensure metadata echoes the request shape
        assert last_status["job_id"] == job_id
        assert "created_at" in last_status
        assert "message" in last_status
