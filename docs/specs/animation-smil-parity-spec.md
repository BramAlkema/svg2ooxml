# Animation SMIL Parity Specification

- **Status:** Draft
- **Date:** 2026-02-21
- **ADR:** `docs/adr/README.md` (`SMIL Parity & W3C Gating`)
- **Documentation map:** `docs/internals/animation-documentation-map.md`
- **Primary Modules:**
  - `src/svg2ooxml/core/animation/parser.py`
  - `src/svg2ooxml/ir/animation.py`
  - `src/svg2ooxml/drawingml/animation/writer.py`
  - `src/svg2ooxml/drawingml/animation/handlers/motion.py`
  - `src/svg2ooxml/drawingml/animation/policy.py`

## 1. Goals

1. Improve semantic parity for core declarative SMIL timing behavior.
2. Preserve valid OOXML output while reducing unnecessary timing suppression.
3. Keep degradation explicit, local, and traceable in telemetry.

## 2. Non-Goals

- Full SMIL script/event runtime parity.
- Arbitrary animation graph dependency resolution.
- Browser-level animation APIs.

## 3. Requirements

### R1: Begin Trigger IR

Introduce a richer begin trigger model in IR that supports:
- absolute offsets (`2s`, `500ms`)
- element click (`click`, `shape.click`)
- element lifecycle references (`shape.begin`, `shape.end`)
- signed offsets from references (`shape.end+0.5s`, `shape.begin-250ms`)

Backward compatibility: simple numeric `begin` inputs must continue to work.

### R2: Parser Begin Semantics

`SMILParser` must parse begin expressions into structured triggers. Invalid values:
- add warnings to `AnimationSummary`
- degrade to deterministic default (`0s`) rather than raising hard failure

### R3: `mpath` Resolution

`animateMotion` with `<mpath href="#pathId">` must resolve referenced path `d`
content before handing values to motion conversion.

If referenced path is missing:
- emit warning
- omit motion fragment only (not entire animation timing tree)

### R4: Motion Rotation Approximation

Support an approximation path for `rotate="auto"`:
- derive tangent direction from sampled motion segments
- translate tangent into rotation animation behavior
- allow policy opt-out where fidelity risk is high

### R5: Localized Policy Degradation

Replace whole-tree timing suppression strategy with per-fragment suppression where
possible:
- unsupported fragment -> `fragment_skipped` with reason
- supported fragments still emit inside `p:timing`

Global timing suppression remains allowed only for explicit user policy modes that
request no native timing output.

### R6: Telemetry Contract

Trace events must include deterministic reason codes for:
- begin trigger parse fallback
- unresolved `mpath`
- rotate-auto downgrade
- policy-driven fragment suppression

## 4. Data Model Changes

Proposed additions in `src/svg2ooxml/ir/animation.py`:
- `BeginTriggerType` enum
- `BeginTrigger` dataclass
- `AnimationTiming.begin` widened to structured trigger(s)

## 5. Compatibility and Migration

- Existing tests expecting numeric begin behavior should remain valid.
- New parser behavior must keep legacy behavior for plain time offsets.
- New fields must be optional for deserialization compatibility.

## 6. Test Plan

### Unit

- parser begin expression parsing matrix
- begin trigger coercion and fallback warnings
- `mpath` reference lookup and miss behavior
- rotate-auto tangent conversion helpers
- policy local suppression behavior

### Integration

- SVG fixtures combining `begin` references + motion
- mixed-supported/unsupported animations on one slide
- assertion that `p:timing` remains when at least one fragment is valid

### Regression

- keep existing animation golden tests green
- update/add golden fragments for new trigger mapping where deterministic

## 7. Exit Criteria

- All new unit/integration tests pass.
- No regression in current animation handler tests.
- W3C run review completed per `docs/specs/animation-w3c-suite-execution-spec.md`.
