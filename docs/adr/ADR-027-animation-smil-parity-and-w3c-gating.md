# ADR-027: Animation SMIL Parity and W3C Gating Strategy

- **Status:** Proposed
- **Date:** 2026-02-21
- **Owners:** svg2ooxml animation and quality teams
- **Depends on:** ADR-020 (animation writer rewrite), ADR-023 (schema validation), ADR-025 (quality roadmap)
- **Related:** `docs/specs/animation-smil-parity-spec.md`, `docs/specs/animation-w3c-suite-execution-spec.md`

## 1. Problem Statement

The current animation pipeline already emits valid PowerPoint timing XML for core
SMIL features, but parity gaps remain in SMIL semantics (`begin` event triggers,
`mpath` resolution, motion rotation behavior). At the same time, W3C validation is
not yet used as a strict release gate for animation behavior.

We need one decision that aligns implementation priorities and validation policy.

## 2. Context

- `src/svg2ooxml/core/animation/parser.py` supports primary SMIL tags but parses
  `begin` as simple time values.
- `src/svg2ooxml/drawingml/animation/handlers/motion.py` converts motion paths
  to `p:animMotion`, but does not implement tangent-follow rotation.
- `src/svg2ooxml/drawingml/animation/writer.py` suppresses full timing output
  for certain policy paths rather than degrading only unsupported fragments.
- W3C tooling exists (`tests/corpus/run_w3c_corpus.sh`, `tests/corpus/run_corpus.py`)
  but default category flows are primarily non-animation focused.

## 3. Decision

1. Keep native OOXML animation generation as the primary architecture.
2. Prioritize SMIL semantic parity over adding new animation effect breadth.
3. Introduce animation-focused W3C execution profiles and treat them as release
   validation gates for animation changes.
4. Move from whole-timing suppression to per-fragment degrade/omit behavior where
   schema or fidelity constraints are violated.

## 4. Scope

### In Scope

- `begin` trigger parsing/modeling (`time`, `click`, `id.begin`, `id.end`, offsets)
- `animateMotion` path reference resolution (`mpath`)
- Motion rotation approximation for `rotate="auto"` behavior
- Policy rewrite for targeted fallback decisions
- W3C corpus runs and report review for animation quality tracking

### Out of Scope

- JavaScript-driven animation synchronization
- Full SMIL scripting/event model beyond declarative timing primitives
- Replacing native writer with a third-party presentation library

## 5. Rationale

- The existing handler architecture is stable and already schema-aware.
- Gaps are concentrated in parser semantics and fallback policy strategy.
- W3C-driven quality checks are repeatable and already integrated into repo tools.
- This approach minimizes architectural churn while improving fidelity and
  reliability where users feel defects.

## 6. Consequences

### Positive

- Better user-visible parity for common animated SVGs.
- Fewer all-or-nothing animation drops.
- Clearer regression detection through repeatable W3C runs.

### Negative

- Additional complexity in IR timing models and mapping logic.
- Longer CI/runtime in animation-focused validation pipelines.
- Short-term increase in policy and compatibility edge cases.

## 7. Rollout

1. Implement spec slices in `docs/specs/animation-smil-parity-spec.md`.
2. Execute validation profiles from `docs/specs/animation-w3c-suite-execution-spec.md`.
3. Track outcomes and unresolved deltas in a dedicated report issue for each run.
4. Flip release gating from advisory to required once baseline pass criteria are met.

## 8. Acceptance Criteria

- Parser + writer changes ship with unit/integration coverage for new semantics.
- W3C animation-targeted profile runs complete with published report artifacts.
- No new OpenXML schema failures for animation-bearing slides.
- Timing XML remains present for partially supported scenes, with unsupported
  fragments explicitly omitted or downgraded.
