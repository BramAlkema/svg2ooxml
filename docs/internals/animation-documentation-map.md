# Animation Documentation Map

- **Status:** Active
- **Date:** 2026-04-18
- **Scope:** where animation decisions, research evidence, runtime SSOTs, and
  task ledgers live after the April 2026 documentation split

## 1. Purpose

Animation work now spans two repos:

- `svg2ooxml` owns conversion behavior
- `openxml-audit` owns empirical PPTX evidence and lab tooling

This note says where to put new documentation so converter policy, research
evidence, and execution tracking do not collapse back into one pile.

## 2. Ownership Rules

### 2.1 `svg2ooxml` owns converter policy and runtime behavior

Use `svg2ooxml` docs when the question is:

- what should the exporter emit?
- what semantics do we claim to support?
- what policy decides between exact/composed/mimic/fallback?
- what implementation slice or blocker is left?

This repo also owns emitted-side SSOTs consumed by runtime code, such as
`src/svg2ooxml/assets/animation_oracle/`.

### 2.2 `openxml-audit` owns empirical PPTX research

Use `openxml-audit` docs when the question is:

- what did PowerPoint author or preserve on save?
- what XML shapes actually played in slideshow?
- what fixture corpus or probe deck proved that?
- what tooling extracts, diffs, or snapshots PPTX evidence?

## 3. Bucket A — Converter Policy / Specs (`svg2ooxml`)

These docs define intended converter behavior.

- `docs/internals/animation-system.md`
  Implemented architecture and subsystem boundaries.
- `docs/specs/svg-animation-native-mapping-spec.md`
  Match taxonomy and SVG/SMIL -> PresentationML mapping table.
- `docs/specs/animation-cleanup-rigour-spec.md`
  Structural cleanup contract, evidence discipline, and `NativeFragment`
  direction.
- `docs/specs/animation-smil-parity-spec.md`
  SMIL parity requirements and constraints.
- `docs/specs/animation-w3c-suite-execution-spec.md`
  W3C gate commands, review rubric, and reporting rules.
- `docs/specs/display-visibility-animation-spec.md`
  Visibility/display compilation rules.
- `docs/specs/animation-use-composition-spec.md`
  Animated `<use>` composition semantics.
- `docs/specs/animation-fidelity.md`
  Known runtime fidelity gaps and how they are classified.
- `docs/specs/powerpoint-fidelity-phase-2.md`
  Broader fidelity program framing for PowerPoint runtime quality.

## 4. Bucket B — Execution / Task Ledger (`svg2ooxml`)

These docs track work slices, blockers, and rollout order.

- `docs/tasks/animation-smil-parity-tasks.md`
- `docs/tasks/display-visibility-animation-tasks.md`
- `docs/tasks/animation_upgrade_plan.md`
- `docs/tasks/animation-writer-refactoring-tasks.md`
- `docs/tasks/effectdag-native-effects-implementation-plan.md`
- `docs/tasks/powerpoint-fidelity-phase-2-slices.md`
- `docs/tasks/powerpoint-fidelity-phase-2-tasks.md`
- `docs/tasks/powerpoint-fidelity-slice-1-animation-runtime-baseline.md`
- `docs/tasks/powerpoint-fidelity-slice-2-authored-scale-opacity.md`
- `docs/tasks/animation-w3c-sample-blocker-matrix.md`
  Current blocker ledger for the deterministic W3C animation sample.
- `docs/tasks/animation-w3c-baseline-review-2026-02-21.md`
  Frozen baseline review for the earlier gate run.

## 5. Bucket C — Research Evidence (`openxml-audit`)

These docs preserve empirical PowerPoint research and oracle ownership.

- sibling `openxml-audit/docs/pptx_oracle/README.md`
  Research index and corpus entrypoint.
- sibling `openxml-audit/docs/pptx_oracle/ssot.md`
  XML-first methodology and artifact policy.
- sibling `openxml-audit/docs/pptx_oracle/animation-oracle-empirical-findings.md`
  Concrete runtime findings from the April 2026 oracle pass.
- sibling `openxml-audit/docs/pptx_oracle/powerpoint-animation-msft-source-map.md`
  Official Microsoft docs that are useful, and the gaps they leave.
- sibling `openxml-audit/docs/pptx_oracle/powerpoint-obscure-animation-backlog.md`
  Open empirical backlog for PowerPoint-authored edge cases.
- sibling `openxml-audit/docs/pptx_oracle/cloudpresentationpack.md`
- sibling `openxml-audit/docs/pptx_oracle/examples-pptx.md`
- sibling `openxml-audit/docs/pptx_oracle/powerpoint-sample-selected.md`
  Curated corpus notes for specific fixture families.

## 6. Runtime SSOTs (`svg2ooxml`)

These are not research notes. They are shipped converter inputs.

- `src/svg2ooxml/assets/animation_oracle/index.json`
- `src/svg2ooxml/assets/animation_oracle/dead_paths.xml`
- `src/svg2ooxml/assets/animation_oracle/attrname_vocabulary.xml`
- `src/svg2ooxml/assets/animation_oracle/filter_vocabulary.xml`
- `src/svg2ooxml/assets/animation_oracle/README.md`

They may cite evidence from `openxml-audit`, but they stay here because runtime
code consumes them directly.

## 7. Placement Rules For New Docs

1. If the doc changes shipping converter behavior, put it in `svg2ooxml/docs/specs/`.
2. If it tracks execution order, blockers, or rollout slices, put it in
   `svg2ooxml/docs/tasks/` or an explicit ledger note.
3. If it records what PowerPoint authored, preserved, or played, put it in
   `openxml-audit/docs/pptx_oracle/`.
4. If it is a runtime vocabulary/template/dead-path catalog consumed by code,
   keep it under `src/svg2ooxml/assets/animation_oracle/`.
5. Do not use scratch deck paths as durable references in converter docs.
   Promote the evidence into `openxml-audit` first, then cite it from here.
