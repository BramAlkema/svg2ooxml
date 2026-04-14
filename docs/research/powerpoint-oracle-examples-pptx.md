# PowerPoint Oracle: examples.pptx

This note records the oracle extracted from:

- `/Users/ynse/projects/svg2ooxml/tmp/examples.pptx`

The extracted artifacts live in:

- `docs/research/powerpoint_oracle/examples-pptx/manifest.json`
- `docs/research/powerpoint_oracle/examples-pptx/README.md`
- `docs/research/powerpoint_oracle/examples-pptx/*/timing.raw.xml`
- `docs/research/powerpoint_oracle/examples-pptx/*/timing.normalized.xml`

This deck is much denser than the first CloudPresentationPack oracle and is
therefore more useful for preset-family mining.

## Scope

High-level extraction summary:

- `13` slides
- `13` slides with `p:timing`
- `12` slides with `p:bldLst`

This deck is not a toy sample. It is a compact library of authored PowerPoint
animation structures.

## Why It Matters

The first oracle from CloudPresentationPack was good for:

- reveal stacks
- motion stacks
- simple scale/pulse combinations
- a small amount of `bldLst` usage

This second oracle adds the missing authored families:

- multiple exit structures
- color-emphasis compositions
- multi-step rotation emphasis
- richer entrance composites
- path variants with extra motion attributes

## Key Families

### 1. Plain reveal still starts with `set style.visibility`

The simplest reveal family is still present:

- `clickEffect|entr|set|style.visibility`

This confirms that explicit visibility-setting is a stable authored baseline,
not an accident from the first oracle.

### 2. There are multiple authored entrance composites, not one

Observed entrance families include:

- `clickEffect|entr|set+animEffect|style.visibility`
- `withEffect|entr|set+anim+anim|style.visibility,ppt_x,ppt_y`
- `clickEffect|entr|set+anim+anim|style.visibility,ppt_w,ppt_h`
- `clickEffect|entr|set+anim+anim+animEffect|style.visibility,ppt_w,ppt_h`
- `clickEffect|entr|set+anim+anim+animEffect+anim+anim|style.visibility,ppt_w,ppt_h,ppt_x,ppt_y`

Implication:

- PowerPoint authors several different reveal recipes depending on whether the
  object only fades in, grows in, or grows and moves in
- our emitter should not collapse all entrances to one template

### 3. Exit is a family of structures, not just fade-out

Observed exit families include:

- `clickEffect|exit|animEffect+set|style.visibility`
- `clickEffect|exit|anim+animEffect+set|ppt_y,style.visibility`
- `clickEffect|exit|animEffect+anim+anim+set|ppt_x,ppt_y,style.visibility`
- `clickEffect|exit|animEffect+anim+anim+anim+set|ppt_x,ppt_y,style.visibility`
- `clickEffect|exit|anim+anim+animEffect+set|ppt_w,ppt_h,style.visibility`
- `clickEffect|exit|anim+anim+anim+animEffect+set|ppt_w,ppt_h,style.rotation,style.visibility`
- `afterEffect|exit|set|style.visibility`

Implication:

- exit semantics are a large oracle surface by themselves
- the current display/visibility work should be split into:
  - reveal-only templates
  - exit-only templates
  - re-entry/reversion templates built from these
- exit can be composed with position, size, and rotation properties before the
  final visibility state change

### 4. Color emphasis is strongly template-shaped

Observed families:

- `clickEffect|emph|animClr+animClr+set+set|style.color,fillcolor,fill.type,fill.on`
- `clickEffect|emph|animClr+animClr+animClr+set|style.color,fillcolor,stroke.color,fill.type`

Implication:

- authored PowerPoint color effects are not just a single `animClr`
- they may toggle fill state and fill mode around the color tweens
- this is directly relevant for our native color animation emitter

### 5. Rotation emphasis is emitted as a multi-node authored stack

Observed family:

- `clickEffect|emph|animRot+animRot+animRot+animRot+animRot|r`

Implication:

- PowerPoint may split one conceptual rotation effect into several `animRot`
  nodes
- if we want close parity with authored behavior, rotation should be template-
  driven rather than assumed to be one `animRot`

### 6. Motion can carry more than `ppt_x` and `ppt_y`

Observed path families:

- `clickEffect|path|animMotion|ppt_x,ppt_y`
- `clickEffect|path|animMotion|ppt_x,ppt_y,ppt_c`

Implication:

- some authored motion effects carry extra path-center metadata
- our motion oracle should preserve these path variants rather than normalizing
  them away

## Most Important Slides

The highest-signal slides are:

- `slide12.xml`
  This is the richest preset-library slide. It contains repeated examples of
  color emphasis, rotation emphasis, multiple exits, and multiple entrances.
- `slide13.xml`
  This adds path, entrance, exit, and rotation combinations in one place.
- `slide5.xml`
  This contributes the largest entrance composite:
  `set + size anims + fade + position anims`.

## Immediate Use

This deck is strong enough to define the next oracle-backed emitter slices:

1. Native entrance catalog
   Separate templates for pure reveal, grow-in, move-in, and grow+move-in.
2. Native exit catalog
   Separate templates for fade-out only, move-out, shrink-out, and
   shrink/rotate-out.
3. Color-emphasis catalog
   Template families driven by actual `animClr + set` structures.
4. Rotation-emphasis catalog
   Multi-node `animRot` stacks instead of one synthetic rotation effect.

## Relation To The First Oracle

Use the two oracles together:

- `CloudPresentationPack`:
  cleaner and easier to read, good for baseline reveal/motion compositions
- `examples.pptx`:
  denser preset library, good for mined families and authoring diversity

The next missing oracle layer is still hand-authored discrete-state behavior:

- appear -> disappear -> appear
- blink
- `fill="remove"` reversion
- parent/group reveal and hide
- event/sync-base trigger chains

Those are not replaced by this deck, but this deck substantially improves the
native entrance/exit/emphasis side of the oracle.
