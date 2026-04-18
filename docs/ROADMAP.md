# Project Roadmap

Last updated: 2026-04-18

This roadmap is for the `svg2ooxml` converter/runtime package. Empirical
PowerPoint behavior research, authored control decks, and durable oracle
evidence live in the companion repository
[`openxml-audit`](https://github.com/BramAlkema/openxml-audit).

## Current Status Snapshot

- **Core pipeline**: SVG → IR → DrawingML → PPTX is established, with the
  current release stream focused on animation fidelity, native-effect mapping,
  and editable-first fallback behavior.
- **Validation**: W3C samples, OpenXML validation, visual proof decks, and
  PowerPoint playback checks remain the main verification path.
- **Packaging**: Published on PyPI as `svg2ooxml`, with GitHub as the source
  repository and primary contributor surface.
- **Research boundary**: PowerPoint-authored control decks and oracle evidence
  are now kept in `openxml-audit` so the converter repo can stay focused on
  shipping behavior.
- **Integrations**: Browser export workflows and hosted service integrations
  exist, but the package/runtime remains the primary product surface.

## Recent Release Focus

- **1.0.0**: repository boundary cleanup, Python 3.14 standardization, the
  extracted `apps/figma2gslides` surface, and reproducible container render
  workflows
- **0.6.8**: animation oracle normalization, universal compound effects, and
  structured SSOT vocabularies for valid and falsified PowerPoint animation
  shapes
- **0.6.7**: deeper SMIL timing support, keyPoints handling, and tighter native
  mapping/proof-deck tooling
- **0.6.6**: better editable animated lines, motion proof decks, and stronger
  PowerPoint capture tooling
- **Earlier gap-closure work**: broad SVG feature coverage improvements remain
  important context, but the immediate release story is now mostly about
  fidelity tightening rather than headline feature-count growth

## Near-Term Priorities

### Blocking

- [ ] run larger W3C/body passes against the current animation/runtime stack
- [ ] keep tightening native animation mappings where PowerPoint playback and
      authored XML permit it
- [ ] finish end-to-end browser export workflow testing and fix integration
      failures that still surface there

### Quality

- [ ] keep converter docs, task plans, and release notes aligned with the
      `openxml-audit` boundary
- [ ] add stronger end-to-end pipeline tests around current animation work
- [ ] define resvg parity thresholds and decide when it should become the
      default visual path
- [ ] keep visual capture and proof-deck tooling reliable enough for routine
      playback verification

## Longer-Term Work

- `calc()` CSS expression evaluator
- `@import` stylesheet resolution
- `<foreignObject>` support through a browser-backed path
- Async conversion option for large multi-frame exports
- Visual regression CI with LibreOffice screenshots
