# Testing Setup

Quick reference for setting up and running tests against the deployed Cloud Run service.

## Smoke Tests

End-to-end tests that verify the API is working correctly in production.

### Quick Start

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Authenticate and run tests
export FIREBASE_TOKEN="$(gcloud auth print-identity-token)"
pytest -m smoke tests/smoke/ -v
```

### Bypassing Quota Limits

The API enforces a 5 export/month limit for free tier users. For testing, you can disable quota checking:

```bash
# Enable unlimited exports (development/testing only)
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --update-env-vars=DISABLE_EXPORT_QUOTA=true

# Re-enable quota limits (production)
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --update-env-vars=DISABLE_EXPORT_QUOTA=false
```

**Important:** The `cloudbuild.yaml` deployment always sets `DISABLE_EXPORT_QUOTA=false` by default (production safe). After each deployment via Cloud Build, you'll need to manually re-enable the override for testing.

## Authentication Methods

See `tests/smoke/README.md` for detailed authentication options.

**Simplest method for developers:**
```bash
export FIREBASE_TOKEN="$(gcloud auth print-identity-token)"
```

This uses your gcloud credentials. The API accepts Google Identity tokens as a fallback to Firebase tokens.

## Verifying Deployment Status

```bash
# Check service status
gcloud run services describe svg2ooxml-export --region=europe-west1

# Check quota setting
gcloud run services describe svg2ooxml-export --region=europe-west1 \
  --format="value(spec.template.spec.containers[0].env)" | grep DISABLE_EXPORT_QUOTA

# View recent logs
gcloud run services logs read svg2ooxml-export --region=europe-west1 --limit=50

# Check recent builds
gcloud builds list --limit=5 --region=europe-west1
```

## Common Workflows

### After pushing code changes:

1. Wait for GitHub Actions tests to pass
2. Wait for Cloud Build deployment to complete (~6 minutes)
3. If running smoke tests, re-enable quota override (see above)
4. Run smoke tests

### Testing locally before deployment:

```bash
# Run unit tests
pytest -m "unit and not slow"

# Run all tests except smoke
pytest -m "not smoke"

# Check linting
ruff check src tests
```
