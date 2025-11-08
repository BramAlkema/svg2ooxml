## Local Backend Testing (Slides Publishing)

Run the FastAPI service on your laptop against the real Firestore/Drive stack so
you can iterate on Slides uploads without redeploying to Cloud Run.

### 1. Prerequisites

- `gcloud` CLI authenticated against `powerful-layout-467812-p1`
- Secret Manager access to `firebase-service-account`, `token-encryption-key`,
  `firebase-web-client-id`, and `firebase-web-client-secret`
- Python virtualenv bootstrapped via `./tools/bootstrap_venv.sh`

### 2. Bootstrap secrets + env vars

Run the helper script once (or whenever you need to refresh secrets):

```bash
bash tools/local_api.sh setup
```

This pulls the four required Secret Manager entries into `secrets/local/` and
writes `.env.local` with all exports (`ENVIRONMENT`, `TOKEN_ENCRYPTION_KEY`,
Firebase web client ID/secret, etc.). Source the env file whenever you open a
new shell:

```bash
source .env.local
```

### 3. Start the API locally

```bash
bash tools/local_api.sh run
```

The server will connect to real Firestore/Storage using the service account and
use the same encryption key, so existing `google_oauth` tokens continue to work.

### 5. Point the Figma plugin at your local server

The UI now supports dev overrides (see `figma-plugin/ui.js`). Open the plugin’s
console (Figma → `Menu > Plugins > Development > Open Console`) and run:

```js
localStorage.setItem('svg2ooxml_api_url', 'http://127.0.0.1:8080');
location.reload();
```

- Keep `AUTH_URL` untouched so OAuth still goes through Firebase Hosting.
- If you need HTTPS, expose the local server via `ngrok http 8080` and set the
  override to the generated `https://*.ngrok-free.app` URL.
- To reset: `localStorage.removeItem('svg2ooxml_api_url'); location.reload();`

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

Note: the batch script uses the identity token’s `sub` as the Firebase UID, so
ensure you have a matching `users/<uid>` document with `google_oauth` populated
if you expect Slides publishing to run.
