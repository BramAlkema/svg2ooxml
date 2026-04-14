# Animation Oracle — Empirical Findings (April 2026)

Captures the knowledge generated during the April 2026 oracle-restructure
session: what XML shapes PowerPoint actually plays, what it silently
drops, the complete vocabulary enumerations, and the structural patterns
that make stacked effects work.

This is a companion to `powerpoint-animation-oracle-ssot.md` (which sets
up the SSOT philosophy). This doc records the *results* of applying that
methodology to a concrete corpus of hand-authored reference files plus
an automated PowerPoint-driver tune loop.

## Methodology recap

1. Hand-author reference animations in PowerPoint for Mac's UI, save as
   `.pptx`, extract the `ppt/slides/slide*.xml` timing tree.
2. Feed each candidate shape through the tune loop
   (`tools/visual/animation_tune.py`) which opens PowerPoint, enters
   slideshow, advances via AppleScript, captures the slideshow window
   via `screencapture`, and computes pixel deltas across frames.
3. Compare the captured deltas against the expected animation to
   classify shapes as `visually-verified` (played on screen) or
   `silently-dropped` (XML accepted, no runtime effect).
4. Record the results in structured XML SSOT files under
   `src/svg2ooxml/assets/animation_oracle/`.

Reference files used:

- `tmp/example.pptx` — initial compound reference (preset 17 entrance +
  preset 6 grow emph + preset 9 transparency)
- `tmp/example3.pptx` — motion path reference
- `tmp/example4.pptx` — 4 emphasis effects (preset 35 blink, preset 7/2
  line color, preset 6 text grow, preset 18 underline)
- `tmp/example5.pptx` — 5 mainSeq effects plus an interactiveSeq with
  preset 28 compound font-size + color
- `tmp/example6.pptx` / `.visual_tmp/samples/experiment 6.pptx` —
  preset 19 shape fill color and preset 27 color pulse
- `tmp/example7.pptx` / `.visual_tmp/samples/experiment 7.pptx` —
  comprehensive 150-animation reference deck covering every
  PowerPoint preset
- `.visual_tmp/samples/attrsearch example.pptx` — user-authored
  transparency + color change reference

## Key empirical findings

### 1. The preset-per-slot model is wrong

PowerPoint's rendering engine does NOT require `presetID` /
`presetSubtype` / `presetClass` to fire animation behaviors. It walks
the `<p:cTn>`'s `childTnLst` and fires every `<p:set>` / `<p:animEffect>`
/ `<p:animClr>` / `<p:animRot>` / `<p:animScale>` / `<p:animMotion>` /
`<p:anim>` child directly. The preset attributes are **cosmetic metadata
for the PowerPoint UI Animation Pane**, not runtime input.

This was verified by authoring an 8-effect stack as two different XML
shapes:

- **v1:** 8 nested `<p:par>` siblings each with its own preset wrapper
  and `nodeType="withEffect"` — 27 total XML elements
- **v2:** 1 `<p:cTn>` with 11 behavior children (no preset attributes) —
  11 total XML elements

Both produced identical animation trajectories (frame-by-frame pixel
match, `delta_max` within 0.05 of each other). The cTn-with-children
shape is structurally trivial and preset-free.

**Consequence:** the universal `emph/compound` slot (empty `<p:cTn>` +
parameterised `<p:childTnLst>`) subsumes every preset-specific emphasis
slot. Handlers compose effects by listing fragments, not by picking
presets.

### 2. The `<p:attrName>` vocabulary is exactly 17 items

Confirmed exhaustive by scanning `tmp/example{4,5,6,7}.pptx` and
`.visual_tmp/samples/experiment {6,7}.pptx` — 400+ authored animations
across 100+ presets. The complete set:

**Geometry:** `ppt_x`, `ppt_y`, `ppt_w`, `ppt_h`
**Rotation:** `r`, `style.rotation`
**Visibility:** `style.visibility`
**Color:** `fillcolor`, `stroke.color`, `style.color`
**Fill primers:** `fill.type`, `fill.on`
**Stroke primers:** `stroke.on`
**Text formatting:** `style.fontWeight`, `style.textDecorationUnderline`,
`style.fontSize`
**Opacity:** `style.opacity`

PowerPoint's XML parser accepts additional attrName values but does not
animate them. The 17 above are the complete runtime vocabulary.

Codified in `src/svg2ooxml/assets/animation_oracle/attrname_vocabulary.xml`.

### 3. Seven empirically falsified paths

XML shapes that parse as valid OOXML but animate nothing at slideshow
time. Each was individually verified to fail via the tune loop:

| Shape                                              | Replacement                               |
|----------------------------------------------------|-------------------------------------------|
| `<p:anim>` on `fill.opacity`                       | `emph/transparency` slot                  |
| `<p:anim>` on `stroke.opacity`                     | EMF rasterization fallback                |
| `<p:anim>` on `stroke.weight`                      | EMF rasterization fallback                |
| `<p:anim>` on `line.weight`                        | EMF rasterization fallback                |
| `<p:anim>` on `style.fontSize` in isolation        | requires full preset 28 compound          |
| `<p:animEffect filter="image">` outside preset 9   | pair with `<p:set>` on `style.opacity`    |
| `<p:anim>` on `style.opacity` with tavLst          | `emph/transparency` (partial range)       |

Notably, `fill.opacity` and `stroke.weight` ARE documented in the
legacy Microsoft binary PowerPoint spec (likely VML remnants) — they
appear valid by ECMA-376 alone, which is why they show up in community
code and hand-written examples. PowerPoint's modern playback engine
does not honor them.

Codified in `src/svg2ooxml/assets/animation_oracle/dead_paths.xml` with
per-entry verdict, source, and replacement guidance. A negative-test
invariant (`test_dead_paths_falsified_attrnames_not_in_valid_vocabulary`)
asserts that every dead-path attrName is NOT in the valid vocabulary.

### 4. Sixteen verified animEffect filters collapse to 2 slots

PowerPoint's entire entrance and exit preset catalog (~40 presets) is
expressed through one XML shape: `<p:animEffect transition="in|out"
filter="X">` where `X` comes from a fixed vocabulary. Verified entries:

```
fade              dissolve
wipe(down)        wipe(up)      wipe(left)       wipe(right)
wedge
wheel(1)          wheel(2)
circle(in)        circle(out)
strips(downLeft)
blinds(horizontal)
checkerboard(across)
barn(inVertical)
randombar(horizontal)
```

All 16 were empirically verified to animate via
`.visual_tmp/filter_sweep.py` — each filter produces its signature
reveal (wipe(down) shows top-down directional reveal, circle(in) shows
elliptical reveal, checkerboard shows checker pattern reveal, etc.).

Direction and spoke sub-parameters are encoded in the filter string
itself (not in `presetSubtype`), so one template handles all
directional variants by changing the token value.

Codified in `src/svg2ooxml/assets/animation_oracle/filter_vocabulary.xml`
as 29 entries (17 visually-verified + 12 derived subparameter variants)
and in the universal `entr/filter_effect.xml` / `exit/filter_effect.xml`
slot templates.

### 5. Targeting wrappers scope effects

PowerPoint uses three distinct target wrappers inside `<p:spTgt>` to
scope an animation:

| Wrapper                                            | Scope                       |
|----------------------------------------------------|-----------------------------|
| (no child)                                         | whole shape (fill+stroke+text) |
| `<p:bg/>`                                          | shape background fill only  |
| `<p:txEl><p:pRg st="0" end="0"/></p:txEl>`         | first text paragraph        |

The `<p:bg/>` variant is the key for **native shape fill color
animation** — our original `emph/color` slot animated `fillcolor`
without `<p:bg/>` and was less reliable than the preset 19 quadruple
primer pattern with `<p:bg/>` scoping. The preset 19 pattern is:

- `<p:animClr>` on `style.color` → target color
- `<p:animClr>` on `fillcolor` → target color
- `<p:set>` on `fill.type` → `"solid"`
- `<p:set>` on `fill.on` → `"true"`

All four as siblings in one `<p:cTn>` with `<p:bg/>` target on every
child. The two `<p:set>` primers ensure the fill is enabled and solid
before the color tween runs.

### 6. Text-paragraph effects require `bldP build="p" rev="1"`

For any effect that targets `<p:txEl><p:pRg>`, the corresponding
`<p:bldP>` entry in the timing's `<p:bldLst>` must have
`build="p" rev="1"` attributes or the effect will not fire. Omitting
this is a common failure mode — the XML parses, PowerPoint opens the
file, but the text effect silently does nothing in slideshow.

Verified for: preset 15 Bold, preset 18 Underline, preset 28 font-size
compound. Whole-shape effects (transparency, rotate, scale, motion,
stroke color, blink) use `animBg="1"` on their bldP entries instead.

### 7. Preset 28 font-size requires compound context

Animating text font size via `<p:anim to="1.5" calcmode="lin"
valueType="num">` on `style.fontSize` does NOT fire in isolation. It
only animates when wrapped in a preset 28 compound alongside:

- `<p:animClr>` on `style.color` (text color change)
- `<p:animClr>` on `fillcolor`
- `<p:set>` on `fill.type` → `"solid"`
- `<p:anim to="N">` on `style.fontSize`

All four as siblings of one cTn. Remove any of the first three and the
font size animation silently stops working. This is codified as a
`requires-compound` verdict in `dead_paths.xml` entry
`anim-style-fontsize-isolated`.

The `to` attribute is a scalar multiplier (`"1.5"` for 150%, `"4"` for
400%), not a PPT fltVal. The scalar form with `to=` is structurally
different from tavLst-based animations.

## Compound stacking demonstration

The `.visual_tmp/xmas_tree_v3_compound.py` script builds an 8-effect
compound using the oracle API:

1. `transparency` (fade to 50%)
2. `fill_color` (green → red via `<p:bg/>` quadruple)
3. `text_color` (white → gold)
4. `bold` (text weight)
5. `underline` (text decoration)
6. `rotate` (720° = 43200000 PPT angle units)
7. `scale` (1.8x)
8. `motion` (diagonal path)

All 8 fire on one click. Verified end-to-end: non-background pixel
share climbs smoothly from 41.95% at frame 0 to 53.60% at frame 17, a
monotonic 11.6-point increase indicating smooth simultaneous
multi-channel animation.

Three structurally-different XML shapes were tested and all produced
identical animation trajectories:

- **v1**: 8 nested `<p:par>` siblings with `nodeType="withEffect"` and
  distinct `grpId`s (27 XML elements)
- **v2**: 1 `<p:cTn>` with 11 direct child behaviors (11 XML elements)
- **v3**: same structure as v2 but assembled via
  `AnimationOracle.instantiate_compound(behaviors=[...])`

Identical `delta_max` (±0.05), identical final frame, identical
intermediate frames. This confirms that (a) preset IDs are cosmetic,
(b) nested par siblings are structurally equivalent to flat cTn
children, and (c) the compound API correctly implements the preset-free
shape.

## Oracle API surface

Resulting from the session's work, the `AnimationOracle` class exposes:

```python
from svg2ooxml.drawingml.animation.oracle import (
    AnimationOracle,
    AttrNameEntry,
    BehaviorFragment,
    DeadPath,
    FilterEntry,
    PresetSlot,
    default_oracle,
)

oracle = default_oracle()

# Layer 1 — preset-specific slot (round-trips through Animation Pane)
par = oracle.instantiate("entr/filter_effect", shape_id="2", par_id=5,
                          duration_ms=1500, FILTER="wipe(down)",
                          PRESET_ID=22, PRESET_SUBTYPE=4,
                          SET_BEHAVIOR_ID=6, EFFECT_BEHAVIOR_ID=7)

# Layer 2 — universal compound (primary path for SMIL→PPT)
par = oracle.instantiate_compound(
    shape_id="2", par_id=5, duration_ms=3000,
    behaviors=[
        BehaviorFragment("transparency", {...}),
        BehaviorFragment("rotate",       {...}),
        BehaviorFragment("motion",       {...}),
    ],
)

# Vocabulary SSOTs
filters = oracle.filter_vocabulary()        # tuple[FilterEntry, ...]
entry   = oracle.filter_entry("wipe(down)") # by-value lookup
attrs   = oracle.attrname_vocabulary()      # tuple[AttrNameEntry, ...]
oracle.is_valid_attrname("fill.opacity")    # False — in dead_paths.xml
dead    = oracle.dead_paths()               # tuple[DeadPath, ...]
dp      = oracle.dead_path("anim-fill-opacity")
```

## Companion Claude skill

The oracle is packaged as a Claude skill at `.claude/skills/pptx-animation/`
assembled by `tools/build_skill.py`. The skill exposes the oracle
through CLI scripts that Claude can invoke via Bash:

- `scripts/emit_entrance.py --shape X --filter F --duration N`
- `scripts/emit_exit.py --shape X --filter F --duration N`
- `scripts/emit_compound.py --shape X --duration N --behaviors '[...]'`
- `scripts/emit_motion.py --shape X --path P --duration N`
- `scripts/validate.py < timing.xml` — walks XML, matches dead_paths.xml
- `scripts/query_vocabulary.py {filter|attrname|dead} [query]`

Markdown references in `references/` are auto-generated from the SSOT
XML files so they cannot drift. The skill is self-contained (vendored
`oracle/` subdirectory) and the build script has a `--check` mode that
fails CI if the in-tree skill differs from what a fresh build would
produce.

## What this does NOT cover

Even the 18-slot + compound + filter_effect oracle does not express
every animation PowerPoint is capable of. Known gaps:

- **`interactiveSeq`** — click-on-shape triggers (as opposed to Next-key
  triggers). Experiment 5/6/7 use these but the oracle slots only emit
  mainSeq clickEffects. SMIL `begin="shape.click"` would need an
  interactiveSeq wrapper.
- **Event-based begin triggers** — `begin="otherAnim.end+2s"` patterns.
  Partially covered by the existing handler codebase but not yet
  surfaced through the oracle API.
- **Iteration sub-parameters** — the compound slot hard-codes
  `<p:iterate type="lt"><p:tmAbs val="0"/>` (no stagger). For
  per-letter cascades with non-zero stagger (bold, underline's real
  behavior), the compound's outer iterate would need tokenisation.
- **Stroke-width animation** — structurally impossible in native PPT;
  requires EMF rasterization fallback in the full pipeline.
- **Text-only transparency** — `style.opacity` on text is structurally
  different from shape transparency and has not been individually
  verified.

These are tracked as follow-up work. The current oracle is sufficient
for the common SMIL→PPT mappings and for LLM-driven authoring via the
skill.

## Provenance

Every verified slot carries a `verification` field in `index.json`
(`visually-verified`, `oracle-matched`, or `derived-from-handler`) plus
a `source` field naming the reference file and capture script. Every
dead-path entry carries a `source` field with the empirical test that
confirmed the failure. Negative-test invariants in
`tests/unit/drawingml/animation/test_oracle.py` enforce that the
vocabularies and dead-paths cannot silently drift.
