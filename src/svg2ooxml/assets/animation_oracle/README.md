# Animation Oracle

A library of parameterised PowerPoint animation XML shapes that have been
**empirically verified to actually play in Microsoft PowerPoint**, plus a
catalog of shapes that look valid but are silently dropped at playback.

The oracle is the single source of truth for which `<p:par>` trees svg2ooxml
emits per preset and per compound effect. Handlers load a slot by name and
instantiate it with runtime tokens — they never hand-write timing XML.

## Why this exists

ECMA-376 describes every XML shape PowerPoint's parser *accepts*. It does not
describe the subset PowerPoint's playback engine actually *animates*. The two
sets differ: plenty of valid-looking XML (e.g. `<p:anim>` on `fill.opacity`,
`stroke.weight`, isolated `style.fontSize`) parses cleanly, round-trips, and
then silently does nothing when the slideshow runs.

This oracle was built by:

1. Authoring reference animations in PowerPoint's UI, saving as `.pptx`, and
   unzipping the timing XML to extract ground-truth shapes (`tmp/example*.pptx`).
2. Running each candidate shape through `.venv/bin/python -m tools.visual.animation_tune`,
   which drives PowerPoint via AppleScript, captures the slideshow window with
   screencapture, and compares frame pixels.
3. Recording what played, what was silently dropped, and the structural
   requirements (wrapper shape, `bldP` mode, iterate semantics) for each.

Every slot marked `visually-verified` has been seen animating on screen, not
just validated against the spec.

## Layout

```
animation_oracle/
├── README.md              (this file)
├── index.json             (slot metadata + SMIL mapping + verification state)
├── entr/                  (entrance presets)
│   ├── fade.xml
│   └── appear.xml
├── exit/                  (exit presets)
│   └── fade.xml
├── emph/                  (emphasis presets)
│   ├── compound.xml       (UNIVERSAL compound slot — primary path)
│   ├── behaviors/         (behavior fragment library for compound)
│   │   ├── transparency.xml
│   │   ├── fill_color.xml
│   │   ├── text_color.xml
│   │   ├── stroke_color.xml
│   │   ├── bold.xml
│   │   ├── underline.xml
│   │   ├── blink.xml
│   │   ├── rotate.xml
│   │   ├── scale.xml
│   │   └── motion.xml
│   ├── color.xml          (preset-specific slots, legacy fidelity path)
│   ├── rotate.xml
│   ├── scale.xml
│   ├── transparency.xml
│   ├── text_color.xml
│   ├── stroke_color.xml
│   ├── shape_fill_color.xml
│   ├── color_pulse.xml
│   ├── bold.xml
│   ├── underline.xml
│   └── blink.xml
└── path/                  (motion-path presets)
    └── motion.xml
```

## Two layers

### Layer 1 — Preset-specific slots (15 total)

Each slot is a full `<p:par>` wrapper with a PowerPoint-recognised
`presetID` / `presetSubtype`. When instantiated, the emitted effect
round-trips cleanly through PowerPoint's Animation Pane with its proper
preset name (e.g. "Change Font Color", "Transparency", "Underline"). Use
this layer when UI fidelity matters — when the user will later re-open the
generated file in PowerPoint and expect to edit the effects in the pane.

```python
from svg2ooxml.drawingml.animation.oracle import default_oracle

oracle = default_oracle()
par = oracle.instantiate(
    "entr/fade",
    shape_id="2",
    par_id=6,
    duration_ms=1500,
    delay_ms=0,
    SET_BEHAVIOR_ID=7,
    EFFECT_BEHAVIOR_ID=71,
)
```

### Layer 2 — Compound slot + behavior fragments (primary path)

**Key empirical insight:** PowerPoint's rendering engine does NOT require
preset IDs to fire animation behaviors. It walks the `<p:cTn>`'s
`childTnLst` and fires every
`<p:set>`/`<p:animEffect>`/`<p:animClr>`/`<p:animRot>`/`<p:animScale>`/
`<p:animMotion>`/`<p:anim>` child directly. Preset IDs are cosmetic
metadata for the Animation Pane, not runtime input.

This means any combination of behaviors can be composed inside ONE `<p:cTn>`
— without nested `<p:par>` siblings, without preset coordination, without
`withEffect` group IDs. The universal compound slot expresses this directly:
a bare `<p:par>`/`<p:cTn>` scaffold with an empty `childTnLst` that the
handler fills with fragments from `emph/behaviors/`.

```python
from svg2ooxml.drawingml.animation.oracle import (
    BehaviorFragment,
    default_oracle,
)

oracle = default_oracle()
par = oracle.instantiate_compound(
    shape_id="2",
    par_id=5,
    duration_ms=3000,
    delay_ms=0,
    behaviors=[
        BehaviorFragment("transparency", {
            "SET_BEHAVIOR_ID": 10,
            "EFFECT_BEHAVIOR_ID": 11,
            "TARGET_OPACITY": "0.5",
        }),
        BehaviorFragment("fill_color", {
            "STYLE_CLR_BEHAVIOR_ID": 20,
            "FILL_CLR_BEHAVIOR_ID": 21,
            "FILL_TYPE_BEHAVIOR_ID": 22,
            "FILL_ON_BEHAVIOR_ID": 23,
            "TO_COLOR": "C81010",
        }),
        BehaviorFragment("rotate", {
            "BEHAVIOR_ID": 60,
            "ROTATION_BY": "43200000",  # 720° in PPT angle units (60000/deg)
        }),
        BehaviorFragment("motion", {
            "BEHAVIOR_ID": 80,
            "PATH_DATA": "M 0 0 L 0.15 0.2 E",
        }),
    ],
)
```

The returned `<p:par>` is a single click-triggered effect that, on one Next
keypress, plays all four behaviours simultaneously: the shape moves along
the path while rotating 720°, changing fill color to red, and fading to 50%
opacity. Verified end-to-end via `.visual_tmp/xmas_tree_v3_compound.py`.

Use this layer for SMIL→PPT mapping — each SVG `<animate>` / `<animateColor>`
/ `<animateTransform>` / `<animateMotion>` / `<set>` on one element becomes
one fragment, aggregated into one compound call.

## Tokens

### Compound-level (passed to `instantiate_compound`)

| Token            | Meaning                                   |
| ---------------- | ----------------------------------------- |
| `shape_id`       | target shape `spid`                       |
| `par_id`         | outer `cTn/@id` (reused as `grpId`)       |
| `duration_ms`    | animation duration in milliseconds        |
| `delay_ms`       | start delay in milliseconds               |

These propagate implicitly into every fragment as `{SHAPE_ID}`,
`{DURATION_MS}`, `{INNER_FILL}` (defaulting to `"hold"`).

### Per-fragment (passed in `BehaviorFragment.tokens`)

| Fragment          | Tokens                                                                |
| ----------------- | --------------------------------------------------------------------- |
| `transparency`    | `SET_BEHAVIOR_ID`, `EFFECT_BEHAVIOR_ID`, `TARGET_OPACITY` (e.g. "0.5") |
| `fill_color`      | `STYLE_CLR_BEHAVIOR_ID`, `FILL_CLR_BEHAVIOR_ID`, `FILL_TYPE_BEHAVIOR_ID`, `FILL_ON_BEHAVIOR_ID`, `TO_COLOR` (6-hex, no `#`) |
| `text_color`      | `BEHAVIOR_ID`, `TO_COLOR`                                             |
| `stroke_color`    | `CLR_BEHAVIOR_ID`, `SET_BEHAVIOR_ID`, `TO_COLOR`                      |
| `bold`            | `BEHAVIOR_ID`                                                         |
| `underline`       | `BEHAVIOR_ID`                                                         |
| `blink`           | `BEHAVIOR_ID`                                                         |
| `rotate`          | `BEHAVIOR_ID`, `ROTATION_BY` (60000 per degree)                       |
| `scale`           | `BEHAVIOR_ID`, `BY_X`, `BY_Y` (100000 = 100%)                         |
| `motion`          | `BEHAVIOR_ID`, `PATH_DATA` (PPT motion path: `M 0 0 L x y E`)         |

### Layer-1 slots (passed to `instantiate`)

Per-slot tokens are declared in `index.json` as `behavior_tokens` and
`content_tokens`. See each slot's `notes` field for semantics.

## Entrance and exit filter vocabulary

PowerPoint's entrance and exit presets are all expressed as a single
`<p:animEffect transition="in|out" filter="X">` element with a filter
string picked from a fixed vocabulary. The `entr/filter_effect` and
`exit/filter_effect` oracle slots parameterise this completely — one
template per direction, with `FILTER` + `PRESET_ID` + `PRESET_SUBTYPE`
tokens substituting into the same structure.

### Filter vocabulary SSOT

The complete authoritative list of filter strings lives in
`filter_vocabulary.xml` at the oracle root — each entry records the
exact value, entrance and exit preset-ID mappings, verification state,
and provenance. **Load the vocabulary programmatically via the oracle**
rather than hand-coding the table:

```python
from svg2ooxml.drawingml.animation.oracle import default_oracle

oracle = default_oracle()
vocab = oracle.filter_vocabulary()      # tuple[FilterEntry, ...]
entry = oracle.filter_entry("wipe(down)")
entry.entrance_preset_id         # 22
entry.entrance_preset_subtype    # 4
entry.verification               # "visually-verified"
entry.description                # "top-to-bottom directional reveal"
```

The SSOT currently declares 29 filter values: 17 `visually-verified`
entries (all 16 swept through the tune loop plus `image` as a pseudo
filter used by the transparency compound) and 12 `derived-from-handler`
variants (additional direction/spoke subparameters that share structure
with verified entries but haven't been individually swept).

Each filter's sub-parameter (e.g. the direction in `wipe(down)`, the
spoke count in `wheel(1)`) is part of the string literal — change the
subparameter to get directional variants without modifying the oracle
template. To promote a `derived-from-handler` entry to `visually-verified`,
add it to `.visual_tmp/filter_sweep.py`'s FILTERS list, run the sweep,
and update `filter_vocabulary.xml`.

### Usage

```python
par = oracle.instantiate(
    "entr/filter_effect",
    shape_id="2",
    par_id=6,
    duration_ms=1500,
    delay_ms=0,
    SET_BEHAVIOR_ID=7,
    EFFECT_BEHAVIOR_ID=71,
    FILTER="circle(in)",
    PRESET_ID=18,
    PRESET_SUBTYPE=12,
)
```

Pass `PRESET_ID` / `PRESET_SUBTYPE` matching PowerPoint's preset catalog
so the effect round-trips through the Animation Pane with the right
name. For pure playback without Pane fidelity, any non-conflicting preset
IDs work.

### Exit template

`exit/filter_effect` uses the same filter vocabulary with an extra
`SET_DELAY_MS` token controlling when the shape becomes hidden (typically
`duration_ms - 1` so the effect fully plays before the shape disappears).

```python
par = oracle.instantiate(
    "exit/filter_effect",
    shape_id="2",
    par_id=6,
    duration_ms=500,
    delay_ms=0,
    SET_BEHAVIOR_ID=7,
    EFFECT_BEHAVIOR_ID=71,
    FILTER="wipe(up)",
    PRESET_ID=22,
    PRESET_SUBTYPE=1,
    SET_DELAY_MS=499,
)
```

## `bldP` build modes

PowerPoint's `<p:bldLst>` needs an entry per animation group. The required
attributes differ by effect target:

| Mode                | bldP attributes                       | Used for                                  |
| ------------------- | ------------------------------------- | ----------------------------------------- |
| `animBg`            | `animBg="1"`                          | Shape-level effects (transparency, rotate, scale, motion, stroke color, blink) |
| `paragraph`         | `build="p" rev="1"`                   | Text-paragraph effects (bold, underline, text color, font size) |
| `allAtOnce`         | `build="allAtOnce" animBg="1"`        | Compound fill-color effects (preset 19)   |

The compound slot declares `bld_mode: "paragraph"` by default so text
fragments fire correctly alongside shape fragments. Shape-only compounds
work with `animBg` too.

## Verification states

Each slot in `index.json` carries a `verification` field:

- `derived-from-handler` — extracted from an existing golden master;
  reflects what current handlers emit. Starting point.
- `oracle-matched` — structurally equivalent (same `family_signature`) to a
  fragment found in `docs/research/powerpoint_oracle/`. Trusted.
- `visually-verified` — confirmed to play correctly in Microsoft PowerPoint
  via `tools/visual/animation_tune.py`. Highest confidence.

Promote templates up this ladder by:

1. Authoring a sample that instantiates the slot
2. Running `.venv/bin/python -m tools.visual.animation_tune <sample_name>`
3. Visually confirming the expected animation plays (not just that pixels
   changed — compare frame 0 to mid/final and verify the *right* change)
4. Updating `verification` and the `notes` field with what you observed

## Empirically falsified paths (DO NOT USE)

These XML shapes are documented or implied by ECMA-376 and legacy Microsoft
sources, but Microsoft PowerPoint does NOT play them. Adding them to the
oracle without empirical verification leads to silently broken output.

| Shape                                                 | Status                                 |
| ----------------------------------------------------- | -------------------------------------- |
| `<p:anim>` on `fill.opacity`                          | **Silently dropped** at playback       |
| `<p:anim>` on `stroke.opacity`                        | **Silently dropped**                   |
| `<p:anim>` on `style.opacity` (partial range)         | **Silently dropped**                   |
| `<p:anim>` on `stroke.weight`                         | **Silently dropped**                   |
| `<p:anim>` on `line.weight`                           | **Silently dropped**                   |
| `<p:animEffect filter="image" prLst="opacity:X">` outside preset 9 | **Silently dropped** |
| `<p:anim>` on `style.fontSize` in isolation           | **Silently dropped** — requires full preset 28 compound (animClr + animClr + set + anim) as siblings in one cTn |

For opacity tweens, use:
- `entr/fade` (0→1) or `exit/fade` (1→0) for full fade transitions
- `emph/transparency` or the `transparency` behavior fragment for partial
  fade-and-hold (via `<p:set>` style.opacity + `<p:animEffect filter="image">`)

For stroke weight: no native path exists. SVG line-width tweens must be
rendered to EMF via the rasterizer fallback.

For text font size: use the `fill_color` fragment's compound form (preset
28 equivalent) with the full quadruple plus a `<p:anim to="N">` on
`style.fontSize` — the `to` attribute carries a scalar multiplier, not a
`<p:tavLst>` percent value. Isolated font-size anims do not fire.

## Runtime targeting wrappers

When a behavior needs to scope its effect, these children go inside
`<p:spTgt spid="X">`:

| Wrapper                                               | Scope                                      |
| ----------------------------------------------------- | ------------------------------------------ |
| (no child)                                            | Whole shape (fill + stroke + text)         |
| `<p:bg/>`                                             | Shape background only (fill + stroke, excludes text) |
| `<p:txEl><p:pRg st="0" end="0"/></p:txEl>`            | Text paragraph range (first paragraph only) |

Shape fill color change: use `<p:bg/>`. Text-only effects (bold, underline,
text color): use `<p:txEl><p:pRg>`. Effects that apply to both (transparency,
rotate, scale, motion): omit both children.

## Methodology references

- Tune loop: `tools/visual/animation_tune.py` + `tools/visual/pptx_session.py`
- Reference files: `tmp/example{3,4,5,6}.pptx`, `.visual_tmp/samples/experiment 6.pptx`,
  `.visual_tmp/samples/attrsearch example.pptx`
- Oracle corpus (pre-extracted research): `docs/research/powerpoint_oracle/`
- End-to-end stack tests: `.visual_tmp/xmas_tree_v{1,2,3}*.py` (2-par nested,
  1-cTn flat, compound-API flat — all three produce identical animation)

See the commit history under
`git log src/svg2ooxml/assets/animation_oracle/` for the provenance of each
slot, including which reference file was extracted and what the tune loop
showed.
