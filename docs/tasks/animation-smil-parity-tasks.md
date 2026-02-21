# Animation SMIL Parity - Implementation Tasks

**ADR**: `docs/adr/ADR-027-animation-smil-parity-and-w3c-gating.md`  
**Specs**:
- `docs/specs/animation-smil-parity-spec.md`
- `docs/specs/animation-w3c-suite-execution-spec.md`

## Phase 1: IR and Parser Semantics

### Task 1.1 - Begin Trigger IR
- [x] Add begin trigger datatypes to `src/svg2ooxml/ir/animation.py`
- [x] Keep compatibility for numeric begin values
- [x] Add/extend tests in `tests/unit/ir/test_ir_animation.py`

### Task 1.2 - Parse Begin Expressions
- [x] Parse `click`, `id.begin`, `id.end`, and signed offsets in `src/svg2ooxml/core/animation/parser.py`
- [x] Emit warnings for invalid begin expressions
- [x] Add parser tests in `tests/unit/core/animation/test_smil_parser.py`

### Task 1.3 - Resolve `mpath` References
- [x] Resolve `<mpath href>` to referenced path definitions in parser
- [x] Warn and degrade fragment if reference missing
- [x] Add tests for resolved and unresolved cases

## Phase 2: Writer and Motion Behavior

### Task 2.1 - Policy Local Degradation
- [x] Refactor suppression behavior in `src/svg2ooxml/drawingml/animation/policy.py`
- [x] Keep supported fragments in timing tree
- [x] Add tests in `tests/unit/drawingml/animation/test_policy.py`

### Task 2.2 - Rotate Auto Approximation
- [x] Add tangent-based rotation approximation in `src/svg2ooxml/drawingml/animation/handlers/motion.py`
- [x] Gate via policy option
- [x] Add handler tests in `tests/unit/drawingml/animation/handlers/test_motion.py`

### Task 2.3 - Begin Trigger Mapping in XML
- [x] Map trigger IR into timing conditions via XML builder/writer
- [x] Validate output shape with integration tests in `tests/unit/core/test_pptx_exporter_animation.py`

## Phase 3: Validation and Gating

### Task 3.1 - Required W3C Profiles
- [x] Run corpus Profile A (gradients + shapes)
- [x] Run corpus Profile B (animation sample)
- [x] Archive resulting report JSON artifacts

### Task 3.2 - Review and Follow-Ups
- [x] Categorize failures by parser/writer/policy buckets
- [x] Create fix issues for new failures
- [x] Track pass-rate trends over time

## Execution Notes

- Prefer deterministic seeds for repeatability.
- For animation PRs, Profile B is mandatory.
- Do not merge if required profiles report failed decks unless explicitly waived.
