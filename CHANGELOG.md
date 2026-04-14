# Changelog

## 0.6.8 - 2026-04-15

- expanded the animation oracle from 7 to 18 slots covering every PowerPoint emphasis, entrance, exit, and motion-path primitive, all empirically verified to play in Microsoft PowerPoint via the tune-loop harness
- introduced the universal `emph/compound` slot plus a 10-item behavior fragment library (`transparency`, `fill_color`, `text_color`, `stroke_color`, `bold`, `underline`, `blink`, `rotate`, `scale`, `motion`) — one `<p:cTn>` holds any combination of behaviors that fire simultaneously, replacing the preset-per-slot model for stacked effects
- added `AnimationOracle.instantiate_compound(behaviors=...)` and `BehaviorFragment` dataclass as the primary multi-effect authoring API, plus `AnimationXMLBuilder.build_compound_par()` as the writer-level entry point for handlers
- collapsed 40+ entrance/exit presets into two universal filter-parameterised slots (`entr/filter_effect`, `exit/filter_effect`) covering 16 empirically verified `<p:animEffect filter>` values (fade, dissolve, wipe, wedge, wheel, circle, strips, blinds, checkerboard, barn, randombar) plus direction subparameters
- promoted the animation vocabulary to three structured XML SSOT files: `filter_vocabulary.xml` (29 filter entries), `attrname_vocabulary.xml` (17 valid `<p:attrName>` values confirmed complete), and `dead_paths.xml` (7 empirically falsified shapes with replacement guidance)
- added typed loaders for the SSOT files: `AnimationOracle.filter_vocabulary()`, `attrname_vocabulary()`, `dead_paths()` with by-value and by-id lookups, plus negative-test invariants that assert dead-path attrNames never appear in the valid vocabulary
- documented empirically falsified paths: `<p:anim>` on `fill.opacity`, `stroke.opacity`, `stroke.weight`, `line.weight`, and isolated `style.fontSize` all parse as valid OOXML but are silently dropped by PowerPoint's playback engine; `<p:animEffect filter="image">` only fires when paired with a `<p:set>` on `style.opacity` inside a preset 9 wrapper
- added the **pptx-animation Claude skill** at `.claude/skills/pptx-animation/` — CLI scripts for entrance/exit/compound/motion emission plus a validator that walks XML and flags dead-path matches against the `dead_paths.xml` SSOT; fully self-contained with vendored oracle SSOT files and auto-generated markdown references
- added `tools/build_skill.py` with `--check` drift detection for CI so the in-tree skill cannot diverge from the oracle SSOT
- expanded the oracle README from 68 to 330+ lines covering both layer-1 (preset-specific) and layer-2 (compound + fragments) APIs, build-mode matrix, targeting wrapper semantics, and empirical methodology
- session totals: 10 new commits, ~8,500+ lines added, 693 unit tests passing (up from 663), including the universal compound slot, three vocabulary SSOTs, the Claude skill package, and the writer-level compound helper

## 0.6.7 - 2026-04-14

- expanded SVG animation plumbing for SMIL timing, from/to/by values, repeat/end/restart handling, keyPoints, native-match metadata, and unsupported-trigger policy decisions
- improved PowerPoint animation fidelity for fade in/out, calcMode linear/paced path retiming, motion keyPoints, opacity pulses, scale transforms, and display/visibility fill behavior
- added a native animation mapping spec plus oracle/proof-deck tooling for matching SVG animation features to PresentationML structures
- updated animation golden fixtures and regression coverage, including the duplicate drawingml image test module collection fix

## 0.6.6 - 2026-04-12

- improved PowerPoint animation fidelity across motion, rotate, opacity, and line endpoint handling, including safer composition of sampled motion stacks and clearer unsupported-case tracing
- fixed editable line and polyline animation export by materializing simple animated lines as native connector lines and splitting stroked animated polylines into per-segment editable lines, including fade-compatible segment targeting
- corrected image layout and visual sizing for converted decks by honoring painted image content bounds and `preserveAspectRatio` when resolving embedded image geometry
- hardened PowerPoint visual tooling with slideshow/window capture fixes plus new motion-lab and W3C proof-deck utilities for end-to-end fidelity checks
- expanded parser, exporter, animation-handler, paint, capture, and visual regression coverage around the new animation and rendering paths

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
