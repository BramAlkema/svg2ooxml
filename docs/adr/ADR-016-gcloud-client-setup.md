# ADR-016: Local gcloud Client Setup for svg2ooxml Cloud Run

**Status**: Accepted  
**Date**: 2025-10-27  
**Authors**: svg2ooxml Core Team

## Context

The svg2ooxml API is deployed to Google Cloud Run and relies on several managed
services (Firestore, Cloud Storage, Cloud Tasks). Team members frequently need
to:

- Trigger builds and deployments (`gcloud builds submit`, GitHub workflows,
  manual hotfixes)
- Call API endpoints during development (health checks, manual job creation)
- Inspect Cloud Run logs, job status, or queued Cloud Tasks

While the codebase documents the runtime architecture (see ADR-014), it lacked a
consolidated guide for configuring the gcloud CLI locally. Developers were often
blocked by missing auth tokens, wrong project selection, or absent SDK
components (Cloud Run/Tasks). This ADR captures the official setup so every
machine can interact with the Cloud Run service without guesswork.

## Decision

Document and standardise the gcloud client setup under source control:

1. **Install the Google Cloud SDK**  
   Follow <https://cloud.google.com/sdk/docs/install> for your OS.  
   Recommended: `brew install --cask google-cloud-sdk` on macOS.

2. **Initial authentication**  
   ```bash
   gcloud auth login
   gcloud auth application-default login  # for ADC-enabled libraries
   ```
   Both commands ensure the CLI and any Python client libraries obtain valid
   tokens.

3. **Select the svg2ooxml project and region**
   ```bash
   gcloud config set project powerful-layout-467812-p1
   gcloud config set run/region europe-west1
   ```
   (The project ID comes from the Cloud Run deployment; adjust if a new
   environment is spun up.)

4. **Install required components**  
   ```bash
   gcloud components install beta cloud-run core
   ```
   Ensure the Cloud Run and Cloud Build CLIs are available. Developers using
   Cloud Tasks or Firestore inspection can optionally install `cloud-firestore-emulator`
   and other extras.

5. **Configure required environment variables**  \
   Set them once per shell session (or add to your preferred `.env`).

   ```bash
   export GCP_PROJECT=powerful-layout-467812-p1
   export GCP_REGION=europe-west1
   export SERVICE_URL="https://svg2ooxml-export-sghya3t5ya-ew.a.run.app"
   # Optional: restrict API rate limiting and Slides uploads
   export SVG2OOXML_RATE_LIMIT=60
   export SVG2OOXML_RATE_WINDOW=60
   export GOOGLE_DRIVE_FOLDER_ID="<folder-id-for-slides-exports>"
   ```

   Cloud Run injects the same variables during deployment; keeping them aligned
   makes local commands behave like production.

6. **Reference commands for daily work**

   - List services:  
     `gcloud run services list`
   - Describe the deployed API:  
     `gcloud run services describe svg2ooxml-export --region europe-west1`
   - Tail logs:  
     `gcloud run services logs tail svg2ooxml-export --region europe-west1`
   - Invoke Cloud Build results:  
     `gcloud builds list --region europe-west1`
   - Print identity tokens when calling private endpoints:  
     `gcloud auth print-identity-token`

   These commands underpin the helper scripts in `tools/` such as
   `tools/google_slides_integration.py` (Slides upload/download) and
   `tools/visual/w3c_suite.py` (rendering + diffing W3C fixtures). They assume
   the active gcloud configuration points to the project/region above.

7. **Map custom domains**  \
   When pointing `app.example.com` (or similar) at the Cloud Run service:

   ```bash
   gcloud domains verify example.com
   gcloud run domain-mappings create \
     --service svg2ooxml-export \
     --domain app.example.com \
     --region europe-west1
   ````

   Google surfaces the DNS records to publish at your registrar (A/AAAA for the
   load balancer and a TXT/CNAME for certificate validation). Once propagated,
   the mapping and TLS certificate activate automatically.

8. **Document Cloud Tasks endpoint usage**  
   When inspecting jobs or requeueing tasks:
   ```bash
   gcloud tasks queues describe svg2ooxml-export-queue --location europe-west1
   gcloud tasks tasks list --queue svg2ooxml-export-queue --location europe-west1
   ```
   
9. **Service URL discovery**  
   `gcloud run services describe svg2ooxml-export --format='value(status.url)'`
   provides the base URL (e.g.,
   `https://svg2ooxml-export-237932518206.europe-west1.run.app`).

10. **Calling the API manually**  
   With the identity token from step 5 you can hit the export endpoint directly:  
   ```bash
   SERVICE_URL=$(gcloud run services describe svg2ooxml-export \
     --format='value(status.url)')
   TOKEN=$(gcloud auth print-identity-token)
   curl -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d @payload.json \
        "$SERVICE_URL/api/v1/export"
   ```
   The sample payload can be generated with `tools/google_slides_integration.py`
   or the fixtures under `tests/svg/`.

The ADR lives in the repo so new contributors can bootstrap quickly without
consulting internal wikis.

## Consequences

- Onboarding is faster: developers copy/paste the documented steps and interact
  with the Cloud Run API moments after cloning the repo.
- Build and deployment consistency improves: every machine stores identical
  project/region defaults.
- Reduced friction calling the deployed service (health, export jobs, Cloud
  Tasks) during debugging or demo sessions.
- The ADR supplements ADR-014 (deployment architecture) with the local CLI view,
  ensuring the team has both infrastructure and operational documentation inside
  git.
