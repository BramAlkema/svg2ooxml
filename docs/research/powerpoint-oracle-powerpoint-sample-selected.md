# PowerPoint Oracle: PowerPoint-Sample Selected

This note covers the selected-subset oracle extracted from:

- `/tmp/svg2ooxml-external/PowerPoint-Sample-selected`

The selected decks are:

- `Journey.pptx`
- `Journey1.pptx`
- `MakeAnimated PowerPoint Slide by PowerPoint School.pptx`
- `Attractive Presentation Slide with animation by PowerPoint School.pptx`

The full extracted artifacts were generated during research but are not kept in
git. The committed representative fixture from this source is:

- `docs/research/powerpoint_oracle/selected/powerpoint-school-slide4/slide4/`

## Why This Subset Matters

This repo is noisy as a whole, but these four decks are useful because they
contain a large number of authored entrance stacks repeated across many slides.

Unlike `examples.pptx`, which broadens the family catalog, this subset mostly
strengthens confidence in which authored structures are common in real decks.

## High-Value Result

The most repeated family by far is:

- `withEffect|entr|set+animEffect+anim+anim|style.visibility,ppt_x,ppt_y`

Count in this subset:

- `45`

That matters because it confirms a strong authored default for:

- reveal object
- fade it in
- animate x/y into place

This is not an edge-case family. It is a mainstream authored pattern.

## Strongly Reinforced Families

The subset repeatedly uses these families:

- `withEffect|entr|set+animEffect+anim+anim|style.visibility,ppt_x,ppt_y`
- `afterEffect|entr|set+anim+anim+animEffect|style.visibility,ppt_w,ppt_h`
- `afterEffect|entr|set+animEffect+anim+anim|style.visibility,ppt_x,ppt_y`
- `withEffect|entr|set+animEffect|style.visibility`
- `withEffect|entr|set+anim+anim|style.visibility,ppt_x,ppt_y`
- `withEffect|emph|animEffect+animScale|-`
- `withEffect|path|animMotion|ppt_x,ppt_y`

This gives us a practical priority order for emitter templates:

1. reveal + fade + x/y motion
2. reveal + grow
3. reveal-only fade
4. reveal + x/y motion without fade
5. pulse emphasis
6. motion-only

## What This Subset Adds Beyond Earlier Oracles

Compared to `CloudPresentationPack`, this subset adds:

- far more frequency data
- repeated `afterEffect` entrance chains
- repeated `withEffect` entrance chains
- stronger evidence that width/height-based entrance stacks are common

Compared to `examples.pptx`, this subset adds:

- less breadth
- more repetition
- better evidence for which families are common enough to implement first

In short:

- `examples.pptx` tells us what PowerPoint can author
- this subset tells us what authored decks actually repeat a lot

## What It Does Not Add

This subset still does not solve the main missing oracle gap:

- appear -> disappear -> appear
- blink
- temporary state with reversion
- group visibility inheritance
- trigger-chain semantics

So it is valuable for template prioritization, but it does not replace the need
for hand-authored discrete-state oracle decks.
