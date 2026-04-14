# PowerPoint Oracle: CloudPresentationPack

This note records the first extracted PowerPoint timing oracle built from the
public `giuleon/CloudPresentationPack` sample decks.

The raw oracle artifacts live in:

- `docs/research/powerpoint_oracle/cloudpresentationpack/manifest.json`
- `docs/research/powerpoint_oracle/cloudpresentationpack/README.md`
- `docs/research/powerpoint_oracle/cloudpresentationpack/*/slide1/timing.raw.xml`
- `docs/research/powerpoint_oracle/cloudpresentationpack/*/slide1/timing.normalized.xml`

The extractor is:

- `tools/visual/powerpoint_oracle.py`

The extraction command used for this first oracle was:

```bash
.venv/bin/python tools/visual/powerpoint_oracle.py \
  --source-name cloudpresentationpack \
  --output docs/research/powerpoint_oracle/cloudpresentationpack \
  /tmp/svg2ooxml-external/CloudPresentationPack/*.pptx
```

## Scope

The sample set is small but useful:

- `Azure Key Vault.pptx`
- `AzureFunc-Animation.pptx`
- `Flow.pptx`
- `SPFx.pptx`

All four are single-slide decks with real `p:timing` content.
None of them depend on slide transitions.
All four use native PowerPoint animation nodes directly.

## What The Oracle Shows

### 1. Visibility is explicitly set before authored entrance effects

The most repeated authored reveal is not "just fade in".
PowerPoint often leads with:

- `set style.visibility = visible`

Then stacks the actual entrance behavior after it.

Observed families:

- `clickEffect|entr|set|style.visibility`
- `withEffect|entr|set|style.visibility`
- `afterEffect|entr|set|style.visibility`

Implication:

- for discrete reveal semantics, authored PowerPoint expects explicit visibility
  state, not only an entrance preset
- our display/visibility emitter should be template-driven from these structures,
  not guessed from schema-valid minimal XML

### 2. Composite entrances are built as sibling effects, not one magic node

The most useful family in this oracle is:

- `withEffect|entr|set+animEffect+anim+anim|style.visibility,ppt_x,ppt_y`

That structure appears three times across the sample decks, with preset IDs
`42` and `47`.

The pattern is:

1. `set style.visibility`
2. `animEffect transition="in" filter="fade"`
3. `anim ppt_x`
4. `anim ppt_y`

Implication:

- PowerPoint authors positional entrances as a stack of sibling effects
- if we want a native editable "reveal while drifting into place" effect,
  this family is the right oracle template
- preset ID drift exists, so the structural family matters more than a single
  hard-coded preset number

### 3. Motion is authored as standalone `animMotion` groups with `ppt_x/ppt_y`

Observed families:

- `withEffect|path|animMotion|ppt_x,ppt_y`
- `afterEffect|path|animMotion|ppt_x,ppt_y`

Implication:

- PowerPoint keeps path motion isolated in its own effect container
- `afterEffect` versus `withEffect` is part of the authored sequencing model and
  should not be flattened away
- our motion pipeline should preserve this separation when stacking motion with
  reveals or emphasis

### 4. Scale emphasis appears in two materially different forms

Observed families:

- `withEffect|emph|animScale|-`
- `withEffect|emph|animEffect+animScale|-`
- `afterEffect|emph|animEffect+animScale|-`

The simple scale family is a plain `animScale`.
The richer pulse family combines:

- `animEffect transition="out" filter="fade"`
- `animScale` with short duration and `autoRev`

Implication:

- our current "pulse" and "fade" logic should treat these as separate authored
  templates, not one merged heuristic
- the pulse-like case is especially relevant for opacity-like mimic work

### 5. Size-and-rotation entrance is authored as property animations, not as scale-only

The `SPFx` deck contributes the family:

- `withEffect|entr|set+anim+anim+anim+animEffect|style.visibility,ppt_w,ppt_h,style.rotation`

This is important because PowerPoint is not using only `animScale`.
It animates:

- width
- height
- rotation
- fade

Implication:

- editable transform/reveal mimicry should allow width/height/rotation property
  stacks, not just `animScale` or `animMotion`
- this is a direct oracle for "grow and unrotate into place" behavior

### 6. `bldLst` appears when one shape participates in multiple build groups

Only `SPFx` emits `p:bldLst`, and it shows the critical pattern:

- the same `spid` can be listed more than once
- additional `grpId` values tie later effects back to that same shape

Implication:

- when a shape is staged through multiple build phases, `bldLst` matters
- we should treat `bldLst` as part of the oracle for multi-phase native effects,
  not as optional decoration

## Immediate Emitter Guidance

The CloudPresentationPack oracle is already strong enough to guide the next
native-animation cleanup:

1. Build template emitters around structural families, not just exact preset IDs.
2. Keep visibility-setting as an explicit first-class step in reveal templates.
3. Preserve `withEffect` versus `afterEffect` sequencing from authored decks.
4. Use separate templates for:
   - reveal-only
   - reveal + drift
   - motion-only
   - pulse emphasis
   - grow/unrotate reveal
5. Treat `bldLst` as required whenever one shape is reused across multiple
   authored build groups.

## Gaps

This oracle does not yet cover the hard cases that motivated the current work:

- appear -> disappear -> appear on the same shape
- blink / repeated visibility toggling
- `fill="remove"` reversion
- parent-gated group reveal/hide
- event/sync-base trigger chains

That means this oracle is a good first layer, but not the full discrete-state
oracle yet. The next step is to add tiny hand-authored decks specifically for
re-entry and reversion semantics.
