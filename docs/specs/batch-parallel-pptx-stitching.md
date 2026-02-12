# Spec: Parallel Batch PPTX Stitching (Huey + Redis)

- **Status:** Draft
- **Date:** 2026-02-13
- **Owners:** svg2ooxml team
- **Related:** ADR-025, ADR-026, ADR-015 (queue throttle), ADR-parser-batch-integration

## 1. Problem

Massive decks (hundreds/thousands of slides) cannot be processed efficiently
by a single worker. We need parallel slide rendering with a deterministic,
single PPTX output that passes OpenXML audit.

## 2. Goals

- Parallelize slide conversion using Redis-backed Huey workers.
- Produce **one PPTX** per job by stitching per-slide outputs in order.
- Keep output deterministic, OpenXML-valid, and idempotent.
- Support bail-on-first-failure and resumable stitching.
- Make it work locally (SQLite Huey) and in prod (Redis Huey).

## 3. Non-Goals

- Cross-slide layout merges beyond ordering (no dynamic reflow).
- Real-time streaming to client during conversion.
- Multi-deck output (still one job → one PPTX).

## 4. Architecture Overview

1. **Splitter**: breaks a job into slide tasks with a stable `slide_index`.
2. **Workers**: render one slide each and emit a `SlideBundle`.
3. **Storage**: slide bundles persisted in shared storage.
4. **Stitcher**: assembles ordered bundles into one PPTX.
5. **Audit**: run OpenXML validation on the final PPTX.

## 5. Data Contracts

### 5.1 Task Payload (Huey)

Required:
- `job_id`: stable job identifier.
- `slide_index`: 1-based index.
- `svg_content` (or serialized frame payload).
- `policy_overrides` (optional).
- `mode`: resvg-only.

Optional:
- `output_dir` for bundle storage.
- `resources` (fonts/images) if pre-fetched.

### 5.2 SlideBundle Layout (filesystem)

```
bundle_root/
  job_id/
    slide_0001/
      slide.xml
      _rels/slide.xml.rels
      media/
        image1.png
      fonts/
        font1.fntdata
      metadata.json
```

`metadata.json` includes:
- `job_id`, `slide_index`, `created_at`
- `slide_size` (width/height, units)
- `media_hashes` (for dedupe)
- `font_families` and embedding metadata
- `warnings` / `fallbacks` / tracer summary

## 6. Stitcher Responsibilities

- Order bundles by `slide_index`.
- Normalize relationship IDs and content types.
- Deduplicate media by hash (single copy under `/ppt/media`).
- Merge font embeddings:
  - Consolidate by family + style.
  - Ensure `presentation.xml` has consistent `embeddedFontLst`.
- Write `/ppt/presentation.xml` and rels in order.
- Build content types and finalize the PPTX package.
- Run OpenXML audit (strict) on final package.

## 7. Failure Handling

- **Worker failure**: mark slide as failed; optionally bail or continue based
  on job policy.
- **Stitch failure**: leave bundles intact; allow retry.
- **Audit failure**: job marked failed; preserve output and audit report.

## 8. Determinism & Idempotency

- Bundle paths are deterministic (`slide_XXXX`).
- Dedupe uses stable hashes (SHA-256) for media.
- Stitcher is idempotent: can be rerun with same bundles.

## 9. Storage Strategy

Local/dev:
- `SVG2OOXML_TEMP_DIR` or project temp dir.

Prod:
- Shared filesystem (PVC) or object storage (GCS/S3).
- If object storage is used, add a small manifest to list bundle URIs.

## 10. Observability

- Per-slide metrics: conversion time, fallbacks, size.
- Job metrics: total time, success rate, audit outcome.
- Emit structured logs per slide and per job.

## 11. Testing

- Unit: bundle writer, stitcher merge logic, media dedupe.
- Integration: small multi-slide job end-to-end on SQLite Huey.
- CI: W3C sample split + stitch, OpenXML audit gating.

## 12. Rollout

1. Implement bundle serialization + stitcher (local path).
2. Add Redis Huey tasks and coordinator.
3. Wire into API/export path for large jobs.
4. Enable in prod behind a feature flag.

## 13. Task Breakdown (Agents)

**Agent A – Spec & Contracts**
- Finalize task payloads and SlideBundle format.
- Define metadata schema and versioning.

**Agent B – Queue/Worker**
- Implement Huey tasks for slide rendering.
- Add Redis/SQLite configuration and env vars.
- Ensure idempotent bundle writes.

**Agent C – Stitcher**
- Implement bundle loader + PPTX stitcher.
- Media/font dedupe and content types merge.
- OpenXML audit integration + report artifacts.

**Agent D – Tests**
- Unit tests for bundle/stitcher.
- Integration test: 5-slide deck → stitched PPTX.
- CI gate for OpenXML audit on stitched output.

**Agent E – Docs/CLI**
- Add CLI for `split`, `stitch`, `run-job`.
- Update docs and operational guidance.
