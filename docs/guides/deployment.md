# Deployment Guide

## Prerequisites

### Service Account Permissions

The Cloud Run service account (`svg2ooxml-runner@PROJECT_ID.iam.gserviceaccount.com`) needs the following IAM roles:

1. **Firestore Access**
   ```bash
   gcloud projects add-iam-policy-binding PROJECT_ID \
     --member="serviceAccount:svg2ooxml-runner@PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/datastore.user"
   ```

2. **Cloud Storage Management**
   ```bash
   gcloud projects add-iam-policy-binding PROJECT_ID \
     --member="serviceAccount:svg2ooxml-runner@PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/storage.admin"
   ```

3. **Self-Signing for Signed URLs** (REQUIRED for generating download links)
   ```bash
   gcloud iam service-accounts add-iam-policy-binding \
     svg2ooxml-runner@PROJECT_ID.iam.gserviceaccount.com \
     --member="serviceAccount:svg2ooxml-runner@PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/iam.serviceAccountTokenCreator"
   ```

   This allows the service account to sign its own blob URLs without needing a key file.

## Deployment

The service deploys automatically via Cloud Build when pushing to `main`:

```bash
git push origin main
```

Monitor the build:
```bash
gcloud builds list --region=europe-west1 --limit=5
```

## Verification

Test the deployed service:

```bash
SERVICE_URL="https://svg2ooxml-export-237932518206.europe-west1.run.app"

# Health check
curl $SERVICE_URL/health

# Create export job
curl -X POST $SERVICE_URL/api/v1/export \
  -H "Content-Type: application/json" \
  -d '{
    "frames": [{"name": "Test", "svg_content": "<svg></svg>", "width": 100, "height": 100}],
    "figma_file_id": "test",
    "output_format": "pptx"
  }'
```

## Troubleshooting

### "you need a private key to sign credentials" error

This means the service account doesn't have the `roles/iam.serviceAccountTokenCreator` role on itself.
Run the self-signing command above.

### Job fails with "403 Missing or insufficient permissions"

Check that the service account has all three roles listed above.

### No signed URL in response

Check Cloud Run logs:
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=svg2ooxml-export" \
  --limit=50 --project=PROJECT_ID
```
