# Animation Oracle

A library of parameterised PowerPoint animation XML shapes that have been
**empirically verified to actually play in Microsoft PowerPoint**, plus a
catalog of shapes that look valid but are silently dropped at playback.

> **For LLMs:** the companion `pptx-animation` Claude skill at
> `.claude/skills/pptx-animation/` wraps this oracle with CLI scripts
> and auto-generated markdown references. Prefer invoking the skill's
> scripts over loading the oracle Python API directly. Regenerate the
> skill after any SSOT change via `python tools/build_skill.py`.

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

## Three layers

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

### Layer 3 — Flipbook (universal fallback)

**When PPT has no native or compound path for an animation**, the flipbook
renderer pre-renders N keyframes of the animated element as separate shapes
(custGeom vector or embedded PNG), stacks them at the same slide position,
and sequences visibility toggles via timed `<p:set>` pairs on
`style.visibility`.

This is the universal fallback for every animation PPT cannot play natively:

- `animateTransform type="skewX/skewY"` — no native skew primitive
- `animate attributeName="d"` — path morph / shape interpolation
- `animate attributeName="stroke-width"` — silently dropped by PPT
- `animate attributeName="fill-opacity"` — per-layer opacity is dead
- `animate attributeName="stroke-opacity"` — per-layer opacity is dead
- Complex filter parameter animation
- Any transform decomposition that fails (matrix, composed skew)
- `font-size` when the preset-28 compound recipe is impractical

```python
from svg2ooxml.drawingml.animation.oracle import default_oracle

oracle = default_oracle()
par, bld_entries = oracle.instantiate_flipbook(
    frame_shape_ids=[10, 11, 12, 13, 14, 15, 16, 17],
    par_id=4,
    duration_ms=3000,
    delay_ms=0,
)
# bld_entries = [("10", 4), ("11", 4), ...] — emit as:
# <p:bldP spid="10" grpId="4" animBg="1"/>
# <p:bldP spid="11" grpId="4" animBg="1"/>
# ...
```

**Critical structural requirement:** every frame shape's `<p:bldP>` entry
must carry `grpId` matching the animation's `<p:cTn>` group ID (the
`par_id` argument). The standard `build_timing_tree` helper does NOT do
this automatically — the caller must emit `bld_entries` into the
`<p:bldLst>` directly. Mismatched `grpId` causes PPT to silently ignore
the visibility sets.

**How the timing works:**

1. On click, all frames 1..N-1 are immediately hidden (`<p:set>` at
   delay=0 → `style.visibility=hidden`).
2. Frame 0 is shown at delay=0 (already visible, but the set makes it
   explicit).
3. At `frame_dur` ms: frame 0 is hidden, frame 1 is shown.
4. At `2×frame_dur` ms: frame 1 is hidden, frame 2 is shown.
5. ...continues until frame N-1, which holds (no hide set).

**Recommended frame counts:** 12–20 frames for a 2–3s animation gives
125–250ms per frame, which appears smooth to the eye. Higher counts
improve smoothness at the cost of file size (one shape per frame).

**Shapes should be custGeom** (vector-scalable) when possible. Fall back
to embedded PNG only for effects that require raster composition (complex
filters, blend modes). custGeom flipbooks scale cleanly at any zoom level.

Verified end-to-end via `.visual_tmp/flipbook_test2.py`: 8 colored
rectangles cycling through blue→cyan→green→yellow-green→yellow→orange→
red→purple at 500ms per frame. All 8 frames display correctly in
PowerPoint slideshow mode.

### Layer 4 — Morph transition (smooth vertex interpolation)

**When the dead-path animation is the only animation on the slide**, the
Morph slide transition can produce smooth geometry interpolation that the
flipbook cannot: PPT interpolates custGeom vertices between two slides,
morphing one shape into another over the transition duration.

**How it works:**

1. Emit two consecutive slides with identical content (background, static
   shapes, text) — only the animated shape differs between them.
2. Slide A has the shape at keyframe state 0, slide B at keyframe state 1.
3. Wire a Morph transition on slide B with auto-advance (`advTm`) so the
   user never needs to click — the slides flip automatically.
4. The slide boundary is invisible: same background, same static content,
   only the morphing shape moves/deforms.

For multi-keyframe animations (`values="0;30;-30;0"`), emit N+1 slides
with Morph between each consecutive pair. Auto-advance timing on each
slide controls the per-segment duration.

For continuous looping, the last slide auto-advances back to the first.

**Morph transition XML (exact PPT-emitted structure):**

```xml
<mc:AlternateContent
    xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">
  <mc:Choice
      xmlns:p159="http://schemas.microsoft.com/office/powerpoint/2015/09/main"
      Requires="p159">
    <p:transition spd="slow"
        xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"
        p14:dur="2000">
      <p159:morph option="byObject"/>
    </p:transition>
  </mc:Choice>
  <mc:Fallback>
    <p:transition spd="slow">
      <p:fade/>
    </p:transition>
  </mc:Fallback>
</mc:AlternateContent>
```

**Critical:** namespace declarations must be inline on each element, not
hoisted to the `<p:sld>` root. Hoisting causes PPT to trigger a repair
dialog that strips the transition. The `mc:AlternateContent` wrapper is
required — a bare `<p:transition>` with `<p159:morph>` is silently ignored.

**Shape matching:** Morph matches shapes by `name` attribute on
`<p:cNvPr>`. Both slides must use the same shape name for the morphing
shape. Shape IDs may differ.

**Empirical vertex interpolation:** verified that Morph interpolates
custGeom path vertices (not just bounding box position/size). A rectangle
on slide 1 smoothly morphs into a parallelogram (skewX 30°) on slide 2,
with each vertex traveling independently to its target position.

**Covers (when sole animation on slide):**

- Skew animation — rectangle → parallelogram vertex morph
- Path morph (`d` attribute) — any shape → any shape with same vertex count
- Stroke-width — geometry with different stroke widths
- Any vertex-interpolatable geometry change

**When NOT to use:**

- Slide has other native animations (fade, rotate, motion) alongside the
  dead-path animation — Morph would interrupt their timing. Use flipbook.
- Animation has complex multi-keyframe sequences — each keyframe pair
  costs a slide. Beyond 4-5 keyframes, flipbook is more practical.
- Animation repeats indefinitely — slide looping can cause visual hiccups
  on the loop point. Flipbook handles `repeatCount="indefinite"` better.

**Policy rule:** Morph for slides where the dead-path animation is the
ONLY animation. Flipbook for slides with mixed native + dead-path
animations or complex keyframe sequences.

Verified end-to-end via `.visual_tmp/morph_test.py`: blue rectangle on
slide 1 morphs smoothly into a red parallelogram (skewX 30°) on slide 2.
Vertex interpolation confirmed — the top edge shifts right while the
bottom edge stays fixed, producing a true visual skew.

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
  fragment found in the sibling `openxml-audit/docs/pptx_oracle/` corpus.
  Trusted.
- `visually-verified` — confirmed to play correctly in Microsoft PowerPoint
  via `tools/visual/animation_tune.py`. Highest confidence.

Promote templates up this ladder by:

1. Authoring a sample that instantiates the slot
2. Running `.venv/bin/python -m tools.visual.animation_tune <sample_name>`
3. Visually confirming the expected animation plays (not just that pixels
   changed — compare frame 0 to mid/final and verify the *right* change)
4. Updating `verification` and the `notes` field with what you observed

## Empirically falsified paths (DO NOT USE)

The authoritative catalog of XML shapes that PPT's parser accepts but its
playback engine silently drops lives in `dead_paths.xml` as a structured
SSOT. Each entry names the element + attributes of the dead shape, the
empirical source, and a pointer to the verified replacement slot.

```python
oracle = default_oracle()
for dp in oracle.dead_paths():
    print(f"{dp.id}: {dp.element} — verdict={dp.verdict}")
    print(f"  replacement: {dp.replacement_slot}")

dp = oracle.dead_path("anim-fill-opacity")
dp.replacement_slot  # "emph/transparency"
```

Current dead-path entries:

- `anim-fill-opacity` → use `emph/transparency`
- `anim-stroke-opacity` → no native path, EMF fallback only
- `anim-stroke-weight` / `anim-line-weight` → no native path, EMF fallback only
- `anim-style-fontsize-isolated` → requires full preset 28 compound
- `animeffect-image-isolated` → use `emph/transparency` (pair with `<p:set>`)
- `anim-style-opacity-tavlst` → use `emph/transparency` or `entr/fade`/`exit/fade`

Negative-test invariants consume this SSOT: `test_dead_paths_*` tests
assert that every dead-path `attrName` value is NOT in the valid
`attrname_vocabulary.xml` (or, for context-dependent entries like
`style.fontSize`, that the verdict marks it as `requires-compound`).

## attrName vocabulary

The complete set of `<p:attrName>` values that PowerPoint emits natively
lives in `attrname_vocabulary.xml` as a structured SSOT. PowerPoint's
parser accepts additional values (see `dead_paths.xml`) but its playback
engine only honors the 17 listed here.

```python
oracle = default_oracle()
vocab = oracle.attrname_vocabulary()       # tuple[AttrNameEntry, ...]
entry = oracle.attrname_entry("fillcolor") # by-value lookup
oracle.is_valid_attrname("fill.opacity")   # False — see dead_paths.xml
```

The 17-item set, by category:

- **geometry**: `ppt_x`, `ppt_y`, `ppt_w`, `ppt_h`
- **rotation**: `r`, `style.rotation`
- **visibility**: `style.visibility`
- **color**: `fillcolor`, `stroke.color`, `style.color`
- **fill-primer**: `fill.type`, `fill.on`
- **stroke-primer**: `stroke.on`
- **text-formatting**: `style.fontWeight`, `style.textDecorationUnderline`, `style.fontSize`
- **opacity**: `style.opacity`

Each entry's `used_by` field lists which oracle fragments or slots
reference it. To add a new attrName, first verify empirically via the
tune loop that PPT actually animates it (not just that the parser
accepts it), then add a `<attrname>` element to the SSOT.

Negative tests enforce the vocabulary: `test_attrname_vocabulary_complete_17`
will fail if anyone adds, drops, or renames an entry without updating
both the SSOT and the test.

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
- Durable oracle corpus: sibling `openxml-audit/docs/pptx_oracle/`
- Scratch PPTX decks, frame captures, and roundtrip artifacts live under
  ignored `tmp/`, `.visual_tmp/`, or CI artifacts when regenerated
- Starter/oracle deck generators: `tools/visual/powerpoint_oracle_starter_deck.py`
  and `tools/visual/powerpoint_timing_oracle_deck.py`

See the commit history under
`git log src/svg2ooxml/assets/animation_oracle/` for the provenance of each
slot, including which reference file was extracted and what the tune loop
showed.
