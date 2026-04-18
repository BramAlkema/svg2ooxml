# Public Surface Marketing Specification

- **Status:** Draft
- **Date:** 2026-04-18
- **Scope:** public-facing positioning, documentation entrypoints, release
  narrative, proof assets, and commercial funnel for `svg2ooxml`, with explicit
  boundary handling against `openxml-audit`
- **Primary Surfaces:**
  - `README.md`
  - `README.pypi.md`
  - `pyproject.toml`
  - `CHANGELOG.md`
  - `docs/README.md`
  - `docs/ROADMAP.md`
  - `docs/website/`
  - GitHub repo metadata (`About`, topics, social preview, website link)
  - PyPI metadata and project links
- **Related repos:**
  - `svg2ooxml`
  - `openxml-audit`
- **Related docs:**
  - `docs/licensing.md`
  - `docs/testing.md`
  - `docs/internals/animation-documentation-map.md`
  - sibling `openxml-audit` public docs site

## 1. Purpose

`svg2ooxml` now has enough substance to support a serious public story.

The problem is no longer "do we have anything worth saying?"

The problem is that the public surfaces do not yet package the work clearly
enough for an outside user to understand:

1. what the product is
2. why it is credible
3. how it differs from the validation/research work in `openxml-audit`
4. where to start
5. when to trust a claim
6. how to buy, adopt, evaluate, or contribute

This spec defines the marketing and public-surface contract for the converter
repo. It treats marketing as product packaging, proof distribution, and
discovery hygiene rather than as copy-first promotion.

## 2. Current Problem

The current public narrative is stronger than it was, but still incomplete.

### 2.1 Substance exists, packaging lags

The project has:

- a publishable PyPI package
- a technically strong README
- a clearer docs landing path
- meaningful release notes
- a companion research/validation repo (`openxml-audit`)
- strong proof material around validation and PowerPoint behavior

But those assets are not yet distributed through the most important public
surfaces with consistent language.

### 2.2 Public product boundaries are still easy to confuse

Without an explicit split, outside readers cannot reliably tell which repo owns:

- conversion/runtime behavior
- validation/proof behavior
- empirical PowerPoint research
- authored control decks
- package-facing release notes

This confusion weakens both repos:

- `svg2ooxml` looks more research-heavy than product-ready
- `openxml-audit` looks like an implementation detail instead of a trust engine

### 2.3 Evidence is a strength, but it is not yet productized

The project has something many conversion libraries do not:

- OpenXML validation
- visual proof decks
- PowerPoint playback verification
- authored XML roundtrip work

That is a marketing asset, but only if it is exposed in a form outsiders can
consume quickly.

### 2.4 Some external surfaces are lower quality than the repo now deserves

Observed on 2026-04-18:

- `svg2ooxml` GitHub lacked an `About` description / website / topics
- public `svg2ooxml` PyPI metadata still reflected older wording
- website/legal pages were carrying older integration-specific language
- `openxml-audit` already had a more mature docs and project-links story

This spec assumes those kinds of gaps will keep reappearing unless the project
defines explicit ownership for public surfaces.

## 3. Goals

1. Give `svg2ooxml` a crisp external identity as the converter/runtime package.
2. Use `openxml-audit` as the trust and proof companion, not as a hidden side
   project.
3. Make the public story legible across GitHub, PyPI, docs, releases, and the
   static website.
4. Turn evidence into consumable proof assets instead of leaving it buried in
   internal tooling and notes.
5. Create a clearer commercial path without weakening the open-source story.
6. Make future public-copy drift harder by defining one canonical messaging
   hierarchy.

## 4. Non-Goals

- A full visual rebrand.
- Paid ad campaigns.
- Vanity social posting as a substitute for documentation and proof.
- Invented customer claims, fabricated metrics, or synthetic testimonials.
- A generic SaaS marketing site detached from the package/repo reality.
- Mixing `svg2ooxml` and `openxml-audit` into one brand surface.

This spec is about accurate product packaging, not hype.

## 5. Product Split

The public model must be simple and repeated everywhere.

### 5.1 svg2ooxml

**One-line position:**

> Convert SVG to editable PowerPoint with native DrawingML output.

**Owns:**

- SVG parsing and conversion
- DrawingML/PresentationML emission
- editable-first fallback behavior
- package distribution
- integration entrypoints
- converter release notes
- converter docs, specs, tasks, and ADRs

### 5.2 openxml-audit

**One-line position:**

> Validate Office files in pure Python and hold the evidence for what works.

**Owns:**

- OOXML and ODF validation
- parity claims against external validators
- authored control decks
- roundtrip-preserved XML evidence
- durable oracle evidence
- validation-facing docs site

### 5.3 Relationship

Publicly, the pairing should be explained as:

- `svg2ooxml` creates files
- `openxml-audit` validates and calibrates trust

That relationship is one of the strongest differentiators the project has.

## 6. Audiences

### 6.1 Primary

Engineers and technical teams who need to generate or convert presentation
files programmatically.

Typical intents:

- "I need SVG to editable PowerPoint"
- "I need PPTX generation in CI"
- "I need something headless"
- "I need to know whether generated Office files will open cleanly"

### 6.2 Secondary

- design-tool export workflows
- AI/agent builders producing Office files
- document/presentation automation teams
- OSS contributors in OpenXML / SVG / validation tooling

### 6.3 Tertiary

- commercial buyers evaluating support or licensing
- technically sophisticated evaluators who need proof before adoption

## 7. Messaging Hierarchy

Every major public surface for `svg2ooxml` should follow this order.

### 7.1 Headline

`SVG to editable PowerPoint`

or

`Convert SVG to PowerPoint with native DrawingML output`

### 7.2 Immediate credibility layer

Within one screen, the surface should establish:

- headless conversion
- editable output
- animation/fidelity emphasis where relevant
- validation-backed trust

### 7.3 Boundary layer

Within two screens, the surface should explain:

- `svg2ooxml` is the converter
- `openxml-audit` is the validation/research companion

### 7.4 Action layer

The user should then be able to do one of:

- install the package
- read docs
- inspect proof
- evaluate licensing/commercial fit

## 8. Evidence Policy For Marketing Claims

The project must not market itself with claims that cannot be defended.

### 8.1 Allowed claim classes

1. **Static product facts**
   - package name
   - language/runtime
   - supported entrypoints
   - existence of docs, CLI, tests, extras

2. **Reproducible technical claims**
   - validation counts
   - benchmark numbers
   - supported feature families
   - documented proof workflows

3. **Comparative claims**
   - only when supported by a reproducible and reviewable basis

### 8.2 Required handling

- Every numeric claim should have a reproducible source path.
- Every "validated" claim should point to the relevant proof path or companion
  repo.
- Every comparative claim should be narrow and defensible, not sweeping.
- If a claim depends on PowerPoint runtime behavior, `openxml-audit` is the
  durable evidence home.

### 8.3 Disallowed claim patterns

- unsupported "best" or "only" language without evidence
- stale counts copied forward after the underlying corpus changes
- pretending research results are package guarantees
- marketing copy that silently shifts between PowerPoint and Google Slides

## 9. Public Surfaces

### 9.1 GitHub Repo Surfaces

`svg2ooxml` GitHub must have:

- clear `About` description
- website/docs URL
- topic tags
- up-to-date social preview
- pinned proof/demo material where useful

Acceptance criteria:

- repo home explains product in one sentence
- repo metadata matches README wording
- topics reflect user-discovery terms, not internal jargon

### 9.2 PyPI

PyPI must present:

- crisp package description
- strong project links
- installation path
- docs path
- trust/proof companion link

Acceptance criteria:

- description matches the current positioning
- project links are populated
- release-facing README is not materially behind GitHub README

### 9.3 Docs Landing

`docs/README.md` is the docs entrypoint.

It must:

- route users by intent
- explain the `svg2ooxml` / `openxml-audit` boundary
- surface testing/proof paths
- keep marketing-lite language grounded in repository reality

### 9.4 Static Website

The static site should function as:

- a lightweight credibility front door
- a stable link target for repo/PyPI metadata
- a minimal legal/commercial surface

It must not become a disconnected marketing site with claims that drift from
the repo.

### 9.5 Release Notes

Release notes should explain:

- release focus
- user-visible impact
- evidence/proof changes where relevant

They should not read like a raw work log.

### 9.6 Licensing / Commercial Surface

The project needs a clear path for:

- open-source adoption
- commercial evaluation
- support/licensing inquiries

This does not require a sales deck. It does require a page that answers:

- who needs commercial terms
- why
- what to do next

## 10. Required Marketing Assets

The following assets should exist or be created.

### 10.1 Must-have

1. **Docs landing page**
2. **Updated README / PyPI parity**
3. **GitHub About metadata**
4. **Static website landing page**
5. **Commercial/licensing explainer page**

### 10.2 High-value proof assets

1. **Short demo video**
   - source SVG
   - generated PPTX
   - editability inside PowerPoint

2. **Before / generated / editable gallery**
   - at least 3 representative cases

3. **Trust page**
   - explain validation and proof workflow
   - explain `svg2ooxml` + `openxml-audit`

4. **Benchmark / proof summary**
   - not every detail
   - enough to support adoption decisions

### 10.3 Acquisition pages

At minimum:

1. `SVG to PowerPoint`
2. `Figma to PowerPoint`
3. `Validate PPTX/DOCX/XLSX in Python`

These are intent pages, not generic marketing filler.

## 11. Commercial Funnel

The project already exposes commercial licensing, but the funnel is too thin.

The minimum acceptable commercial path is:

1. public mention of commercial licensing
2. licensing explainer page
3. clear contact method
4. examples of who typically needs it

The copy should target:

- proprietary internal automation
- SaaS embedding
- enterprise document/presentation workflows
- support-sensitive buyers

## 12. Phase Plan

### Phase 1: Metadata And Entry Points

Deliverables:

- GitHub About descriptions, topics, and website links
- PyPI metadata cleanup
- README / PyPI / docs landing consistency
- website landing page consistency

Success:

- a new visitor can identify the product and where to start within one minute

### Phase 2: Proof Packaging

Deliverables:

- trust page
- before/after/editable gallery
- short demo video
- proof-summary page linking to `openxml-audit`

Success:

- the project can answer "why should I trust this?" without requiring a repo
  deep-dive

### Phase 3: Commercial And Adoption Surface

Deliverables:

- licensing explainer page
- commercial use-case copy
- stronger issue/discussion intake path for evaluators

Success:

- a commercial evaluator can self-qualify without emailing first

### Phase 4: Distribution Content

Deliverables:

- launch-style post for `svg2ooxml`
- launch-style post for `openxml-audit`
- release summary template
- acquisition pages

Success:

- the project has reusable content that compounds discovery instead of one-off
  announcements

## 13. Acceptance Criteria

This spec is satisfied when:

1. `svg2ooxml` and `openxml-audit` have distinct, repeated public one-liners.
2. GitHub, PyPI, docs, and website all tell the same product story.
3. public claims rely on evidence that can be pointed to quickly.
4. a new technical evaluator can find:
   - install
   - docs
   - trust/proof
   - licensing/commercial path
5. the repo no longer presents stale Google-Slides/Firebase-era language as
   the main product story.
6. release notes consistently summarize user-facing impact rather than raw
   internal activity.

## 14. Follow-On Tasks

This spec should be followed by a task document that breaks the work into:

- repo metadata updates
- docs/website content tasks
- proof asset production
- licensing page work
- acquisition page work
- release-note template normalization

The task list should stay in `svg2ooxml`, while `openxml-audit` owns any proof
asset generation that depends on durable validation or oracle evidence.
