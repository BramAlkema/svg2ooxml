# Dead Paths — Do Not Use

XML shapes that PowerPoint's parser accepts but its playback engine
silently drops at slideshow time. Every entry below has been
empirically verified to fail via the tune loop.

Auto-generated from `oracle/dead_paths.xml` — do not hand-edit.

Loaded programmatically via:

```python
from svg2ooxml.drawingml.animation.oracle import default_oracle
oracle = default_oracle()
paths = oracle.dead_paths()        # tuple[DeadPath, ...]
dp = oracle.dead_path('anim-fill-opacity')  # lookup by id
```

Use `scripts/validate.py` to check arbitrary XML against this catalog:

```bash
cat some_timing.xml | python scripts/validate.py
```

## Entries

### `anim-fill-opacity`

**Shape:** `p:anim` with `attrName=fill.opacity`

**Verdict:** `silently-dropped`

**Source:** .visual_tmp/transparency_experiment.py; legacy VML attrName from binary PPT spec

Attempted to animate shape fill opacity via p:anim on fill.opacity
      attrName with a fltVal tavLst. PPT parses the XML as valid OOXML but
      the playback engine drops the animation entirely — the shape renders
      at its authored opacity with zero transition.

**Replacement slot:** `emph/transparency`

Use preset 9 Transparency — p:set style.opacity + p:animEffect filter="image" prLst="opacity: X" in one cTn. This is the native shape fill opacity path PPT actually honors.

### `anim-stroke-opacity`

**Shape:** `p:anim` with `attrName=stroke.opacity`

**Verdict:** `silently-dropped`

**Source:** .visual_tmp/transparency_experiment.py; legacy VML attrName

Attempted to animate shape stroke opacity via p:anim on stroke.opacity.
      Legacy VML attrName; no modern PPT animation primitive exists for
      partial-range stroke opacity.

**Replacement slot:** `none`

No native path. For SVG animate[stroke-opacity] fall back to EMF rasterization. Binary 0-or-1 stroke opacity can be approximated by toggling stroke.on via p:set.

### `anim-stroke-weight`

**Shape:** `p:anim` with `attrName=stroke.weight`

**Verdict:** `silently-dropped`

**Source:** .visual_tmp/transparency_experiment.py stroke_weight candidate; research notes on VML legacy

Attempted to animate shape stroke (line) width via p:anim on
      stroke.weight. ECMA-376 documents stroke.weight as an animatable
      attribute but PowerPoint's modern playback engine silently drops it.
      The LineFormat.Weight VBA property exists for static formatting only.

**Replacement slot:** `none`

No native path. For SVG animate[stroke-width] fall back to EMF rasterization or discrete set steps via static LineFormat.Weight. Fundamentally impossible as an interpolated animation in current PPT.

### `anim-line-weight`

**Shape:** `p:anim` with `attrName=line.weight`

**Verdict:** `silently-dropped`

**Source:** .visual_tmp/transparency_experiment.py

Alternate spelling of stroke.weight. Also silently dropped — PPT's
      attrName resolver accepts either but neither fires at playback.

**Replacement slot:** `none`

Same as stroke.weight — no native path, EMF fallback only.

### `anim-style-fontsize-isolated`

**Shape:** `p:anim` with `attrName=style.fontSize`

**Context:** without sibling animClr/animClr/set children in the same cTn

**Verdict:** `requires-compound`

**Source:** .visual_tmp/transparency_experiment.py font_size retest — 3 iterations across simple, full-compound, and final working (to="4" for visibility) configurations

Attempted to animate text font size via a lone p:anim to="1.5" on
      style.fontSize inside a standalone clickEffect wrapper. Does NOT fire
      in isolation. PPT only honors style.fontSize when it appears alongside
      the full preset 28 compound (animClr on style.color + animClr on
      fillcolor + set on fill.type + anim on style.fontSize) as sibling
      children of ONE cTn. Remove any of the siblings and the font size
      animation silently stops working.

**Replacement slot:** `emph/compound with fill_color + custom anim-style.fontSize child`

When SVG requires text font-size animation, emit the full preset 28 compound: use emph/compound + fill_color fragment + a raw style.fontSize anim child. Size-only animations (no color change) are NOT supported natively.

### `animeffect-image-isolated`

**Shape:** `p:animEffect` with `filter=image`, `prLst=opacity: X`

**Context:** outside preset 9 Transparency wrapper (no paired p:set style.opacity)

**Verdict:** `silently-dropped`

**Source:** .visual_tmp/transparency_experiment.py transparency_pulse with autoRev — emitted the animEffect but not the paired set; animation did not fire

The animEffect filter="image" element with prLst="opacity: X" is
      NOT a standalone entrance/exit effect. It only fires when paired with
      a p:set on style.opacity (to the same target value) inside a preset 9
      Transparency cTn. Using the filter in any other preset wrapper or
      without the paired set results in the shape rendering at its current
      opacity with no transition.

**Replacement slot:** `emph/transparency`

Always pair p:animEffect filter="image" prLst="opacity: X" with a p:set on style.opacity → "X" in the same cTn. The emph/transparency oracle slot bakes this pairing in.

### `anim-style-opacity-tavlst`

**Shape:** `p:anim` with `attrName=style.opacity`

**Context:** with p:tavLst keyframes (interpolated partial-range tween)

**Verdict:** `silently-dropped`

**Source:** .visual_tmp/transparency_experiment.py opacity_property candidate

Attempted to animate shape opacity by emitting p:anim on style.opacity
      with a p:tavLst containing fltVal keyframes (e.g. from 0.2 to 1.0).
      style.opacity accepts p:set for instantaneous values (used as the
      preset 9 Transparency primer) but rejects p:anim-with-tavLst at
      playback. Legacy attrName from binary PPT spec.

**Replacement slot:** `emph/transparency (partial range) or entr/fade / exit/fade (0↔1 range)`

For partial-range opacity holds use emph/transparency. For full 0→1 or 1→0 fade use entr/filter_effect FILTER=fade or exit/filter_effect FILTER=fade.
