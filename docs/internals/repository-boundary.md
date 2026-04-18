# Repository Boundary

This repository currently hosts two code surfaces plus one sibling research
repo. Keeping the boundary explicit avoids leaking app concerns into the
converter and avoids treating empirical PowerPoint lab work as product code.

## Ownership

### `svg2ooxml`

Owns the converter library and converter-facing CLI:

- SVG parse -> IR -> DrawingML / PresentationML emission
- PPTX packaging
- converter-side policies, fallbacks, and validators
- converter documentation, specs, tasks, and ADRs
- converter-facing CLI commands under `cli/`

### `figma2gslides`

Owns the extracted app/product surface that happens to live in this repo for
now:

- FastAPI runtime under `src/figma2gslides/`
- app assets under `apps/figma2gslides/`
- API entrypoints and app-local runners under `apps/figma2gslides/`
- auth, hosting, Firebase, Google Slides publishing, and legal pages
- app-local helper scripts and app-specific operational notes

### `openxml-audit`

Owns empirical PowerPoint discovery and validation infrastructure:

- authored control decks
- roundtrip and diff tooling
- oracle-corpus research
- research ADRs and durable evidence for PowerPoint behavior

## Placement Rules

Put work in `svg2ooxml` when it changes emitted converter behavior.

Put work in `figma2gslides` when it changes app runtime, auth, hosting,
plugin UX, or Google-specific operational flows.

Put work in `openxml-audit` when it discovers or records what PowerPoint does
with authored XML.

## Practical Rule Of Thumb

If a change could disappear without affecting `svg2ooxml convert input.svg -o
output.pptx`, it probably does not belong in the converter surface.
