# ADR-015 — Queue, Throttling, and Cache Strategy

- **Status:** Proposed  
- **Date:** 2025-10-27  
- **Owners:** svg2ooxml maintainers  
- **Depends on:** ADR-014 (Figma export service on Cloud Run), ADR-parser-batch-integration  
- **Revisits:** ADR-parser-core (service wiring), ADR-policy-map (pending)

## Context

ADR-014 brought the export HTTP surface online, but every conversion request still
runs inline inside FastAPI. That creates four pain points:

1. **No back-pressure.** A burst of requests can saturate a single Cloud Run
   instance; autoscaling only helps once the instance is already thrashing.
2. **Quota blind spots.** Nothing prevents a single tenant from spamming the
   `/export` endpoint and monopolising CPU/GPU budgets.
3. **Repeated work.** Identical frames/fonts generate brand‑new PPTX artefacts.
4. **Operational gaps.** There is no scheduled cleanup for temporary caches, nor
   metrics/alerts around queue depth or font download churn.

We need a job queue with built‑in throttles and caching hooks before exposing the
API broadly.

## Decision

Adopt **Huey** as the queue layer and layer throttling/caching around it:

1. **Huey task queue**
   - Run a Huey worker (Redis backend) alongside the Cloud Run service.
   - Wrap `ExportService.process_job` as `@huey.task`, scheduling retries/backoff.
   - API route enqueues work (`enqueue_export_job`) and returns immediately.
2. **Rate limiting / throttles**
   - FastAPI middleware (`slowapi` or similar) to cap requests per IP/Figma token.
   - Query Firestore for in-flight jobs; reject with HTTP 429 if global or
     per-tenant limits would be exceeded.
   - Huey worker count (and queue depth) define overall concurrency.
3. **Caching layers**
   - **Font cache:** keep remote fonts in `gs://…/font-cache/` plus a shared local
     directory; store metadata in Firestore for reuse across jobs.
   - **Conversion cache:** hash SVG payload + font set, reuse slide artefacts when
     hashes match, invalidating on svg2ooxml version bumps.
   - **Status cache:** LRU in-memory cache for `/export/{id}` responses to reduce
     Firestore load during polling bursts.
4. **Cleanup & monitoring**
   - Huey periodic tasks purge stale exports and expired font artefacts.
   - Emit queue depth and failure metrics to Cloud Logging/Monitoring.
   - Alert on job retries/failures and on queue length thresholds.

## Alternatives considered

- **Celery or Cloud Tasks:** heavier footprint; Huey already aligns with
  svg2pptx’s batch ADR and keeps dependencies minimal.
- **Autoscale-only approach:** doesn’t solve quota enforcement or duplicate work.
- **Pub/Sub or SQS:** adds cross-service complexity for the initial target scale.

## Consequences

- Redis (or SQLite) becomes required infrastructure; deployments must manage
  credentials and network egress.
- Workers need health/metrics endpoints so SREs can observe queue state.
- Cache invalidation must account for svg2ooxml version changes (e.g., include
  commit hash in conversion key).
- With Huey controlling concurrency, we can ratchet down Cloud Run max instances
  and let the queue hold bursts.

## Follow-up actions

1. Provision Redis (Cloud Memorystore) and inject `REDIS_URL` into Cloud Run.
2. Add `background/queue.py` and move conversion to Huey tasks.
3. Implement middleware enforcing per-IP and per-tenant request rates.
4. Introduce Firestore-backed active-job counters and conversion hash cache.
5. Add nightly Huey tasks to prune Storage/Firestore artefacts and warm critical
   fonts.
6. Publish dashboards/alerts for queue depth, failure rate, font download rate.
7. Update ADR-014 once the queue-backed version is live.
