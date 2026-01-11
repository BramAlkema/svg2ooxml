# Smoke Tests

End-to-end smoke tests for the svg2ooxml export API deployed on Cloud Run.

## Authentication

The export API requires authentication. The smoke tests support multiple authentication methods:

### Method 1: Google Cloud Identity Token (Recommended for Local Testing)

This is the simplest method for developers with gcloud access:

```bash
export SVG2OOXML_AUDIENCE=https://svg2ooxml-export-sghya3t5ya-ew.a.run.app
export FIREBASE_TOKEN="$(gcloud auth print-identity-token)"
pytest tests/smoke/test_export_flow.py -m smoke
```

**How it works:**
- Uses your gcloud credentials to generate an identity token
- The API's authentication middleware (`src/svg2ooxml/api/auth/firebase.py`) accepts Google Identity tokens as a fallback
- No additional setup required if you're already authenticated with gcloud

### Method 2: Firebase ID Token (Production)

For testing with production Firebase credentials:

```bash
export FIREBASE_TOKEN="<your-firebase-id-token>"
pytest tests/smoke/test_export_flow.py -m smoke
```

The Firebase token is what the Figma plugin uses in production.

### Method 3: Service Account Impersonation

For CI/CD or automated testing with service account permissions:

```bash
export SVG2OOXML_AUDIENCE=https://svg2ooxml-export-sghya3t5ya-ew.a.run.app
export FIREBASE_TOKEN="$(gcloud auth print-identity-token \
  --impersonate-service-account=svg2ooxml-runner@powerful-layout-467812-p1.iam.gserviceaccount.com \
  --audiences=$SVG2OOXML_AUDIENCE)"
pytest tests/smoke/test_export_flow.py -m smoke
```

**Prerequisites:**
- User account must have `roles/iam.serviceAccountTokenCreator` role on the service account
- Grant permission with:
  ```bash
  gcloud iam service-accounts add-iam-policy-binding \
    svg2ooxml-runner@powerful-layout-467812-p1.iam.gserviceaccount.com \
    --member="user:YOUR-EMAIL@example.com" \
    --role="roles/iam.serviceAccountTokenCreator" \
    --project=powerful-layout-467812-p1
  ```

### Method 4: Anonymous Testing (Limited)

For testing public endpoints only (health check):

```bash
export SVG2OOXML_ANON_TEST=true
pytest tests/smoke/test_export_flow.py -m smoke
```

**Note:** This will skip tests that require authentication (export endpoints).

## Test Coverage

The smoke tests verify:

1. **Health Endpoint** (`/health`)
   - Service is running and responding
   - Returns `{"status": "healthy"}`

2. **Export Job Lifecycle** (`/api/v1/export`, `/api/v1/export/{job_id}`)
   - Create export job (PPTX format)
   - Create export job (Slides format)
   - Poll job status until completion or timeout (60 seconds)
   - Verify job metadata and status transitions

## Environment Variables

- `SVG2OOXML_BASE_URL` - API base URL (default: production Cloud Run URL)
- `SVG2OOXML_AUDIENCE` - Token audience for identity tokens (default: base URL)
- `FIREBASE_TOKEN` - Authentication token (Firebase ID or Google Identity)
- `SVG2OOXML_ANON_TEST` - Set to `true` to skip authenticated tests
- `SVG2OOXML_SMOKE_STRICT` - Set to `true` to fail on network errors instead of skipping
- `GCLOUD_BIN` - Path to gcloud binary (default: `gcloud`)

### Server-Side Environment Variables

These are set on the Cloud Run service:

- `DISABLE_EXPORT_QUOTA` - Set to `true` to disable the 5 export/month quota limit (default: `false`). **Use only for testing/development.**

## Troubleshooting

### "Authentication token missing" error

The test was skipped because no valid token was provided. Use one of the authentication methods above.

### "Smoke endpoint unreachable" skip

The smoke tests skip when the base URL cannot be reached (DNS/timeout). Set
`SVG2OOXML_BASE_URL` to a reachable service or export
`SVG2OOXML_SMOKE_STRICT=true` to force a failure instead of skipping.

### 402 Payment Required error

You've exceeded the free tier quota (5 exports per month). This is expected for accounts without an active subscription. The quota resets monthly.

To bypass quota limits for testing:
- **Recommended:** Update the Cloud Run service to set `DISABLE_EXPORT_QUOTA=true`:
  ```bash
  gcloud run services update svg2ooxml-export \
    --region=europe-west1 \
    --update-env-vars=DISABLE_EXPORT_QUOTA=true
  ```
  Remember to set it back to `false` for production.
- Test with a service account that has a Pro subscription
- Manually reset usage in Firestore (collection: `usage`, document: `{uid}_{YYYY-MM}`)
- Wait until the next calendar month

### 403 Forbidden error

Your token is being sent but is invalid or expired. Common causes:
- Token has expired (generate a new one)
- Wrong audience specified for service account tokens
- User doesn't have access to the API

Try generating a fresh token:
```bash
export FIREBASE_TOKEN="$(gcloud auth print-identity-token)"
```

### "Failed to impersonate" error

Your user account doesn't have permission to impersonate the service account. See Method 3 prerequisites above.

## CI/CD Integration

For GitHub Actions or other CI systems, use service account key authentication:

```yaml
- name: Run smoke tests
  env:
    GOOGLE_APPLICATION_CREDENTIALS: ${{ secrets.GCP_SA_KEY }}
    SVG2OOXML_AUDIENCE: https://svg2ooxml-export-sghya3t5ya-ew.a.run.app
  run: |
    export FIREBASE_TOKEN="$(gcloud auth print-identity-token --audiences=$SVG2OOXML_AUDIENCE)"
    pytest tests/smoke/test_export_flow.py -m smoke
```
