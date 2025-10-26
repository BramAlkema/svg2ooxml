# ADR-014 — Figma export service on Google Cloud Run

- Status: Accepted
- Date: 2025-03-19
- Owners: svg2ooxml maintainers
- Related: ADR-parser-core, ADR-color-engine-port

## Context

We want a Figma plugin that converts selected frames into PowerPoint decks and
publishes them straight to Google Slides. The converter already exists inside
svg2ooxml, but it requires Python with native extensions (`numpy`,
`skia-python`, `lxml`) plus dynamic font handling. Earlier explorations looked at
Replit and Vercel, but they either sleep frequently or cannot install the
dependencies we need. LibreOffice (`soffice`) also adds ~800 MB of baggage if we
try to rasterise slides ourselves.

The ideal rollout should:

- keep the runtime lean (no LibreOffice) while preserving SVG→PPTX fidelity;
- reuse Google Slides for public previews/thumbnails;
- stay inside free tiers until usage scales;
- support automatic deployments from the GitHub repo; and
- let the Figma plugin invoke a single HTTPS endpoint.

## Decision

We will run the export API on **Google Cloud Run**, built from source with Cloud
Build’s buildpacks (no handwritten Dockerfile). The service will:

1. Accept SVG payloads from the Figma plugin.
2. Run svg2ooxml (Python 3.13, `numpy`, `skia-python`, `colorspacious`, `lxml`)
   to produce a PPTX for each request.
3. Cache or download required fonts on demand (embedded payloads or Google
   Fonts) so text fidelity matches the Figma design.
4. Store the PPTX in Cloud Storage, then upload to Google Drive and convert or
   publish it via the Slides API to obtain shareable links and slide thumbnails.
5. Persist job metadata in Firestore so the plugin can poll status.
6. Return Drive/slides URLs (and optional signed Cloud Storage links) to the
   plugin; the plugin never transfers large binaries directly.

Cloud Build will trigger on pushes to `main`, build the image via buildpacks,
push it to Artifact Registry, and deploy the new revision to Cloud Run. Secrets
(service account JSON, API keys) live in Secret Manager, mounted at runtime.

## Alternatives considered

- **Replit-based FastAPI service**: attractive for quick prototypes, but
  frequent cold starts, tighter CPU/RAM limits, and lack of native dependency
  support made it brittle for production workloads.
- **Render / Railway with LibreOffice**: viable, but requires shipping
  `soffice` (~800 MB) just to produce thumbnails. Since we can ask Google Slides
  for thumbnails, the added maintenance didn’t justify the size.
- **Pure Google Slides converter (no svg2ooxml)**: Slides cannot ingest raw Figma
  SVG with the fidelity we need, and font coverage is limited to Google’s set.
  We still need svg2ooxml to build a PPTX first.
- **Serverless Cloud Functions (Gen2)**: limited ability to install native wheels
  without custom containers, which returns us to Cloud Run anyway.

## Consequences

- All exports run inside GCP and enjoy autoscaling, HTTPS, and IAM integration.
- We depend on Drive/Slides quotas; heavy usage will require quota increases and
  better caching. We also must delete staged files to avoid storage bloat.
- The free tier covers our initial load (≤2 million requests/month) but bursts
  beyond that incur per-second charges.
- Buildpacks remove the need for Dockerfiles but still output OCI images, so we
  must monitor image size and layer caching.
- The Figma plugin needs a polling flow (job create → status check) rather than
  a single synchronous response for long conversions.
- We must manage font caching carefully (tmp directory cleanup, license
  compliance).

## Follow-up actions

1. Create the GCP project, enable Cloud Run, Cloud Build, Cloud Storage,
   Firestore, Drive, and Slides APIs. Provision the service account with
   `drive.file`, `slides`, and storage roles.
2. Add a Cloud Build trigger (push to `main`) that builds via buildpacks and
   deploys to `svg2ooxml-export` Cloud Run service.
3. Implement the FastAPI app with endpoints for job submission and status, plus
   font caching and Google API integration.
4. Set up Firestore collections (`exports`) and a background cleanup task to
   purge stale Drive/Storage artefacts.
5. Build the Figma plugin UI that exports SVG, calls the Cloud Run endpoint, and
   displays publish links and thumbnails.
6. Define monitoring/alerts (Cloud Logging sinks, error rate dashboards) and a
   retention policy for exported decks.
