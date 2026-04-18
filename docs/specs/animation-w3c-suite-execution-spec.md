# Animation W3C Suite Execution Specification

- **Status:** Draft
- **Date:** 2026-02-21
- **ADR:** `docs/adr/README.md` (`SMIL Parity & W3C Gating`)
- **Documentation map:** `docs/internals/animation-documentation-map.md`
- **Scope:** corpus and visual W3C validation for animation-related work

## 1. Purpose

Define a repeatable command set and review rubric for validating animation
changes against W3C fixtures using repository-native tooling.

## 2. Command Profiles

### Profile A: Corpus Category Smoke (required per PR)

Runs representative non-animation categories to detect regressions in shared
parser/writer behavior.

```bash
./tests/corpus/run_w3c_corpus.sh gradients --mode resvg
./tests/corpus/run_w3c_corpus.sh shapes --mode resvg
```

Artifacts:
- `tests/corpus/w3c/report_gradients.json`
- `tests/corpus/w3c/report_shapes.json`

### Profile B: Animation-Focused Corpus Sample (required per animation PR)

Generate metadata from `animate*` fixtures and run a deterministic sample.

```bash
python tests/corpus/add_w3c_corpus.py \
  --category animate \
  --limit 40 \
  --output tests/corpus/w3c/w3c_animation_metadata.json

python tests/corpus/run_corpus.py \
  --corpus-dir tests/svg \
  --metadata tests/corpus/w3c/w3c_animation_metadata.json \
  --output-dir tests/corpus/w3c/output_animation \
  --report tests/corpus/w3c/report_animation.json \
  --mode resvg \
  --sample-size 20 \
  --sample-seed 20260221
```

Artifacts:
- `tests/corpus/w3c/report_animation.json`
- `docs/tasks/animation-w3c-sample-blocker-matrix.md`

### Profile C: Curated Visual W3C Diff (optional, pre-release)

```bash
python -m tools.visual.w3c_suite struct-use-10-f styling-css-01-b
```

This remains optional because curated suite is not animation-heavy by default.

## 3. Pass/Fail Criteria

For each required profile:

1. `failed_decks == 0`
2. no hard parser exceptions in summary/error fields
3. native/emf/raster rates are within metadata thresholds for the sampled set
4. report files are attached to PR or release note

### 3.1. Fidelity Caveat

Passing Profile B does **not** mean the sampled W3C animations are semantically
closed. The current profile is still an export-validity gate first.

Reviewers must pair the report with the current blocker ledger in
`docs/tasks/animation-w3c-sample-blocker-matrix.md` and distinguish:

- native-baseline control decks
- known fidelity blockers being actively worked
- explicit unsupported PowerPoint-runtime semantics

## 4. Review Checklist

1. Confirm command lines and seed values used.
2. Compare summary metrics with previous baseline run.
3. Inspect per-deck failures and group by root cause:
   - parse failure
   - mapping failure
   - timing generation failure
   - policy suppression
4. For decks without hard failures, still map them to the blocker matrix and
   note whether they are:
   - native-baseline controls
   - exact/composed-native work remaining
   - mimic/fallback work remaining
   - explicit unsupported runtime semantics
5. Identify whether failures or blocker movements are known, new, or expected
   deltas.
6. Document follow-up fixes with file-level ownership.

## 5. Reporting Template

Use this structure in PR/release notes:

- `run_date`
- `git_sha`
- `profiles_executed`
- `decks_total`
- `decks_failed`
- `known_failures`
- `new_failures`
- `action_items`

## 6. Automation Guidance

- CI should run Profile A on every PR touching parser, drawingml, or policy.
- CI should run Profile B for PRs touching `src/svg2ooxml/core/animation/` or
  `src/svg2ooxml/drawingml/animation/`.
- Fail builds when required profile reports missing or have failed decks.
