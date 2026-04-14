# Oracle Overview

This skill is a thin wrapper around the `AnimationOracle` in
`src/svg2ooxml/drawingml/animation/oracle.py`. The oracle is a
single-source-of-truth library of PowerPoint animation XML shapes that
have been empirically verified to play in Microsoft PowerPoint, plus a
catalog of shapes that *look* valid but are silently dropped at
playback.

## Two layers

### Layer 1 — Preset-specific slots

Each slot is a full `<p:par>` wrapper with a PowerPoint-recognised
`presetID` / `presetSubtype`. When instantiated, the effect round-trips
through PowerPoint's Animation Pane with its proper preset name (e.g.
"Change Font Color", "Transparency"). Use this layer when you want PPT
authors to later edit the animation in the Pane UI.

```python
from svg2ooxml.drawingml.animation.oracle import default_oracle
par = default_oracle().instantiate(
    "entr/fade",
    shape_id="2",
    par_id=6,
    duration_ms=1500,
    SET_BEHAVIOR_ID=7,
    EFFECT_BEHAVIOR_ID=71,
)
```

Slot list (18 slots total): see the scripts in this skill — they each
call a specific layer-1 slot for the corresponding effect type.

### Layer 2 — Compound slot + behavior fragments

**Key empirical finding:** PowerPoint's rendering engine does NOT
require preset IDs to fire animation behaviors. It walks the
`<p:cTn>`'s `childTnLst` and fires every
`<p:set>`/`<p:animEffect>`/`<p:animClr>`/`<p:animRot>`/`<p:animScale>`/
`<p:animMotion>`/`<p:anim>` child directly. Preset IDs are cosmetic
metadata for the PPT UI, not runtime input.

This means any combination of behaviors can be composed inside ONE
`<p:cTn>` — without nested `<p:par>` siblings, without preset
coordination, without `withEffect` group IDs. The universal compound
slot expresses this directly: a bare `<p:par>`/`<p:cTn>` scaffold with
an empty `childTnLst` that the handler fills with behavior fragments.

```python
from svg2ooxml.drawingml.animation.oracle import (
    BehaviorFragment,
    default_oracle,
)
par = default_oracle().instantiate_compound(
    shape_id="2",
    par_id=5,
    duration_ms=3000,
    behaviors=[
        BehaviorFragment("transparency", {"SET_BEHAVIOR_ID": 10, "EFFECT_BEHAVIOR_ID": 11, "TARGET_OPACITY": "0.5"}),
        BehaviorFragment("rotate",       {"BEHAVIOR_ID": 20, "ROTATION_BY": "21600000"}),
        BehaviorFragment("motion",       {"BEHAVIOR_ID": 30, "PATH_DATA": "M 0 0 L 0.1 0.1 E"}),
    ],
)
```

Available fragments in `oracle/emph/behaviors/`:
`transparency`, `fill_color`, `text_color`, `stroke_color`, `bold`,
`underline`, `blink`, `rotate`, `scale`, `motion`. Each takes its own
per-fragment tokens (`BEHAVIOR_ID`, `TO_COLOR`, `ROTATION_BY`, etc.).
See `compound_api.md` for the full catalog.

## Three vocabulary SSOTs

The oracle carries three structured XML vocabularies that define what
PowerPoint actually supports. All are machine-readable and loadable
via the oracle:

- **`oracle/filter_vocabulary.xml`** — 29 `<p:animEffect filter>` string
  values. Loaded via `oracle.filter_vocabulary()`. See
  `filter_vocabulary.md` (auto-generated).

- **`oracle/attrname_vocabulary.xml`** — the 17 valid `<p:attrName>`
  values. Confirmed exhaustive by scanning all PowerPoint reference
  files. Loaded via `oracle.attrname_vocabulary()`. See
  `attrname_vocabulary.md` (auto-generated).

- **`oracle/dead_paths.xml`** — 7 empirically falsified shapes with
  their replacement paths. Loaded via `oracle.dead_paths()`. See
  `dead_paths.md` (auto-generated).

Each vocabulary is lazy-cached and has lookup APIs:

```python
oracle = default_oracle()
oracle.filter_entry("wipe(down)")    # FilterEntry with preset 22/4
oracle.attrname_entry("fillcolor")   # AttrNameEntry with scope 'shape-background'
oracle.dead_path("anim-fill-opacity") # DeadPath with replacement 'emph/transparency'
oracle.is_valid_attrname("fill.opacity")  # False — it's in dead_paths.xml
```

## Why the oracle exists

ECMA-376 describes every XML shape PowerPoint's parser *accepts*. It
does not describe the subset PowerPoint's playback engine actually
*animates*. Many paths that appear valid in the spec are silently
dropped at playback. The oracle was built by:

1. Authoring reference animations in PowerPoint's UI, saving as .pptx,
   and unzipping the timing XML to extract ground-truth shapes.
2. Running each candidate through the tune-loop harness
   (`tools/visual/animation_tune.py`) which drives PowerPoint via
   AppleScript and captures slideshow frames.
3. Recording what played, what was dropped, and the structural
   requirements (wrapper shape, `bldP` build mode, iterate semantics).

Every `visually-verified` slot has been seen animating on screen, not
just validated against the spec. Every `dead_paths.xml` entry has been
seen to silently fail, not just documented as "probably won't work".
