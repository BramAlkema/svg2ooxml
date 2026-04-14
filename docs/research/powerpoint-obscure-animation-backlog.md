# PowerPoint Obscure Animation Backlog

This is the collection target for animation research that should eventually
land in XML-first oracle artifacts.

The goal is not "find fancy animations".

The goal is:

- identify animation behaviors where ECMA is insufficient
- author or find them in PowerPoint
- extract raw XML
- classify what is actually stable and useful for the exporter

## Priority 1

These are the highest-value missing cases because they directly affect current
exporter fidelity and timing semantics.

### Triggered sequences

- click self
- click other shape
- one effect with multiple trigger shapes
- trigger on begin of another effect
- trigger on end of another effect
- restart modes for triggered sequences
- repeated clicks while active

Why:

- this is where `interactiveSeq`, `evtFilter`, and wrapper structure become
  PowerPoint-specific
- UI and slideshow behavior matter as much as raw validity

### Visibility and state reversion

- appear only
- disappear only
- appear -> disappear
- appear -> disappear -> appear
- blink
- hide after animation
- `fill="remove"` behavior and state rollback

Why:

- visibility state and reversion are easy to get wrong
- authored PowerPoint often uses `set style.visibility` in ways that are more
  specific than a naive emitter would guess

### Group semantics

- reveal a group
- hide a group
- reveal/hide/re-reveal a group
- animate child inside visible group
- animate child while parent reveal happens
- trigger attached to a group versus a child
- nested groups

Why:

- group shape trees matter, not just timing
- raw `slide.xml` is part of SSOT here, not only `timing.xml`

### Motion sequencing

- path effect with trigger
- path + auto-reverse
- path + repeat
- path + concurrent scale
- path + concurrent rotation
- reverse motion
- motion plus authored path metadata variants

Why:

- PowerPoint sometimes adds extra path metadata
- the order and wrapper structure affect behavior

## Priority 2

These are likely important but slightly less blocking than trigger/state work.

### Emphasis composites

- pulse
- grow/shrink
- spin
- teeter
- transparency pulse
- color pulse
- line/fill coordinated emphasis

Why:

- emphasis effects are often emitted as multi-node structures, not one simple
  behavior

### Entrance and exit composites

- fade
- wipe
- zoom
- split
- fly in / fly out
- grow and turn
- shrink and turn
- motion + fade entrance
- motion + fade exit

Why:

- there are multiple authored family templates for conceptually similar UI
  effects

### Timing controls

- with previous
- after previous
- delayed starts
- zero-duration set plus longer effect
- overlapping duration stacks
- very short durations
- long-running durations

Why:

- wrapper shape and condition placement affect slideshow results

## Priority 3

These are deeper cuts that may matter later for completeness or difficult SVG
cases.

### Text-specific animation

- by paragraph
- by word
- by letter
- grouped text builds
- mixed text and shape timing

### Media and special targets

- chart element animation
- SmartArt builds
- image emphasis versus shape emphasis
- connector motion / line-specific behavior

### Advanced behavior attributes

- `accel` / `decel`
- `autoRev`
- repeat count values
- indefinite repeat
- override modes
- additive behaviors
- runtime-only properties such as `ppt_*`

## Source Types To Mine

We should collect from several kinds of sources, not just one:

- hand-authored PowerPoint decks made specifically for oracle extraction
- community example decks with interesting timing trees
- PowerPoint template/demo repositories
- VBA-authored decks that use the object model
- our own minimal authoring boards saved back through PowerPoint

## Evidence We Want Per Case

For each case, preserve:

- raw slide XML
- raw timing XML
- normalized timing XML
- a short text description of the expected visual result
- whether it opens without repair
- whether it renders correctly in slideshow
- whether it appears cleanly in the Animation Pane
- whether save-roundtrip rewrites it

## Minimal Case Format

Every obscure case should ultimately reduce to a compact XML-first record:

```text
case id
source
slide
expected behavior
raw slide xml
raw timing xml
normalized timing xml
confidence tier
```

That is enough to:

- inspect the exact PowerPoint structure
- compare it to related cases
- convert it into an emitter template later

## Current Working Rule

If a behavior is important and non-obvious:

- do not trust prose alone
- do not trust ECMA alone
- do not trust one rendered screenshot alone

Collect the XML.
