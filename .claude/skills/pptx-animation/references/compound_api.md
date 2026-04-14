# Compound API — Behavior Fragment Catalog

The compound slot (`emph/compound.xml`) is the primary way to author
multi-effect PowerPoint animations. It's a bare `<p:par>`/`<p:cTn>`
wrapper with an empty `childTnLst` — callers fill it by listing
**behavior fragments** from `oracle/emph/behaviors/`.

Every fragment file is one or more raw
`<p:set>`/`<p:animEffect>`/`<p:animClr>`/`<p:animRot>`/`<p:animScale>`/
`<p:animMotion>`/`<p:anim>` elements. When you call
`emit_compound.py --behaviors '[...]'` or
`AnimationOracle.instantiate_compound(behaviors=[...])`, each fragment
is token-substituted and appended to the compound's `childTnLst` as
direct siblings. They all fire simultaneously on one click.

Shape IDs and durations propagate automatically. Per-fragment tokens
(behavior IDs, colors, paths, scales, etc.) are supplied in the
`tokens` dict passed to each `BehaviorFragment`.

## Fragment list

### `transparency`

Fades the whole shape (fill + stroke + text together) to a partial
opacity and holds. Uses `<p:set>` on `style.opacity` paired with
`<p:animEffect filter="image" prLst="opacity: X">`.

**Tokens:**
- `SET_BEHAVIOR_ID` — inner cTn id for the `<p:set>`
- `EFFECT_BEHAVIOR_ID` — inner cTn id for the `<p:animEffect>`
- `TARGET_OPACITY` — decimal string like `"0.5"` (NOT a PPT fltVal)

**Example:**
```json
{"name": "transparency", "tokens": {"SET_BEHAVIOR_ID": 10, "EFFECT_BEHAVIOR_ID": 11, "TARGET_OPACITY": "0.5"}}
```

### `fill_color`

Changes the shape fill color (background only, excluding text). Emits
the preset 19 quadruple primer: `<p:animClr>` on `style.color` +
`<p:animClr>` on `fillcolor` + `<p:set>` on `fill.type`→solid +
`<p:set>` on `fill.on`→true. All targeting `<p:bg/>`.

**Tokens:**
- `STYLE_CLR_BEHAVIOR_ID` — cTn id for the style.color animClr
- `FILL_CLR_BEHAVIOR_ID` — cTn id for the fillcolor animClr
- `FILL_TYPE_BEHAVIOR_ID` — cTn id for the fill.type set
- `FILL_ON_BEHAVIOR_ID` — cTn id for the fill.on set
- `TO_COLOR` — 6-hex srgbClr value (no `#` prefix), e.g. `"C81010"`

**Example:**
```json
{"name": "fill_color", "tokens": {"STYLE_CLR_BEHAVIOR_ID": 20, "FILL_CLR_BEHAVIOR_ID": 21, "FILL_TYPE_BEHAVIOR_ID": 22, "FILL_ON_BEHAVIOR_ID": 23, "TO_COLOR": "C81010"}}
```

### `text_color`

Changes the text color inside a shape. Single `<p:animClr>` on
`style.color` with `override="childStyle"`, targeting the whole shape.
Distinct from `fill_color` which targets `<p:bg/>`.

**Tokens:**
- `BEHAVIOR_ID`
- `TO_COLOR` — 6-hex srgbClr value

**Example:**
```json
{"name": "text_color", "tokens": {"BEHAVIOR_ID": 30, "TO_COLOR": "FFD700"}}
```

### `stroke_color`

Changes the shape line (stroke) color. `<p:animClr>` on `stroke.color`
paired with `<p:set>` on `stroke.on`→true (primer to ensure the stroke
is visible). Whole-shape target.

**Tokens:**
- `CLR_BEHAVIOR_ID` — cTn id for the animClr
- `SET_BEHAVIOR_ID` — cTn id for the stroke.on set
- `TO_COLOR` — 6-hex srgbClr value

### `bold`

Sets `style.fontWeight` to `"bold"` on the first text paragraph. Uses
`<p:cBhvr override="childStyle">` with `<p:txEl><p:pRg st="0" end="0"/>`
target. Per-letter stagger via `<p:iterate type="lt"><p:tmAbs val="25"/>`
built into the fragment (25ms stagger for typewriter effect).

**Tokens:**
- `BEHAVIOR_ID`

**Note:** Requires `bldP build="p" rev="1"` for text-paragraph scope
— the build_skill.py script and compound slot handle this automatically.

### `underline`

Sets `style.textDecorationUnderline` to `"true"` with per-letter
cascade. Same shape as `bold` but with `tmPct="4000"` (40% stagger).

**Tokens:**
- `BEHAVIOR_ID`

### `blink`

Discrete two-keyframe animation on `style.visibility`. Whole-shape,
no iterate. Hides at tm=0, shows at tm=50000 (half).

**Tokens:**
- `BEHAVIOR_ID`

### `rotate`

Rotates the whole shape via `<p:animRot by="N">` on the `r` attribute.

**Tokens:**
- `BEHAVIOR_ID`
- `ROTATION_BY` — PPT angle units (60000 per degree). 360° = 21600000;
  720° = 43200000.

### `scale`

Scales the whole shape via `<p:animScale>` with `<p:by x="X" y="Y">`.
Scale values in hundred-thousandths (100000 = 100%).

**Tokens:**
- `BEHAVIOR_ID`
- `BY_X` — e.g. `"150000"` for 150%
- `BY_Y` — e.g. `"150000"` for 150%

### `motion`

Moves the shape along a motion path via `<p:animMotion>`.

**Tokens:**
- `BEHAVIOR_ID`
- `PATH_DATA` — PPT motion path string in slide-relative coordinates
  (0..1 range), e.g. `"M 0 0 L 0.25 0.5 E"` (move 25% right, 50% down).
  Commands: M=moveto, L=lineto, C=curveto, E=end.

## Full example: 8-effect stack

One click, all eight play simultaneously:

```bash
python scripts/emit_compound.py \
  --shape 2 --duration 3000 --par-id 5 \
  --behaviors '[
    {"name": "transparency", "tokens": {"SET_BEHAVIOR_ID": 10, "EFFECT_BEHAVIOR_ID": 11, "TARGET_OPACITY": "0.5"}},
    {"name": "fill_color",   "tokens": {"STYLE_CLR_BEHAVIOR_ID": 20, "FILL_CLR_BEHAVIOR_ID": 21, "FILL_TYPE_BEHAVIOR_ID": 22, "FILL_ON_BEHAVIOR_ID": 23, "TO_COLOR": "C81010"}},
    {"name": "text_color",   "tokens": {"BEHAVIOR_ID": 30, "TO_COLOR": "FFD700"}},
    {"name": "bold",         "tokens": {"BEHAVIOR_ID": 40}},
    {"name": "underline",    "tokens": {"BEHAVIOR_ID": 50}},
    {"name": "rotate",       "tokens": {"BEHAVIOR_ID": 60, "ROTATION_BY": "43200000"}},
    {"name": "scale",        "tokens": {"BEHAVIOR_ID": 70, "BY_X": "180000", "BY_Y": "180000"}},
    {"name": "motion",       "tokens": {"BEHAVIOR_ID": 80, "PATH_DATA": "M 0 0 L 0.15 0.2 E"}}
  ]'
```

This shape is verified end-to-end — see
`.visual_tmp/xmas_tree_v3_compound.py` in the svg2ooxml repository.
Frame 0 shows the initial shape; frame 17 shows the compound end state
(red rectangle faded to 50%, scaled 1.8x, text in bold underlined gold,
rotated 720° back to 0°, moved down-right along the path).

## Token conflict resolution

Give each fragment **distinct** behavior IDs. PowerPoint doesn't allow
duplicate cTn ids within one timing tree — if two fragments both use
`BEHAVIOR_ID: 10` the XML will fail to parse. Convention: use
monotonic blocks (10-19 for fragment 1, 20-29 for fragment 2, etc.).
