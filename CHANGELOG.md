# Changelog

Release notes for the `svg2ooxml` converter package live here.
Empirical PowerPoint behavior research, authored control decks, and durable
oracle evidence live in the companion repository
[`openxml-audit`](https://github.com/BramAlkema/openxml-audit).

## 0.7.0 - 2026-04-18

Release focus: package boundary cleanup, Python 3.14 standardization, and a
more explicit split between converter code and PowerPoint evidence tooling.

### Added

- first-class container render lane with Python 3.14 parity, pinned upstream
  FontForge source builds, and stable wrapper scripts for reproducible Linux
  raster/font checks
- clearer converter documentation surface, including a repository-boundary doc,
  animation documentation map, and container workflow guide
- stronger animation regression coverage around repeat-trigger expansion,
  visibility rewrite timing, and compatibility lazy imports

### Changed

- standardized local and container development on Python 3.14
- extracted Figma and Google Slides app/runtime work into a clearly separated
  `apps/figma2gslides` surface while keeping `svg2ooxml` as the converter
  package and public CLI
- moved empirical PowerPoint research ownership out of the converter docs path
  and into the companion `openxml-audit` project
- tightened repeat-trigger handling so deterministic `repeat(n)` syncbases are
  expanded before visibility planning and end triggers are emitted on the
  correct relative basis

### Removed

- stale OrbStack-specific container image definitions in favor of one shared
  Docker render lane
- obsolete in-repo PowerPoint oracle research copies that now belong in
  `openxml-audit`

## 0.6.8 - 2026-04-15

Release focus: animation oracle normalization and compound native effects.

### Added

- expanded the animation oracle from 7 to 18 slots covering emphasis,
  entrance, exit, and motion-path primitives that were empirically verified to
  play in Microsoft PowerPoint
- introduced the universal `emph/compound` slot plus a 10-item behavior
  fragment library for simultaneous transparency, fill, text/stroke color,
  bold, underline, blink, rotate, scale, and motion effects
- added `AnimationOracle.instantiate_compound(behaviors=...)`,
  `BehaviorFragment`, and `AnimationXMLBuilder.build_compound_par()` as the
  primary multi-effect authoring path
- promoted the animation vocabulary to structured SSOT XML files:
  `filter_vocabulary.xml`, `attrname_vocabulary.xml`, and `dead_paths.xml`
- added typed loaders for the SSOT files together with negative-path
  invariants

### Changed

- collapsed 40+ entrance/exit presets into two universal filter-parameterized
  slots, `entr/filter_effect` and `exit/filter_effect`, covering 16 verified
  `<p:animEffect filter>` values and their direction parameters
- documented falsified XML paths that parse as valid OOXML but are silently
  dropped by PowerPoint playback, including unsupported `<p:anim>` targets and
  the `filter="image"` wrapper requirement

### Tooling And Docs

- added the `pptx-animation` Claude skill with vendored oracle SSOT files and
  dead-path validation
- added `tools/build_skill.py --check` drift detection so the in-tree skill
  stays aligned with the oracle SSOT
- expanded the oracle README with API shape, build modes, targeting semantics,
  and empirical methodology

## 0.6.7 - 2026-04-14

Release focus: SMIL timing plumbing and PowerPoint timing fidelity.

- expanded SVG animation plumbing for SMIL timing, from/to/by values,
  repeat/end/restart handling, keyPoints, native-match metadata, and
  unsupported-trigger policy decisions
- improved PowerPoint animation fidelity for fade in/out, calcMode
  linear/paced retiming, motion keyPoints, opacity pulses, scale transforms,
  and display/visibility fill behavior
- added a native animation mapping spec plus oracle/proof-deck tooling for
  matching SVG animation features to PresentationML structures
- updated animation golden fixtures and regression coverage, including the
  duplicate drawingml image test-module collection fix

## 0.6.6 - 2026-04-12

Release focus: editable animated lines and proof-deck tooling.

- improved PowerPoint animation fidelity across motion, rotate, opacity, and
  line-endpoint handling, including safer composition of sampled motion stacks
  and clearer unsupported-case tracing
- fixed editable line and polyline animation export by materializing simple
  animated lines as native connector lines and splitting stroked animated
  polylines into per-segment editable lines, including fade-compatible segment
  targeting
- corrected image layout and visual sizing for converted decks by honoring
  painted image content bounds and `preserveAspectRatio` when resolving
  embedded image geometry
- hardened PowerPoint visual tooling with slideshow/window capture fixes plus
  new motion-lab and W3C proof-deck utilities for end-to-end fidelity checks
- expanded parser, exporter, animation-handler, paint, capture, and visual
  regression coverage around the new animation and rendering paths

## 0.6.5 - 2026-04-11

- fixed W3C lighting and specular PowerPoint fallbacks so isolated SVG previews resolve relative image assets again instead of collapsing to black panels
- corrected raster preview rendering for transformed image/filter content by flattening localized group transforms and using transformed image bounds during filter application
- aligned Skia image drawing with the installed `skia-python` API and added regressions covering transformed-group filter previews
- improved text fidelity in converted decks by scaling resvg text metrics into the active coordinate space, fixing legacy SVG web-font conversion, and removing stale outline fallback metadata on live text

## 0.6.4 - 2026-04-11

- fixed single-shape filter fallbacks so expanded filter bounds are honored instead of being squeezed back into the source geometry box
- preserved raster filter alpha by default and limited PowerPoint background flattening to explicitly opted-in fallback assets
- hardened PowerPoint visual capture staging with unique per-run deck copies so failed cleanup cannot silently reuse a stale in-memory presentation
- added regression tests covering filter fallback bounds, raster alpha preservation, opt-in flattening, and unique staged PowerPoint copies

## 0.6.3 - 2026-04-11

- expanded the editable-first filter pipeline with stronger mimic planning and rendering for blur, flood, merge, blend, composite, lighting, and color-transform stacks
- fixed fallback correctness issues in rasterized filter output, including objectBoundingBox region scaling, user-space definition handling, no-op editable glow stacks, and fallback image color transforms
- hardened fidelity-tier export isolation so policy overrides and page variants do not leak state across direct, mimic, EMF, and bitmap outputs
- added corpus-driven filter analysis and PowerPoint museum tooling to measure primitive usage and generate stacked comparison decks for tuning
- broadened filter, renderer, exporter, policy, and visual-tool test coverage around the new editable and fallback paths

## 0.6.2 - 2026-04-10

- improved PowerPoint animation authoring and validation, including authored fade in/out handling, stronger begin-trigger remapping, clearer unsupported animation reason codes, and better W3C animation audit reporting
- stabilized the PowerPoint slideshow capture flow across LaunchServices open, Home-screen activation, and slideshow startup/teardown paths
- enabled local Python 3.14 `.venv` workflows with working `skia` and `fontforge`, updated bootstrap/docs to prefer `.venv`, and added a focused FontForge stderr suppression helper
- fixed FontForge font subsetting so ligature glyphs are preserved during embedding
- added Phase 2 fidelity spec/task docs for the animation and filter roadmap

## 0.6.1 - 2026-04-06

- visual audit and rendering fidelity improvements
- PowerPoint slideshow capture and animation checking
- animation XML fidelity fixes
- WordArt and text-path fixes
- Gallardo pattern and filter rendering improvements
