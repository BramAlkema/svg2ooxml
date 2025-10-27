#!/bin/bash
# Setup script for Cloud Tasks queue and permissions

set -e

PROJECT_ID="${GCP_PROJECT:-powerful-layout-467812-p1}"
REGION="${CLOUD_TASKS_LOCATION:-europe-west1}"
QUEUE_NAME="${CLOUD_TASKS_QUEUE:-svg2ooxml-jobs}"
SERVICE_ACCOUNT="svg2ooxml-runner@${PROJECT_ID}.iam.gserviceaccount.com"

echo "Setting up Cloud Tasks for svg2ooxml..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Queue: $QUEUE_NAME"
echo ""

# Enable Cloud Tasks API
echo "Enabling Cloud Tasks API..."
gcloud services enable cloudtasks.googleapis.com --project="$PROJECT_ID"

# Create Cloud Tasks queue if it doesn't exist
echo "Creating Cloud Tasks queue..."
if gcloud tasks queues describe "$QUEUE_NAME" --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    echo "Queue $QUEUE_NAME already exists"
else
    gcloud tasks queues create "$QUEUE_NAME" \
        --location="$REGION" \
        --project="$PROJECT_ID" \
        --max-attempts=3 \
        --max-concurrent-dispatches=100 \
        --max-dispatches-per-second=10
    echo "✅ Created queue: $QUEUE_NAME"
fi

# Grant Cloud Tasks permissions to the service account
echo ""
echo "Granting Cloud Tasks permissions to service account..."

# Allow service account to create tasks
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/cloudtasks.enqueuer" \
    --condition=None

echo "✅ Granted cloudtasks.enqueuer role"

# Allow service account to be used by Cloud Tasks (for OIDC tokens)
gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/iam.serviceAccountUser" \
    --project="$PROJECT_ID"

echo "✅ Granted serviceAccountUser role"

echo ""
echo "✅ Cloud Tasks setup complete!"
echo ""
echo "Queue details:"
gcloud tasks queues describe "$QUEUE_NAME" \
    --location="$REGION" \
    --project="$PROJECT_ID"
