# Animation Cleanup Rigour Specification

- **Status:** Draft
- **Date:** 2026-04-18
- **Scope:** rigorous cleanup of the animation stack, empirical tooling, oracle workflow, and native-emission architecture
- **Primary Modules:**
  - `src/svg2ooxml/core/animation/parser.py`
  - `src/svg2ooxml/core/animation/timing_parser.py`
  - `src/svg2ooxml/core/export/animation_processor.py`
  - `src/svg2ooxml/drawingml/animation/writer.py`
  - `src/svg2ooxml/drawingml/animation/oracle.py`
  - `src/svg2ooxml/drawingml/animation/xml_builders.py`
  - `src/svg2ooxml/drawingml/animation/handlers/`
  - `src/svg2ooxml/drawingml/animation/visibility_compiler.py`
  - canonical lab ownership in `openxml-audit` via `openxml_audit.pptx.lab`
  - local compatibility entrypoint: `tools/visual/pptx_lab.py`
- **Related docs:**
  - `docs/internals/animation-documentation-map.md`
  - `docs/specs/svg-animation-native-mapping-spec.md`
  - `docs/specs/animation-smil-parity-spec.md`
  - `docs/specs/animation-w3c-suite-execution-spec.md`
  - `docs/specs/powerpoint-fidelity-phase-2.md`
  - sibling `openxml-audit/docs/pptx_oracle/ssot.md`
  - `docs/tasks/animation-w3c-sample-blocker-matrix.md`

## 1. Purpose

At this point the animation docs are structurally in a much better place. The
next cleanup is editorial rather than structural.

The project is no longer blocked on "can we emit a valid PPTX at all."

The current problem is discipline:

1. research tooling exists, but the entrypoints were fragmented
2. native mappings exist, but their evidence tiers are mixed
3. handlers increasingly need extra metadata and container surgery
4. PowerPoint-authored XML templates are valuable, but not yet a formal part of
   the emission architecture
5. W3C export success is green, but closure of the remaining animation gap is
   still tracked informally across specs, notes, and scratch artifacts

This spec defines the cleanup contract that turns the animation subsystem from
"active research code that mostly works" into "a controlled system with
explicit layers, evidence, and release gates."

This document owns structural cleanup only: planning/emission boundaries,
evidence discipline, template promotion, and empirical-tooling ownership. It
does not restate the broader fidelity program from
`docs/specs/powerpoint-fidelity-phase-2.md` or the durable decisions recorded
in `docs/adr/README.md`.

## 2. Goals

1. Make semantic ownership explicit from SMIL parse through PowerPoint timing
   emission.
2. Require evidence tiers for every native mapping claim.
3. Put empirical PowerPoint research on an XML-first footing instead of a
   scratch-deck footing.
4. Consolidate visual, diff, roundtrip, and oracle workflows behind one lab
   entrypoint.
5. Introduce a first-class planning layer for native effects before further
   growth in handler complexity.
6. Make the remaining closure work reviewable by blocker family, not by vague
   "animation progress."

## 3. Non-Goals

- Full browser runtime emulation inside PowerPoint.
- Elimination of all research code in one pass.
- Rewriting the parser or IR unless cleanup demands a boundary change.
- Replacing the native mapping spec or the W3C blocker matrix.

This spec is about discipline and architecture, not a restart.

## 4. Current Problems

### 4.1 Research and production boundaries are blurred

The current codebase contains real exporter logic, research decks, visual
probes, roundtrip tools, and oracle extraction logic, but they have not all
been organized under one operational contract.

That makes it too easy to:

- treat a one-off probe result as a stable mapping
- rely on a hand-authored XML guess without preserving evidence
- patch one handler around an edge case while making container semantics less
  coherent overall

### 4.2 Evidence is present, but not mandatory

We now know at least four materially different truth surfaces exist:

1. ECMA-valid XML
2. PowerPoint-loadable XML
3. PowerPoint roundtrip-preserved XML
4. PowerPoint slideshow-verified behavior

The project already reasons this way informally. The cleanup now needs to make
that distinction mandatory in code review, mapping classification, and template
promotion.

### 4.3 Handler complexity is growing in the wrong place

Handlers currently do more than "map one semantic animation family to one
native family." They are also starting to encode:

- outer container shape
- start/end condition placement
- build-list concerns
- setup `<p:set>` requirements
- special runtime grouping decisions

That is the point where raw handler return values stop being an adequate
abstraction.

### 4.4 XML SSOT templates are under-formalized

For simple stable primitives, hand-built XML is fine.

For obscure or PowerPoint-sensitive structures, the safest source is still
PowerPoint-authored XML that has been extracted, normalized, and classified.

The project already discovered this empirically. The cleanup must turn that
into a rule instead of leaving it as an implementation preference.

## 5. Target Architecture

The cleaned-up animation stack must be organized into five layers.

### 5.1 Semantic Layer

Inputs:

- parsed SVG/SMIL structure
- resolved timing expressions
- resolved style/attribute targets

Outputs:

- semantic IR only

Responsibilities:

- preserve SMIL meaning
- do not make native claims
- do not encode PowerPoint container quirks

The semantic layer remains the source of truth for what the SVG asked for.

### 5.2 Composition Layer

Inputs:

- semantic IR
- resolved base values
- inheritance and `<use>` propagation state
- visibility/display compilation state

Outputs:

- composed animation requests whose values and timing are concrete enough for
  native planning

Responsibilities:

- resolve `from` / `to` / `by` and additive/accumulate interactions where
  feasible
- segment discrete and sampled timing where required
- lower structural visibility concerns into executable target intervals

The composition layer owns semantic preprocessing. Handlers should not each
re-solve these problems ad hoc.

### 5.3 Native Planning Layer

This layer must be introduced explicitly.

The required abstraction is a first-class `NativeFragment` plan.

A `NativeFragment` represents one reviewable native emission unit, with fields
such as:

- semantic source animation(s)
- target element(s)
- native family (`anim`, `animMotion`, `animScale`, `animRot`, `animClr`,
  `set`, `animEffect`, or explicit unsupported/mimic/fallback)
- required setup fragments
- required container semantics
- build-list participation
- evidence tier
- oracle/template provenance if applicable
- degradation reason if not exact/composed-native

Rules:

1. handlers return plans or plan fragments, not direct slide XML surgery
2. handlers do not directly mutate outer timing containers
3. handlers do not smuggle wrapper semantics through incidental builder calls
4. container-level concerns are applied centrally by the writer/planner

If a native mapping requires extra metadata or outer-container surgery, that is
not a reason to keep bolting fields onto handler return values. That is
precisely the reason to promote the abstraction to a first-class layer.

### 5.4 Template Layer

The template layer defines how native fragments are materialized into concrete
PowerPoint XML.

Two sources are allowed:

1. stable hand-built generic templates for well-understood primitives
2. PowerPoint-authored XML templates for sensitive or obscure structures

Rules:

- simple generic primitives may continue to be emitted through code builders
- any structure whose correctness depends on authored wrapper shape, grouping,
  pane behavior, or roundtrip stability should prefer an oracle-backed template
- template provenance must be recorded

This is where the project should rely on XML SSOT templates more, not less.
The point is not "everything must become a pasted XML blob." The point is that
obscure authored structures should be mined from PowerPoint and promoted
deliberately instead of re-guessed in code every time.

### 5.5 Emission Layer

The writer remains responsible for:

- assembling timing trees
- assigning IDs
- placing start and end conditions
- applying repeat/restart/fill on the correct container node
- producing final slide XML

The writer should consume planned fragments and templates, not infer semantic
intent from low-level element shape.

## 6. Evidence Model

Every native mapping and every promoted template must carry an evidence tier.

### 6.1 Required tiers

| Tier | Meaning | Allowed use |
| --- | --- | --- |
| `schema-valid` | ECMA-valid or hand-authored XML only | research, not promotion |
| `loadable` | PowerPoint opens without repair | weak candidate |
| `roundtrip-preserved` | PowerPoint save-roundtrip preserves the intended structure materially intact | promotable candidate |
| `slideshow-verified` | slideshow behavior has been observed and matches the intended claim closely enough | required for runtime claims |
| `ui-authored` | structure came from PowerPoint-authored or PowerPoint-roundtripped XML | preferred template source |

These are not mutually exclusive labels. A mature native template should
normally be at least:

- `ui-authored`
- `roundtrip-preserved`
- `slideshow-verified`

### 6.2 Promotion rules

1. A mapping cannot be called `exact-native` or `composed-native` without
   slideshow evidence or a strong oracle-backed precedent that is already
   slideshow-verified.
2. A mapping cannot become a reusable template based only on schema legality.
3. A failed roundtrip strips a structure of template-candidate status.
4. A behavior that is loadable but inert must be classified as dead,
   unsupported, or mimic-only.

## 7. Oracle and Empirical Tooling Contract

Canonical empirical-lab ownership now lives in `openxml-audit` under
`openxml_audit.pptx.lab` (also exposed as `openxml-audit-pptx-lab`).
`tools/visual/pptx_lab.py` remains a local compatibility entrypoint while this
repo sheds empirical tooling. The lab front door covers:

- oracle extraction
- package diffing
- PowerPoint roundtrip save
- forwarded PowerPoint capture
- forwarded LibreOffice roundtrip

That tool is the operational shell for empirical work. New visual or roundtrip
flows should be added there, or clearly justified as separate.

The oracle contract remains XML-first:

1. temporary `.pptx` decks are for authoring and replay
2. extracted raw XML is the durable source
3. normalized XML is for diffing and mining
4. human notes are commentary

Any new probe result worth keeping should be reducible to:

- raw slide XML or raw timing XML
- normalized timing XML
- manifest metadata
- evidence tier
- concise behavior notes

## 8. Documentation Contract

The docs set must be split by responsibility.

### 8.1 Specs

Specs define intended architecture, rules, and release gates.

Examples:

- native mapping rules
- cleanup architecture
- W3C execution gates

### 8.2 Research notes

Research notes preserve findings, uncertainty, and raw observations.

Examples:

- oracle SSOT note in `openxml-audit/docs/pptx_oracle/ssot.md`
- PowerPoint probe findings

### 8.3 Ledgers and blockers

Ledgers track concrete unfinished closure work.

Examples:

- W3C blocker matrix
- dead-or-mimic target lists
- evidence gaps by feature family

### 8.4 Tasks

Tasks are execution slices, not architecture.

A cleanup is complete when work moves from task note to ledger closure to spec
conformance.

## 9. Cleanup Workstreams

### W1. Freeze the current baseline

Required artifacts:

- current W3C animation export report
- current blocker matrix
- current oracle corpus notes
- current `openxml-audit-pptx-lab` / `pptx_lab` help surface

This prevents "cleanup" from becoming a moving target.

### W2. Classify every current mapping by evidence

For each native family in the mapping spec:

- record its evidence tier
- record whether it is template-backed, builder-backed, or policy-only
- mark dead, mimic, exact, composed, expand, or unsupported explicitly

Unclassified mappings are not considered closed.

### W3. Introduce `NativeFragment`

This is the main structural cleanup.

Required outcomes:

- handlers stop returning raw ad hoc XML bundles as the primary contract
- outer container semantics become central writer/planner logic
- setup `<p:set>` emissions, build-list participation, and condition placement
  become explicit plan data

### W4. Split generic builders from oracle-backed templates

Required outcomes:

- generic builder functions remain for stable primitives
- PowerPoint-sensitive structures gain template-backed emitters with provenance
- code review can tell which emitters are generic vs oracle-backed

### W5. Retire duplicate empirical entrypoints

Required outcomes:

- `openxml-audit-pptx-lab` is the documented front door
- older scripts may remain, but only as implementation modules or thin wrappers
- documentation examples stop pointing to scattered ad hoc scripts by default

### W6. Turn blocker families into owned closure slices

The blocker matrix already groups the main unfinished work:

- timing interpolation
- composition solver
- attribute propagation
- dead-or-mimic targets
- geometry morph
- unsupported runtime semantics

Cleanup requires each family to have:

- a semantic owner
- a template/evidence plan
- explicit exit criteria

## 10. Release Gates

The cleaned-up system is not done when the code merely "looks cleaner."

It is done when all of the following are true:

1. `openxml-audit-pptx-lab` is the documented front door for empirical
   animation work.
2. Native mappings have evidence tiers recorded.
3. New obscure emitters are either oracle-backed or explicitly marked
   speculative.
4. Handler contracts no longer require ad hoc outer-container surgery.
5. W3C animation export gates remain green.
6. The blocker matrix is updated by feature-family movement, not by vague prose.
7. Roundtrip and slideshow evidence are attached to any new runtime claim.

## 11. Exit Criteria

This cleanup spec is satisfied when:

1. a first-class native planning layer exists
2. template provenance is explicit
3. evidence tiers are enforced in review and docs
4. empirical tooling has one front door
5. blocker-family closure is tracked systematically
6. the remaining unsupported space is explicit rather than accidental

At that point the project is still not "finished," but it is on a sound
footing again: semantic IR on one side, empirical PowerPoint truth on the
other, and a disciplined planning/emission layer in between.
