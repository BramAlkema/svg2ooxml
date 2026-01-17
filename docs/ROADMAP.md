# Project Roadmap

Last updated: 2026-01-17

## Purpose
Provide a single, project-wide view of current status, near-term goals, and
outstanding work across the svg2ooxml codebase.

## Status Snapshot (actuals)
- Resvg migration: P1-P2 complete, P3 in progress (visual CI + telemetry
  dashboards pending), P4 pending default flip and legacy deprecation.
- Core pipeline: drawingml writer and pipeline remain partial; exporter gating
  and end-to-end pipeline tests still needed.
- Porting: modern modules are in place; legacy shims removed; docs and
  downstream references still need a sweep.
- Testing: visual suite exists; CI skips visual comparisons; lighting visual
  regression fixture not yet added.
- Telemetry: resvg metrics are aggregated into conversion summaries; dashboards
  and resvg vs legacy split counters are pending.
- Deployment/payment: payment integration is complete, but CI/CD is blocked
  because the GCP project was deleted and secrets are not configured.

## Outstanding Work (project-wide)
- Unblock CI/CD by restoring or replacing the GCP project, then configure secrets.
- Wire CI visual comparisons (resvg vs legacy) and add a lighting visual fixture.
- Ship telemetry dashboards and add resvg vs legacy split counters.
- Define parity thresholds, flip resvg defaults, and publish deprecation notes.
- Fill remaining DrawingML writer gaps and add end-to-end pipeline tests.
- Complete doc and downstream reference sweep for the post-legacy module layout.

## Near-Term Goals (next milestone)
- Decide on infra direction (restore/replace GCP project) and unblock CI/CD.
- Add CI visual comparisons for resvg vs legacy and publish diff artifacts.
- Add lighting visual regression fixture to the visual suite.
- Ship telemetry dashboards using `conversion.resvg_metrics`.
- Define parity thresholds and complete the resvg default flip plan.

## Sources
- `docs/resvg_migration_plan.md`
- `docs/specs/resvg-integration-roadmap.md`
- `docs/porting.md`
- `docs/refactoring_plan_2026-01-11.md`
- `docs/telemetry/resvg_metrics.md`
- `docs/NEXT_STEPS.md`
