# Changelog

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
