# PowerPoint Animation Oracle SSOT

This note defines where animation research should land long-term.

The short version:

- authored `.pptx` files are input material
- extracted raw PowerPoint XML is the durable oracle
- normalized XML is for diffing and mining
- human notes are commentary, not the source of truth

## Why This Exists

For animation work we care about at least five different things:

1. ECMA legality
2. PowerPoint loadability
3. PowerPoint slideshow behavior
4. Animation Pane / build-list behavior
5. Round-trip stability after save

Those are not the same set.

The practical consequence is:

- a valid ECMA structure may be ignored by PowerPoint
- a renderable structure may be rewritten on save
- a renderable structure may not surface cleanly in the UI
- a UI-authored structure is often the safest emitter template

So we need a corpus that preserves what PowerPoint actually emitted, not just
what we think should work.

## SSOT Hierarchy

For each researched animation case, the data hierarchy should be:

1. Raw slide XML from a saved PowerPoint deck
2. Extracted `p:timing` and `p:bldLst` fragments
3. Normalized XML for stable diffs
4. Manifest metadata
5. Human research notes

In other words:

- SSOT: raw XML
- derived analysis: normalized XML, signatures, summaries
- temporary tooling input: working `.pptx` decks

## Canonical Artifact Layout

Oracle material should live under `docs/research/powerpoint_oracle/`.

Recommended structure:

```text
docs/research/powerpoint_oracle/
  <source-name>/
    manifest.json
    README.md
    <deck-name>/
      deck.meta.json
      slide1/
        slide.raw.xml
        timing.raw.xml
        timing.normalized.xml
        summary.json
      slide2/
        ...
```

Rules:

- `slide.raw.xml` is the primary artifact when group structure or shape tree
  matters.
- `timing.raw.xml` is the primary artifact when timing-only work is being
  mined.
- `timing.normalized.xml` exists only to make diffs and pattern families
  readable.
- `manifest.json` indexes provenance and signatures across the source.

## Temporary Deck Policy

Working `.pptx` decks are allowed, but they are not the long-term research
target.

Use them only for:

- authoring a case in PowerPoint
- replaying in slideshow
- triggering PowerPoint to canonicalize XML on save
- passing material into the extractor

Once the XML is extracted, the deck becomes secondary.

If we later clean house, we should be able to delete a temporary deck and keep
the research value intact because the raw XML and manifest remain.

## Case Identity

Each research case should have a stable identity independent of any one deck.

Suggested fields:

- `case_id`
- `category`
- `source_kind`
- `source_deck`
- `source_slide`
- `ui_description`
- `expected_behavior`
- `powerpoint_version`
- `roundtrip_status`
- `render_status`
- `pane_status`
- `notes`

This should live in `deck.meta.json` or a future case-level manifest once the
corpus gets larger.

## Confidence Tiers

Every case should be labeled by evidence tier:

- `tier_ecma_only`
  XML is spec-driven or hand-authored, but not PowerPoint-authored.
- `tier_loadable`
  PowerPoint opens without repair.
- `tier_renderable`
  Slideshow behavior verified.
- `tier_ui_native`
  Authored or re-saved by PowerPoint.
- `tier_roundtrip_stable`
  Re-save does not materially rewrite the intended structure.

Emitter templates should prefer `tier_ui_native` or `tier_roundtrip_stable`
cases whenever possible.

## Research Flow

The intended flow for obscure animation research is:

1. Find or author a behavior in PowerPoint.
2. Save the deck.
3. Extract with `tools/visual/powerpoint_oracle.py`.
4. Preserve raw slide XML and timing XML.
5. Record expected behavior and confidence tier.
6. Mine common structures into emitter templates.

That means the pipeline is:

```text
PowerPoint UI -> saved PPTX -> raw XML extraction -> normalization -> template mining
```

Not:

```text
spec guess -> emitter -> hope
```

## What Counts As "Obscure"

The obscure bucket is any case where at least one of these is true:

- not obvious from ECMA alone
- not easy to author with our current exporter
- PowerPoint adds wrapper structure that is not intuitive
- slideshow and edit mode disagree
- Animation Pane grouping matters
- triggers or build sequencing matter
- save-roundtrip materially rewrites the tree

## Immediate Repository Direction

The repository should eventually contain:

- a curated oracle corpus in XML-first form
- a backlog of missing animation cases
- tooling that extracts, validates, and classifies cases

The repository should not depend on one giant omnibus demo deck as the durable
knowledge base.

That deck can exist as a temporary authoring board, but the XML corpus is the
real archive.
