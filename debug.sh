#!/bin/bash
# Setup Cloud Build Trigger for svg2ooxml
# This script creates a Cloud Build trigger for the svg2ooxml repository

set -e  # Exit on error

# Configuration
REGION="europe-west1"
CONN="github-bram"
PROJECT="powerful-layout-467812-p1"
REPO_NAME="svg2ooxml"
TRIGGER_NAME="svg2ooxml-main"

echo "=== Cloud Build Trigger Setup for svg2ooxml ==="
echo ""

# Step 1: Ensure we're using the correct project
echo "Step 1: Setting the active project..."
gcloud config set project "$PROJECT"
echo "✓ Project set to: $PROJECT"
echo ""

# Step 2: Verify the repository exists
echo "Step 2: Verifying repository connection..."
REPO_RES=$(gcloud alpha builds repositories describe "$REPO_NAME" \
  --connection="$CONN" \
  --region="$REGION" \
  --format='value(name)' 2>/dev/null || echo "")

if [ -z "$REPO_RES" ]; then
    echo "❌ Repository not found. Please ensure the repository is connected."
    exit 1
fi
echo "✓ Repository found: $REPO_RES"
echo ""

# Step 3: Get the gitRepositoryLink using REST API
echo "Step 3: Fetching gitRepositoryLink..."
ACCESS_TOKEN=$(gcloud auth print-access-token)
GRL_RESPONSE=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://cloudbuild.googleapis.com/v2/projects/$PROJECT/locations/$REGION/connections/$CONN/repositories/$REPO_NAME")

# Extract gitRepositoryLink from JSON response (simple grep approach)
GRL=$(echo "$GRL_RESPONSE" | grep -o '"gitRepositoryLink":"[^"]*"' | cut -d'"' -f4)

if [ -z "$GRL" ]; then
    echo "⚠️  gitRepositoryLink not found in repository. Creating it..."
    
    # Create gitRepositoryLink using REST API
    curl -X POST \
      -H "Authorization: Bearer $ACCESS_TOKEN" \
      -H "Content-Type: application/json" \
      "https://cloudbuild.googleapis.com/v2/projects/$PROJECT/locations/$REGION/connections/$CONN/gitRepositoryLinks?git_repository_link_id=$REPO_NAME" \
      -d '{
        "cloneUri": "https://github.com/BramAlkema/svg2ooxml.git"
      }'
    
    # Construct the expected GRL path
    GRL="projects/$PROJECT/locations/$REGION/connections/$CONN/gitRepositoryLinks/$REPO_NAME"
    echo ""
fi

echo "✓ gitRepositoryLink: $GRL"
echo ""

# Step 4: Verify cloudbuild.yaml exists on main branch
echo "Step 4: Verifying cloudbuild.yaml exists on main branch..."
# Use gh CLI for authenticated access to private repo
if gh api repos/BramAlkema/svg2ooxml/contents/cloudbuild.yaml?ref=main > /dev/null 2>&1; then
    echo "✓ cloudbuild.yaml found on main branch"
else
    echo "❌ cloudbuild.yaml not found on main branch"
    echo "   Please ensure cloudbuild.yaml exists at the root of your main branch"
    exit 1
fi
echo ""

# Step 5: Create the trigger - Try multiple approaches
echo "Step 5: Creating Cloud Build trigger..."
echo ""

# First attempt: Try with alpha developer-connect (most likely to work)
echo "Attempting method 1: Alpha developer-connect trigger..."
if gcloud alpha builds triggers create developer-connect \
    --name="$TRIGGER_NAME" \
    --region="$REGION" \
    --git-repository-link="$GRL" \
    --branch-pattern="main" \
    --build-config="cloudbuild.yaml" 2>/dev/null; then
    echo "✓ Trigger created successfully using developer-connect!"
else
    echo "Method 1 failed, trying alternative..."
    echo ""
    
    # Second attempt: Try with beta developer-connect
    echo "Attempting method 2: Beta developer-connect trigger..."
    if gcloud beta builds triggers create developer-connect \
        --name="$TRIGGER_NAME" \
        --region="$REGION" \
        --git-repository-link="$GRL" \
        --branch-pattern="main" \
        --build-config="cloudbuild.yaml" 2>/dev/null; then
        echo "✓ Trigger created successfully using beta developer-connect!"
    else
        echo "Method 2 failed, trying alternative..."
        echo ""
        
        # Third attempt: Try with 2nd-gen github trigger using repository resource
        echo "Attempting method 3: GitHub trigger with repository resource..."
        if gcloud builds triggers create github \
            --name="$TRIGGER_NAME" \
            --region="$REGION" \
            --repository="$REPO_RES" \
            --branch-pattern="main" \
            --build-config="cloudbuild.yaml" 2>/dev/null; then
            echo "✓ Trigger created successfully using GitHub repository!"
        else
            echo "Method 3 failed, trying final alternative..."
            echo ""
            
            # Fourth attempt: Create trigger using REST API directly
            echo "Attempting method 4: Direct REST API call..."
            TRIGGER_PAYLOAD='{
              "name": "projects/'$PROJECT'/locations/'$REGION'/triggers/'$TRIGGER_NAME'",
              "github": {
                "name": "'$REPO_RES'",
                "push": {
                  "branch": "main"
                }
              },
              "filename": "cloudbuild.yaml"
            }'
            
            RESPONSE=$(curl -X POST \
              -H "Authorization: Bearer $ACCESS_TOKEN" \
              -H "Content-Type: application/json" \
              "https://cloudbuild.googleapis.com/v1/projects/$PROJECT/locations/$REGION/triggers" \
              -d "$TRIGGER_PAYLOAD" 2>&1)
            
            if echo "$RESPONSE" | grep -q "error"; then
                echo "❌ All methods failed. Last error response:"
                echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
                echo ""
                echo "=== Manual Fix Required ==="
                echo "Please try running with debug flags to see the exact error:"
                echo ""
                echo "gcloud builds triggers create github \\"
                echo "  --name=$TRIGGER_NAME \\"
                echo "  --region=$REGION \\"
                echo "  --repository=\"$REPO_RES\" \\"
                echo "  --branch-pattern=main \\"
                echo "  --build-config=cloudbuild.yaml \\"
                echo "  --verbosity=debug --log-http"
                exit 1
            else
                echo "✓ Trigger created successfully using REST API!"
            fi
        fi
    fi
fi

echo ""
echo "=== Verification ==="
echo "Listing triggers in $REGION..."
gcloud builds triggers list --region="$REGION" \
  --format='table(name,region,github.name,createTime)' 2>/dev/null || \
  echo "Unable to list triggers. Please verify manually."

echo ""
echo "=== Next Steps ==="
echo "1. Verify the trigger appears in the Cloud Console:"
echo "   https://console.cloud.google.com/cloud-build/triggers;region=$REGION?project=$PROJECT"
echo ""
echo "2. Test the trigger by pushing to the main branch:"
echo "   git commit --allow-empty -m 'Test Cloud Build trigger'"
echo "   git push origin main"
echo ""
echo "3. Monitor the build:"
echo "   gcloud builds list --region=$REGION --limit=5"
echo ""
echo "✅ Setup complete!"
