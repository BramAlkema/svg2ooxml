# Changelog

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
