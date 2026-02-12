# ADR-025: Quality Roadmap Necessity (Determinism, Resvg-Only, Filters, Policies, Fonts, Docker)

- **Status:** Accepted
- **Date:** 2026-02-12
- **Last Updated:** 2026-02-12
- **Owners:** svg2ooxml team
- **Related:** ADR-017 (resvg rendering strategy), ADR-018 (EMF fallbacks), ADR-024 (batch conversion performance)

## 1. Problem Statement

We need to decide whether the current quality roadmap is required or optional. The roadmap items are:

- Deterministic corpus sampling + OpenXML audit gating.
- Resvg-only pipeline as default with a controlled legacy escape hatch.
- Filter fidelity improvements (feImage, blend/composite/color_matrix fallbacks).
- Policy and test alignment to stop per-test churn.
- Font and asset reliability (path resolution, caching, FontForge guards).
- Docker and runtime ergonomics (one-command environment, cache volumes).

This ADR evaluates if these items are necessary for a SaaS-grade product and establishes which are required to progress toward a stable 8.5–9/10 quality bar.

## 2. Context and Evidence

- The testing guide expects multiple tiers and optional visual checks but does not mandate deterministic sampling or OpenXML audit in CI. See `docs/testing.md`.
- The resvg strategy explicitly targets native → resvg → raster and acknowledges ongoing resvg work; default behaviors are still evolving. See `docs/resvg.md`.
- W3C corpus tooling exists but relies on metadata generation and does not enforce determinism or audit gating by default. See `tests/corpus/run_corpus.py` and `tests/corpus/add_w3c_corpus.py`.
- Fonts and external assets are common sources of portability issues (font caches, local paths, W3C resource layouts). See `docs/specs/web-font-support.md` and `src/svg2ooxml/services/fonts/`.
- Operational reliability matters for SaaS: reproducible outputs, clean audits, and predictable runtime are required for support, customer trust, and cost control.

## 3. Decision

We will adopt the roadmap, but with explicit priority tiers.

Required (must complete):

- Deterministic corpus sampling and OpenXML audit gating.
- Resvg-only as the default strategy with a controlled legacy fallback.
- Filter fidelity improvements for the primitives that dominate W3C and real-world test failures.
- Policy and test alignment to prevent per-test drift.
- Font and asset reliability for W3C and customer SVGs.

Strongly recommended (near-term):

- Docker/runtime ergonomics to guarantee a single reproducible environment and cache volumes.

Optional (later):

- Broader performance optimization beyond the above unless new regressions show a clear need.

## 4. Rationale by Item

Deterministic corpus + OpenXML audit gating is required because:

- Regression detection is currently noisy without fixed samples.
- OpenXML audit is the only reliable gate for PPTX correctness in production.

Resvg-only default is required because:

- Mixed pipelines are harder to reason about and debug.
- Stable resvg-only provides consistent metrics and reduces back-and-forth in quality audits.

Filter fidelity improvements are required because:

- Filters are a high-visibility feature; failures force raster or EMF fallbacks, degrading output and editability.
- The current resvg strategy explicitly acknowledges missing fidelity for key primitives.

Policy and test alignment is required because:

- Tests currently encode expectations that change with pipeline evolution.
- Per-test adjustments create churn and hide regressions.

Font and asset reliability is required because:

- Missing fonts or incorrect path resolution directly impact output correctness and customer trust.
- W3C and real-world SVGs include relative resources and embedded fonts.

Docker/runtime ergonomics is strongly recommended because:

- Dependency friction (FontForge, LibreOffice, audit tooling) is a recurring source of failure.
- A single containerized environment reduces onboarding and CI variance.

## 5. Consequences

Positive outcomes:

- Fewer regressions and faster diagnosis due to deterministic sampling and audit gating.
- Clearer ownership of output quality with resvg-only as default.
- Reduced noise in tests and metrics through policy alignment.
- Improved portability and developer experience with standardized runtime.

Tradeoffs:

- Increased short-term engineering effort for filters and policy work.
- Some legacy behavior will be deprecated, requiring a controlled migration window.

## 6. Success Criteria

- W3C sample runs are deterministic via seed and report stable metrics.
- OpenXML audit pass rate is above 98% on the sample set in CI.
- Resvg-only is the default pipeline, with legacy gated behind an explicit escape hatch.
- Filter primitives listed above show improved native or resvg fidelity and reduced raster fallbacks.
- Font resolution and webfont caching work across W3C and real-world fixtures.
- Docker runs corpus + audit with no manual setup steps.

## 7. Rollout Plan

- Phase 1: Deterministic sampling + OpenXML audit gating in CI.
- Phase 2: Resvg-only default and policy alignment.
- Phase 3: Filter fidelity improvements and font/asset hardening.
- Phase 4: Docker ergonomics and documentation updates.

## 10. Implementation Status

- **Phase 1 (in CI):** Deterministic W3C sampling + OpenXML audit gating wired into `Tests` workflow.
- **Phase 2 (done):** Resvg-only default path + policy/test alignment landed; legacy geometry removed.
- **Phase 3 (in progress):** Filter fidelity + font/asset hardening (feImage href resolution + corpus image resolver wiring landed; composite mask wrapping landed). Remaining: blend/composite/color_matrix fidelity, font/asset caching.
- **Phase 4 (pending):** Docker runtime ergonomics and documentation updates.

## 8. Alternatives Considered

- Keep mixed pipeline as default and only tune tests.
  - Rejected: continues churn and masks regressions.

- Keep OpenXML audit optional and manual.
  - Rejected: fails to enforce PPTX correctness as a quality gate.

- Delay filter work and rely on raster fallbacks.
  - Rejected: degrades editability and visual fidelity for core SVG features.

## 9. Open Questions

- What is the acceptable deprecation window for legacy geometry mode?
- What is the smallest deterministic sample size that still catches regressions?
- Which filter primitives should be prioritized after the initial set?
