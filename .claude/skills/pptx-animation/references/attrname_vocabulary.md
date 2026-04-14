# attrName Vocabulary

The 17 `<p:attrName>` values PowerPoint emits natively. Confirmed
exhaustive by scanning 400+ authored animations across reference decks.
Auto-generated from `oracle/attrname_vocabulary.xml` — do not hand-edit.

Loaded programmatically via:

```python
from svg2ooxml.drawingml.animation.oracle import default_oracle
oracle = default_oracle()
vocab = oracle.attrname_vocabulary()    # tuple[AttrNameEntry, ...]
entry = oracle.attrname_entry('fillcolor')
oracle.is_valid_attrname('fill.opacity')  # False — see dead_paths.md
```

## geometry

### `ppt_x`

- **Scope:** whole-shape
- **Verification:** visually-verified
- **Used by:** legacy imperative position handler

Shape left edge, in EMUs. Animated via p:anim with numeric tavLst for arbitrary paths; preferred over animMotion for simple single-axis position tweens.

### `ppt_y`

- **Scope:** whole-shape
- **Verification:** visually-verified
- **Used by:** legacy imperative position handler

Shape top edge, in EMUs. Animated via p:anim with numeric tavLst.

### `ppt_w`

- **Scope:** whole-shape
- **Verification:** visually-verified
- **Used by:** legacy imperative size handler; emph/behaviors/scale.xml

Shape width, in EMUs. Animated via p:anim or p:animScale. animScale is the preset-preserving path (preset 6 Grow/Shrink); direct p:anim is used when width/height must be decoupled from the shape's center point.

### `ppt_h`

- **Scope:** whole-shape
- **Verification:** visually-verified
- **Used by:** legacy imperative size handler; emph/behaviors/scale.xml

Shape height, in EMUs. Paired with ppt_w for size animations.

## rotation

### `r`

- **Scope:** whole-shape
- **Verification:** visually-verified
- **Used by:** emph/behaviors/rotate.xml; path/motion (via rAng auto-rotate)

Shape rotation in PPT angle units (60000 per degree). Animated via p:animRot by="N" with cBhvr targeting. 720° = 43200000.

### `style.rotation`

- **Scope:** text
- **Verification:** derived-from-handler
- **Used by:** not yet wired into any oracle fragment

Text rotation independent of the containing shape's rotation. Used by a small number of text-specific rotate emphasis presets. Rarely needed; the shape-level 'r' attribute is the primary rotation path.

## visibility

### `style.visibility`

- **Scope:** whole-shape
- **Verification:** visually-verified
- **Used by:** entr/appear.xml, entr/fade.xml (primer), exit/fade.xml (tail), entr/filter_effect.xml (primer), exit/filter_effect.xml (tail), emph/behaviors/blink.xml

Shape visibility toggle, set to "visible" or "hidden". Fired as an instantaneous p:set for appear/disappear transitions, or as a discrete p:anim with two tavLst keyframes for blink effects (hidden → visible at tm=50000).

## color

### `fillcolor`

- **Scope:** shape-background
- **Verification:** visually-verified
- **Used by:** emph/color.xml (legacy), emph/shape_fill_color.xml, emph/color_pulse.xml, emph/behaviors/fill_color.xml

Shape fill color. Animated via p:animClr with srgbClr or schemeClr targets. Typically paired with fill.on and fill.type primers to ensure a solid enabled fill before the color tween runs. When targeting shape background only, wrap the spTgt with <p:bg/>.

### `stroke.color`

- **Scope:** whole-shape
- **Verification:** visually-verified
- **Used by:** emph/stroke_color.xml, emph/behaviors/stroke_color.xml

Shape line color. Animated via p:animClr with srgbClr or schemeClr targets. Paired with a stroke.on primer to ensure the stroke is visible before the color tween runs.

### `style.color`

- **Scope:** text-or-shape
- **Verification:** visually-verified
- **Used by:** emph/text_color.xml, emph/shape_fill_color.xml, emph/color_pulse.xml, emph/behaviors/text_color.xml, emph/behaviors/fill_color.xml

Text run color OR shape text color, depending on target wrapper. When spTgt has <p:txEl><p:pRg/></p:txEl> the target is a text paragraph (preset 3 Change Font Color); when spTgt has <p:bg/> it is part of the preset 19 shape fill compound. Requires <p:cBhvr override="childStyle"> when animating text.

## fill-primer

### `fill.type`

- **Scope:** shape-background
- **Verification:** visually-verified
- **Used by:** emph/shape_fill_color.xml, emph/color_pulse.xml, emph/behaviors/fill_color.xml

Primer set value "solid" that ensures the fill is a solid color before fillcolor tweens. Fires as p:set with duration matching the outer effect. Never animated on its own.

### `fill.on`

- **Scope:** shape-background
- **Verification:** visually-verified
- **Used by:** emph/shape_fill_color.xml, emph/color_pulse.xml, emph/behaviors/fill_color.xml

Primer set value "true" that ensures the fill is enabled before fillcolor tweens. Fires as p:set with duration matching the outer effect.

## stroke-primer

### `stroke.on`

- **Scope:** whole-shape
- **Verification:** visually-verified
- **Used by:** emph/stroke_color.xml, emph/behaviors/stroke_color.xml

Primer set value "true" that ensures the stroke is enabled before stroke.color tweens. Fires as p:set with duration matching the outer effect.

## text-formatting

### `style.fontWeight`

- **Scope:** text
- **Verification:** visually-verified
- **Used by:** emph/bold.xml, emph/behaviors/bold.xml

Text weight, set to "bold" for the preset 15 Bold emphasis. Fires as p:set with dur="indefinite". Requires <p:cBhvr override="childStyle"> and text paragraph target (p:txEl/p:pRg) plus bldP build="p" rev="1".

### `style.textDecorationUnderline`

- **Scope:** text
- **Verification:** visually-verified
- **Used by:** emph/underline.xml, emph/behaviors/underline.xml

Text underline toggle, set to "true" for the preset 18 Underline emphasis. Fires as p:set with dur="500" fill="hold". Per-letter stagger via p:iterate tmPct="4000" (40% between letters) for a typewriter effect.

### `style.fontSize`

- **Scope:** text
- **Verification:** visually-verified
- **Used by:** not yet wired into a standalone oracle fragment — see dead_paths.xml for isolation caveat

Text font size scale, animated via p:anim to="N" with a scalar multiplier (e.g. "4" for 4x). ONLY works as a child of the preset 28 compound emphasis alongside other child behaviors (animClr + animClr + set + anim). In isolation under any other preset the animation is silently dropped. Requires override="childStyle" and bldP build="p" rev="1".

## opacity

### `style.opacity`

- **Scope:** whole-shape
- **Verification:** visually-verified
- **Used by:** emph/transparency.xml, emph/behaviors/transparency.xml

Shape opacity set value (e.g. "0.5"). Used as a primer for preset 9 Transparency emphasis, paired with p:animEffect filter="image" prLst="opacity: X" which is the actual opacity carrier. Standalone p:anim on style.opacity with a tavLst does NOT fire — see dead_paths.xml.
