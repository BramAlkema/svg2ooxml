# Project Roadmap

Last updated: 2026-03-22

## Current Status (v0.5.0-dev)

- **Core pipeline**: SVG → IR → DrawingML → PPTX. Feature map at **97% closed**
  (167/172 features). 1527 unit tests pass. W3C corpus: 524/525 SVGs pass
  OpenXML validation (both Python openxml-audit and .NET Open XML SDK).
- **Validation corpus**: W3C test suite (525 SVGs) + Kelvin Lawrence collection
  (45 SVGs, on-demand download). 569 total validated SVGs.
- **Deployment**: API live on Coolify at `svg2ooxml.tactcheck.com`. Supabase
  Google OAuth replaces Firebase. Synchronous conversion (no job queue).
- **PyPI**: Published as `pip install svg2ooxml`. Trusted publishing via
  GitHub Actions OIDC.
- **Repo**: Public at `github.com/BramAlkema/svg2ooxml`. CI: unit tests +
  W3C sample with OpenXML validation.
- **Figma plugin**: Rewritten for Supabase auth + Coolify backend. Pending
  end-to-end testing.

## What changed (v0.4.0 → v0.5.0-dev)

### Feature gap closure (+78 features in one session)

Feature map went from 52% → 97% closed. Major items:

**Animation**
- Multi-keyframe rotate: splits N angles into sequential `<p:animRot>` segments
- Rotate with cx/cy center: companion `<p:animMotion>` orbital arc
- stroke-dashoffset animation: Wipe entrance for SVG line-drawing effect
- SMIL min/max duration, restart attribute, accumulate="sum" baking
- Animation sampler optimized: pre-grouped lookups + value cache (12% faster)

**Painting & Stroke**
- `stroke-dashoffset` wired to custDash writer
- `paint-order: stroke fill` via shape duplication
- `gradientUnits="userSpaceOnUse"` coordinate normalization
- Radial gradient focal point (fx/fy) center shift approximation
- `mix-blend-mode` and `isolation` via Skia rasterization
- Group opacity with overlapping children → Skia PNG rasterization

**Text**
- `xml:lang` → `lang` on `<a:rPr>`
- `font-variant: small-caps` → `cap="small"` on `<a:rPr>`
- `writing-mode: vertical` → `vert` on `<a:bodyPr>`
- `word-spacing` → proportional `spc` inflation
- `textLength` → computed letter-spacing from bbox width
- `dominant-baseline` / `alignment-baseline` → y-offset from font metrics
- `text-decoration: overline` → separate line shape
- `font-stretch` → font family suffix
- `baseline-shift` → `baseline` attribute on `<a:rPr>`
- Per-character dx/dy/x/y/rotate → glyph outlines via Skia (last resort)
- Uniform rotation → native `<a:xfrm rot>` (keeps text editable)
- textPath → WordArt `<a:prstTxWarp>` preferred over outlines

**CSS & Color**
- CSS `var()` custom properties resolved from `:root`
- CSS `@media` queries evaluated against viewport
- `oklab()` / `oklch()` color functions → sRGB conversion
- CSS system colors → sensible sRGB defaults

**Document Structure**
- `<title>` / `<desc>` → `descr` attribute on `<p:cNvPr>`

**Infrastructure**
- Fixed `_DummyNumpy` shim (float64, shape, indexing, tolist)
- Fixed `prstTxWarp` schema: child element not attribute
- Fixed custDash d/sp minimum (ECMA-376 compliance)
- WordArt classifier: relaxed thresholds, prefer native over outlines
- Skia Font cache for glyph rendering
- 9 obsolete specs removed (-5,664 lines)
- Feature map bulk-updated with verification

### Remaining open (5 items)

- `fr` (SVG2 focal radius) — zero real-world usage
- `<pattern>` vector EMF — current raster tile works
- `<foreignObject>` — needs headless browser
- `@import` — needs network/file fetch
- `calc()` — CSS math expression evaluator

## Next milestone (v0.5.0)

### Blocking

- [ ] End-to-end Figma plugin test (sign in → export → Slides link)
- [ ] Google OAuth consent screen: verify status on `do-this-484623`, publish
      if still in "Testing" mode
- [ ] Fix issues found during plugin testing

### Quality

- [ ] Redeploy API with latest code (gap closures, animation fixes)
- [ ] Switch CI badge from static to live GitHub Actions badge
- [x] Fill remaining DrawingML writer gaps (97% done)
- [ ] Add end-to-end pipeline tests
- [ ] Define resvg parity thresholds and flip resvg to default

## Future

- `calc()` CSS expression evaluator
- `@import` stylesheet resolution
- Async conversion option for large multi-frame exports
- Visual regression CI with LibreOffice screenshots
