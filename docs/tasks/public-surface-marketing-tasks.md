# Public Surface Marketing - Task Plan

**Spec**: [docs/specs/public-surface-marketing-spec.md](../specs/public-surface-marketing-spec.md)
**Primary Repo**: `svg2ooxml`
**Companion Repo**: `openxml-audit`

## Objective

Turn the marketing/public-surface spec into concrete execution work so that:

1. `svg2ooxml` is clearly packaged as the converter/runtime product
2. `openxml-audit` is clearly packaged as the proof/validation companion
3. GitHub, PyPI, docs, releases, and the website tell the same story
4. evidence becomes consumable proof assets instead of buried internal context
5. commercial and evaluator paths become explicit

## Workstream Overview

### WS1: Metadata And Discovery Hygiene

Goal:
- make GitHub and PyPI legible before a user reads deep docs

### WS2: Docs And Website Consistency

Goal:
- make the package, docs, roadmap, and static site route users correctly by
  intent

### WS3: Proof Packaging

Goal:
- expose validation and PowerPoint-runtime evidence in formats evaluators can
  consume quickly

### WS4: Commercial And Adoption Surface

Goal:
- make licensing, support-sensitive usage, and evaluation paths clear without
  turning the repo into a sales site

### WS5: Release Narrative Discipline

Goal:
- make releases readable to outsiders and keep public claims evidence-backed

## Repo Ownership Split

### svg2ooxml owns

- converter-facing README/PyPI/website copy
- docs landing and routing
- converter release notes
- licensing/commercial page
- acquisition pages for conversion use cases

### openxml-audit owns

- durable proof pages
- validation benchmarks and parity summaries
- authored control-deck evidence when those are used as trust assets
- research-backed proof artifacts linked from `svg2ooxml`

## Phase 1: Lock Metadata And Entry Points

### Task 1.1 - Fill GitHub About Metadata
- [ ] set `svg2ooxml` GitHub description to a crisp converter one-liner
- [ ] set `svg2ooxml` website link to the public docs/site landing page
- [ ] add discovery topics:
  - `svg`
  - `pptx`
  - `powerpoint`
  - `drawingml`
  - `openxml`
  - `presentationml`
  - `python`
- [ ] verify `openxml-audit` metadata still reflects the proof/validation role

### Task 1.2 - Normalize PyPI Metadata
- [ ] keep `pyproject.toml` description aligned with README/PyPI copy
- [ ] keep project URLs populated and current
- [ ] verify PyPI README points to:
  - docs landing
  - testing guide
  - `openxml-audit`
- [ ] remove stale product wording from PyPI release-facing copy

### Task 1.3 - Keep README / Docs Entry Cohesive
- [ ] keep `README.md` start-here links stable
- [ ] keep `docs/README.md` as the docs routing page
- [ ] ensure `README.md` explains the `svg2ooxml` / `openxml-audit` split
  within the first two screens

### Acceptance Criteria
- [ ] a new visitor can identify the product and companion repo in under
      60 seconds
- [ ] GitHub, PyPI, and root README use the same one-line positioning
- [ ] no stale Google-Slides-as-primary-product wording remains on primary
      package surfaces

## Phase 2: Unify Docs And Website Story

### Task 2.1 - Keep Docs Landing Clean
- [ ] maintain `docs/README.md` as the canonical docs entrypoint
- [ ] link from docs landing to:
  - testing guide
  - roadmap
  - ADRs
  - animation documentation map
  - licensing
- [ ] keep routing language intent-based rather than folder-jargon-first

### Task 2.2 - Keep Static Website Minimal And Honest
- [ ] maintain `docs/website/index.html` as a lightweight project front door
- [ ] keep website wording aligned with package reality, not a speculative SaaS
  pitch
- [ ] ensure website links work when opened locally and when hosted
- [ ] ensure legal pages use current, integration-agnostic language

### Task 2.3 - Add A Public Docs Site Plan
- [ ] decide whether `svg2ooxml` gets a GitHub Pages docs site or continues to
      use repo-native docs links
- [ ] if Pages is chosen, define:
  - landing page
  - primary nav
  - docs sync strategy
  - ownership
- [ ] keep this separate from `openxml-audit` docs branding

### Acceptance Criteria
- [ ] website, docs landing, and roadmap all reflect the same converter-first
      story
- [ ] legal pages no longer read like a Firebase/Google-Slides-only product
- [ ] users can reach install, docs, and proof links from the website in one
      click

## Phase 3: Package Proof As Marketing Assets

### Task 3.1 - Create A Trust Page
- [ ] add a converter-side trust/proof page in `svg2ooxml` docs
- [ ] explain:
  - editable output
  - OpenXML validation
  - slideshow/runtime verification
  - the role of `openxml-audit`
- [ ] keep the durable proof assets themselves in `openxml-audit` where
      appropriate

### Task 3.2 - Build Before / After / Editable Gallery
- [ ] select 3-5 representative examples:
  - simple vector conversion
  - text-heavy example
  - filter-heavy example
  - animation example
- [ ] produce assets showing:
  - source SVG
  - generated slide
  - editability in PowerPoint
- [ ] publish as a docs page or website section

### Task 3.3 - Produce A Short Demo Video
- [ ] record a short clip showing:
  - input SVG
  - conversion
  - output PPTX in PowerPoint
  - one edit applied to prove editability
- [ ] keep raw source project files so the video is reproducible

### Task 3.4 - Publish A Proof Summary
- [ ] decide which metrics are stable enough for public use:
  - validation counts
  - benchmark numbers
  - proof-deck coverage
  - runtime verification coverage
- [ ] link each published metric to a reproducible source path
- [ ] keep `openxml-audit` as the canonical source for validator/parity claims

### Acceptance Criteria
- [ ] the project can answer "why trust this?" without requiring a deep repo
      dive
- [ ] at least one proof asset exists for static output and one for animation
- [ ] public numeric claims all have a traceable evidence home

## Phase 4: Commercial And Evaluation Surface

### Task 4.1 - Write A Licensing / Commercial Page
- [ ] add a public page explaining:
  - AGPL usage
  - when commercial terms are relevant
  - who typically needs commercial licensing
  - how to contact for evaluation
- [ ] link this page from:
  - README
  - website
  - PyPI project URLs if appropriate

### Task 4.2 - Add Use-Case Framing
- [ ] write concise evaluator-facing examples:
  - proprietary internal automation
  - SaaS embedding
  - design export workflows
  - CI validation-backed generation pipelines
- [ ] keep these grounded in real package capabilities

### Task 4.3 - Define Intake Path
- [ ] decide whether evaluation/support traffic should go to:
  - email
  - GitHub Discussions
  - GitHub Issues
  - a separate contact path
- [ ] document the path consistently on public surfaces

### Acceptance Criteria
- [ ] a commercial evaluator can self-qualify without guessing
- [ ] the licensing path is visible but not pushy
- [ ] support/evaluation contact routing is unambiguous

## Phase 5: Normalize Release Narrative

### Task 5.1 - Create Release Note Template
- [ ] define a release template with:
  - release focus
  - user-visible impact
  - proof or validation implications
  - links to docs/tasks where relevant
- [ ] use it for future `CHANGELOG.md` entries

### Task 5.2 - Backfill Recent Releases
- [ ] normalize recent release sections so they read as release notes rather
      than raw work logs
- [ ] keep deep implementation detail available, but subordinate it to user
      impact

### Task 5.3 - Keep Claims Within Evidence Policy
- [ ] audit README, PyPI, roadmap, website, and changelog for:
  - stale counts
  - unsupported "only/best" claims
  - repo-boundary confusion
  - integration drift
- [ ] create a lightweight pre-release check against the marketing spec

### Acceptance Criteria
- [ ] release notes remain readable to outsiders
- [ ] user-facing surfaces do not drift into unsupported claims
- [ ] the current release story is about converter behavior, with proof linked
      rather than implied

## Phase 6: Acquisition Pages

### Task 6.1 - SVG To PowerPoint Page
- [ ] create a page targeted at the core search/use-case intent
- [ ] include:
  - what it does
  - install path
  - proof/trust links
  - editable output examples

### Task 6.2 - Figma To PowerPoint Page
- [ ] create a page for browser/plugin workflow intent
- [ ] explain current scope without overselling the integration surface

### Task 6.3 - Validate PPTX/DOCX/XLSX In Python Page
- [ ] route this primarily to `openxml-audit`
- [ ] keep the relationship explicit:
  - `svg2ooxml` generates
  - `openxml-audit` validates

### Acceptance Criteria
- [ ] the project has at least three intent-driven pages
- [ ] each page has one clear call to action
- [ ] no page blurs the repo boundary

## Validation Checklist

### Required for public-surface changes
- [ ] all touched links resolve locally or in the intended hosted environment
- [ ] README, PyPI README, website, and roadmap use consistent one-line
      positioning
- [ ] `svg2ooxml` / `openxml-audit` ownership is explicit where relevant
- [ ] any new numeric claim has a reproducible evidence source

### Required for proof-asset publication
- [ ] source files and generation path are retained
- [ ] asset is reproducible from repo state or companion-repo state
- [ ] public caption text does not over-claim beyond the evidence

### Required per release
- [ ] changelog entry uses the normalized release template
- [ ] release-facing copy is audited against the marketing spec
- [ ] stale metrics are updated or removed

## Recommended Execution Order

1. Phase 1: metadata and entry points
2. Phase 2: docs and website consistency
3. Phase 5: release narrative normalization
4. Phase 3: proof packaging
5. Phase 4: commercial/evaluation surface
6. Phase 6: acquisition pages

This order improves discoverability first, then trust, then distribution.
