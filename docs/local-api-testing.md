## Local Backend Testing (Slides Publishing)

Run the FastAPI service on your laptop against the real Firestore/Drive stack so
you can iterate on Slides uploads without redeploying to Cloud Run.

### Google Slides upload (ADC + desktop OAuth)

Service accounts usually have 0 Drive quota, so use a user OAuth client for
Slides uploads. The quickest flow is Application Default Credentials (ADC) with
the desktop OAuth client JSON.

1. Create a **Desktop app** OAuth client in the GCP project.
2. Download the JSON and place it in the repo root (or update the script path).
3. Run the helper script to avoid line-wrap scope errors:

```bash
bash gcloud_adc_remote_bootstrap.sh
```

4. Verify credentials were saved:

```bash
gcloud auth application-default print-access-token | head -c 20
```

If you see `invalid_scope` errors, it is usually caused by line breaks in the
scope list. Re-run the script above (it uses a single-line `--scopes` value).

### 1. Prerequisites

- `gcloud` CLI authenticated against `powerful-layout-467812-p1`
- Secret Manager access to `firebase-service-account`, `token-encryption-key`,
  `firebase-web-client-id`, and `firebase-web-client-secret`
- Python virtualenv bootstrapped via `./tools/bootstrap_venv.sh`

### 2. Bootstrap secrets + env vars

Run the helper script once (or whenever you need to refresh secrets):

```bash
# Python CLI (recommended)
python tools/local_api.py setup

# Or the legacy bash script
bash tools/local_api.sh setup
```

This pulls the four required Secret Manager entries into `secrets/local/`. The
Python version manages these automatically without requiring a `.env.local`
file.

### 3. Start the API locally

```bash
# Python CLI (recommended)
python tools/local_api.py run

# Or the legacy bash script
bash tools/local_api.sh run
```

The server will connect to real Firestore/Storage using the service account and
use the same encryption key, so existing `google_oauth` tokens continue to work.

**Port override**: Set `SVG2OOXML_LOCAL_PORT` to use a different port:
```bash
SVG2OOXML_LOCAL_PORT=8081 python tools/local_api.py run
```

### 5. Point the Figma plugin at your local server

At the bottom of the plugin UI there’s a **Developer Settings** panel. Expand it
and enter your local URL (for example `http://127.0.0.1:8080` or the ngrok URL)
in the *API URL override* field. Hit **Apply Overrides** and the plugin will
reload against the new endpoint.

- Leave the *Auth URL override* blank so OAuth still goes through Firebase
  Hosting.
- If you need HTTPS, expose the local server via `ngrok http 18123` (or whichever
  port you used) and enter the generated `https://*.ngrok-free.app` URL.
- Use **Clear Overrides** to revert to the production endpoints.

### 6. Trigger an export locally

Use the Figma plugin as usual. Requests now hit `http://127.0.0.1:8080`, so you
can inspect the FastAPI logs as the Slides upload runs.

For headless experiments you can also hit the API via curl:

```bash
export FIREBASE_TOKEN="$(gcloud auth print-identity-token)"
SVG2OOXML_BASE_URL=http://127.0.0.1:8080 \
FIREBASE_TOKEN="$FIREBASE_TOKEN" \
python tests/batch_export_w3c.py --limit 1
```

Note: the batch script uses the identity token's `sub` as the Firebase UID, so
ensure you have a matching `users/<uid>` document with `google_oauth` populated
if you expect Slides publishing to run.

## Using in Pytest Integration Tests

The Python-based local API server can be used directly in pytest integration
tests via fixtures:

```python
def test_export_endpoint(api_base_url):
    """Test the export endpoint against local server."""
    import requests

    response = requests.get(f"{api_base_url}/")
    assert response.status_code == 200
    assert response.json()["service"] == "svg2ooxml-export"
```

The `local_api_server` fixture (in `tests/integration/conftest.py`) automatically:
- Fetches secrets from GCP Secret Manager (cached in `secrets/local/`)
- Sets up environment variables
- Starts the uvicorn server on a test port (default: 8081)
- Stops the server after all tests complete

**Custom port**: Override the test port with the `SVG2OOXML_TEST_PORT` environment
variable:

```bash
SVG2OOXML_TEST_PORT=9000 pytest tests/integration/api/
```

## Programmatic Usage

You can also use the local API server programmatically in Python scripts:

```python
from src.svg2ooxml.api.testing import LocalAPIServer, LocalAPIConfig

# Create and start server
config = LocalAPIConfig(port=8080)
server = LocalAPIServer(config)
server.setup()  # Fetch secrets
server.start()  # Start uvicorn

# ... use the server ...

server.stop()  # Clean up

# Or use as a context manager
with LocalAPIServer(config) as server:
    # Server is running
    pass
# Server automatically stopped
```
