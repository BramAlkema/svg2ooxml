# SVG Animation Native PowerPoint Mapping Specification

- **Status:** Draft
- **Date:** 2026-04-14
- **Documentation map:** `docs/internals/animation-documentation-map.md`
- **Scope:** native-only SVG/SMIL animation mapping into PowerPoint timing XML
- **Primary Fixtures:** `tests/svg/animate-*.svg`, `tests/svg/color-prop-*.svg`, `tests/svg/coords-transformattr-*.svg`
- **Primary Modules:**
  - `src/svg2ooxml/core/animation/parser.py`
  - `src/svg2ooxml/ir/animation.py`
  - `src/svg2ooxml/drawingml/animation/writer.py`
  - `src/svg2ooxml/drawingml/animation/xml_builders.py`
  - `src/svg2ooxml/drawingml/animation/native_matcher.py`
  - `src/svg2ooxml/drawingml/animation/handlers/`
  - `src/svg2ooxml/drawingml/animation/policy.py`

## 1. Purpose

The parser now preserves all animation elements in the W3C animation-focused
fixture set: 79 scenarios, 646 animation elements, 646 IR definitions, and no
parser degradations.

This spec defines how much of that IR can be matched to editable native
PowerPoint timing XML, and which remaining SVG features may only be mimicked.

This document owns the mapping contract: match levels, primitive selection,
policy rules, and verification expectations for native emission claims. It does
not own the broader fidelity program (`docs/specs/powerpoint-fidelity-phase-2.md`)
or the structural cleanup direction (`docs/specs/animation-cleanup-rigour-spec.md`).

Rasterization, frame fallback, movie export, and non-native fallback are out of
scope for this spec.

## 2. Match Levels

| Level | Meaning | Native-only? | Use in policy |
| --- | --- | --- | --- |
| `exact-native` | PowerPoint has a timing primitive with equivalent runtime semantics. | yes | preferred |
| `composed-native` | Equivalent result can be built from multiple native timing primitives. | yes | preferred when visually stable |
| `mimic-native` | A native PowerPoint effect can approximate the visual result but not the full SVG semantics. | yes | allowed only with explicit reason |
| `expand-native` | Precompute SVG semantics into several native effects or samples. Editable but not semantically compact. | yes | allowed when deterministic |
| `metadata-only` | Preserve in IR/export metadata, but do not emit an attempted native effect yet. | yes | no visual claim |
| `unsupported-native` | No credible editable PowerPoint native equivalent. | yes | report and skip |
| `flipbook` | Pre-render N keyframes as stacked shapes, sequence with `<p:set>` visibility toggles. | yes | universal fallback for dead paths |
| `morph-transition` | Duplicate slide with Morph transition for smooth vertex interpolation between two shape states. | yes | preferred over flipbook when sole animation on slide |

`mimic-native` means “may be approximated by native PowerPoint effects.” It does
not mean raster fallback.

`flipbook` means “the animation cannot be expressed through any PPT animation
primitive, but the visual result can be reproduced by cycling through
pre-rendered static frames.” Shapes should be custGeom (vector) when possible.
The oracle's `instantiate_flipbook()` method generates the timing XML.
Visually verified with 8-frame color cycling test.

`morph-transition` means “the animation can be expressed as smooth vertex
interpolation between two shape states using PPT's Morph slide transition.”
Requires duplicating the slide — all static content stays identical, only the
animated shape differs. Produces continuous interpolation (no discrete steps)
but consumes slides and cannot coexist with other in-slide animations.
Use when the dead-path animation is the sole animation on the slide.
Visually verified with rectangle → parallelogram skew morph.

## 3. PowerPoint Native Primitive Inventory

| PowerPoint primitive | Native use | Notes |
| --- | --- | --- |
| `<p:anim>` + `<p:tavLst>` | Generic property animation. | Best for numeric properties and opacity properties. |
| `<p:animClr>` | Color tween. | No native TAV list; multi-keyframes need segmentation. |
| `<p:animMotion>` | Motion path. | Supports editable paths; SVG coordinate normalization is the hard part. |
| `<p:animScale>` | Grow/shrink scale. | Scales around shape center; SVG width/height often need anchor compensation. |
| `<p:animRot>` | Rotation. | Rotation center mismatch may require composed motion. |
| `<p:animEffect filter="fade">` | Authored fade in/out. | Good for simple whole-shape opacity fade. |
| `<p:animEffect>` entrance/exit presets | Wipe, appear, disappear, emphasis effects. | Useful mimic path for reveal/hide/line drawing. |
| `<p:set>` | Discrete property set. | Best for visibility and categorical jumps. |
| `<p:cTn>` | Duration, fill, repeat, auto reverse, restart, grouping. | Needs oracle verification for some attrs. |
| `<p:stCondLst>` | Begin conditions. | Time, click, element begin/end are practical. |
| `<p:endCondLst>` | End conditions. | Required for SMIL `end`; not wired yet. |
| `<p:seq>` / nested `<p:par>` | Sequencing/segmentation. | Required for keyframes and discrete jumps. |

## 4. Animation Element Mapping

| SVG element | Input forms | PowerPoint strategy | Level | Mimic? | Status |
| --- | --- | --- | --- | --- | --- |
| `<animate>` numeric position | `x`, `y`, `cx`, `cy`, `from/to/by/values` | `<p:animMotion>` relative path. | `exact-native` for simple one-axis; `composed-native` for x+y coalescing | no | partially implemented |
| `<animate>` numeric size | `width`, `height`, `w`, `h`, `rx`, `ry` | `<p:animScale>` plus anchor `<p:animMotion>`. | `composed-native` | no | partially implemented |
| `<animate>` generic numeric | `stroke-width`, numeric style attrs | `<p:anim>` with TAV values. | `exact-native` when PPT property exists | no | partially implemented |
| `<animate>` opacity | `opacity` | Simple 0->1/1->0 uses fade effect; complex uses `<p:anim>` on `style.opacity`. | `exact-native` / `composed-native` | no | implemented for core cases |
| `<animate>` paint opacity | `fill-opacity`, `stroke-opacity` | `<p:anim>` on `fill.opacity` / `stroke.opacity`. | `exact-native` if PPT honors property on target | no | implemented |
| `<animate>` color | `fill`, `stroke`, selected color attrs | `<p:animClr>` or segmented `<p:animClr>`/`<p:set>`. | `exact-native` for simple shape colors; `expand-native` for keyframes | no | partially implemented |
| `<animate>` visibility | `visibility` | `<p:set>` on `style.visibility`. | `exact-native` for leaf visibility | no | implemented for compiled cases |
| `<animate>` display | `display` | Compile render-tree state into descendant `style.visibility` sets. | `composed-native` | no | partially implemented |
| `<animate>` path geometry | `d`, `points`, polygon/polyline data | No direct shape morph primitive in current profile. Could sample as motion/scale only for special cases. | `metadata-only` or `mimic-native` | yes | not implemented |
| `<animateTransform>` translate | `type="translate"` | `<p:animMotion>` path. | `exact-native` for simple transforms; `expand-native` for keyframes | no | partially implemented |
| `<animateTransform>` scale | `type="scale"` | `<p:animScale>` plus center/anchor compensation. | `composed-native` | no | partially implemented |
| `<animateTransform>` rotate | `type="rotate"` | `<p:animRot>`; orbit motion if SVG rotation center differs. | `exact-native` / `composed-native` | no | partially implemented |
| `<animateTransform>` skew | `type="skewX/skewY"` | No general native editable skew animation. Possible mimic with sampled geometry or sheared static variants. | `mimic-native` | yes | not implemented |
| `<animateTransform>` matrix | `type="matrix"` | Decompose into translate/scale/rotate when possible; otherwise unsupported. | `composed-native` or `metadata-only` | maybe | not implemented |
| `<animateMotion>` path | `path`, `values`, `from/to/by` | `<p:animMotion path="...">`. | `exact-native` when path conversion is valid | no | partially implemented |
| `<animateMotion>` mpath | `<mpath href="#path">` | Resolve referenced path then emit `<p:animMotion>`. | `exact-native` when reference resolves | no | implemented in parser, partial writer |
| `<animateMotion>` rotate | `rotate="auto"`, `auto-reverse`, angle | `rAng` when constant; sampled rotation for auto tangent. | `composed-native` or `mimic-native` | yes for tangent approximation | partial |
| `<animateColor>` | same as color animate | `<p:animClr>` / segmented color. | `exact-native` / `expand-native` | no | partially implemented |
| `<set>` numeric/string | `to` value | `<p:set>` when PPT property exists. | `exact-native` | no | partially implemented |
| `<set>` display/visibility | `display`, `visibility` | Visibility compiler to `style.visibility`. | `composed-native` | no | partially implemented |

## 5. Value Form Mapping

| SVG value form | Native strategy | Level | Mimic? | Notes |
| --- | --- | --- | --- | --- |
| `values="a;b;c"` | TAV list or segmented native effects. | `exact-native` / `expand-native` | no | Depends on primitive. |
| `from` + `to` | Direct from/to native primitive. | `exact-native` | no | Best-supported form. |
| `from` + `by` | Derive endpoint, emit from/to. | `exact-native` for numeric values | no | Non-numeric remains raw metadata. |
| `to` + `by` | Derive startpoint for numeric values. | `exact-native` for numeric values | no | Parser preserves raw form too. |
| `by` only | Relative delta. | `composed-native` if base value known; otherwise `metadata-only` | maybe | Needs target-state resolver in writer. |
| `to` only | Resolve underlying target attr/style when available. | `exact-native` when underlying value resolves | no | Required for W3C discrete to-animation. |
| mixed units | Normalize into EMU/PPT value space. | `exact-native` when unit conversion is deterministic | no | Percent/object-bbox cases may need policy. |
| color keywords/rgb/hex | Normalize to sRGB. | `exact-native` for flat sRGB | no | ICC/currentColor/system colors are harder. |
| `inherit` / `currentColor` | Resolve before animation emission. | `composed-native` | no | Should be resolved in style cascade layer. |

## 6. Timing Mapping

| SVG timing feature | PowerPoint strategy | Level | Mimic? | Status |
| --- | --- | --- | --- | --- |
| `begin="0s"`, offsets | `<p:stCondLst><p:cond delay="...">`. | `exact-native` | no | implemented |
| `begin="click"` | `evt="onClick"` on default target. | `exact-native` | no | implemented |
| `begin="shape.click"` | `evt="onClick"` with target shape. | `exact-native` | no | implemented when target maps |
| `begin="anim.begin"` | `evt="onBegin"` condition. | `exact-native` if PPT references work reliably | no | partial |
| `begin="anim.end"` | `evt="onEnd"` condition. | `exact-native` if PPT references work reliably | no | partial |
| `begin="indefinite"` | No direct free-standing equivalent; bookmark click can remap to click. | `composed-native` for bookmark case | yes outside bookmark case | partial |
| `begin="base.repeat(n)"` | Rewrite deterministic integer repeat events to absolute time offsets when the base timing is resolvable. | `expand-native` for integer `n`, otherwise `metadata-only` | maybe outside deterministic subset | partial |
| `begin="accessKey(a)"` | No PowerPoint keyboard trigger equivalent in normal slideshow XML. | `unsupported-native` | no | parsed and explicitly skipped by policy |
| `begin="wallclock(...)"` | No useful deck-local runtime equivalent. | `unsupported-native` | no | parsed and explicitly skipped by policy |
| generic DOM events | No PowerPoint DOM event model. | `unsupported-native` | no | parsed and explicitly skipped by policy |
| multiple begin tokens | Emit multiple start conditions where native-compatible. | `exact-native` / `metadata-only` mixed | maybe | partial |
| `dur` | `<p:cTn dur="...">`. | `exact-native` | no | implemented |
| `dur="indefinite"` | Long duration or wait-state; no exact finite slide behavior. | `mimic-native` | yes | partial |
| `end` time offset | `<p:endCondLst>`. | `exact-native` | no | wired; probe with `openxml_audit.pptx.timing_oracle_deck` / `openxml-audit-pptx-timing-oracle` |
| `end` click/element refs | `<p:endCondLst>` event conditions. | `exact-native` | no | wired; probe with `openxml_audit.pptx.timing_oracle_deck` / `openxml-audit-pptx-timing-oracle` |
| `repeatCount="n"` | `<p:cTn repeatCount="{n * 1000}">`; fractional counts are lowered to a repeat-duration cap. | `exact-native` for integer `n`, `expand-native` for fractional `n` | no | implemented |
| `repeatCount="indefinite"` | `repeatCount="indefinite"`. | `exact-native` | no | implemented where passed through |
| `repeatDur` | `repeatDur` on repeating `<p:cTn>` nodes. | `exact-native` candidate | maybe | wired; probe with `openxml_audit.pptx.timing_oracle_deck` / `openxml-audit-pptx-timing-oracle` |
| `fill="freeze"` | `fill="hold"` / final segment hold. | `exact-native` | no | partially implemented |
| `fill="remove"` | `fill="remove"` / omit final hold. | `exact-native` | no | partially implemented |
| `restart="always"` | `restart` attr on outer `<p:cTn>`. | `exact-native` candidate | maybe | wired; probe with `openxml_audit.pptx.timing_oracle_deck` / `openxml-audit-pptx-timing-oracle` |
| `restart="whenNotActive"` | `restart` attr on outer `<p:cTn>`. | `exact-native` candidate | maybe | wired; probe with `openxml_audit.pptx.timing_oracle_deck` / `openxml-audit-pptx-timing-oracle` |
| `restart="never"` | `restart` attr on outer `<p:cTn>`. | `exact-native` candidate | maybe | wired; probe with `openxml_audit.pptx.timing_oracle_deck` / `openxml-audit-pptx-timing-oracle` |
| `min`, `max` | Possible timing attrs but not validated. | `metadata-only` | maybe with clamping | parser only |

## 7. Interpolation Mapping

| SVG interpolation feature | PowerPoint strategy | Level | Mimic? | Notes |
| --- | --- | --- | --- | --- |
| `calcMode="linear"` | Native from/to, TAV linear values, or segment durations. | `exact-native` | no | should be preferred. |
| `calcMode="paced"` numeric | Compute paced keyTimes, emit native TAV/segments. | `expand-native` | no | Exact for scalar distance model. |
| `calcMode="paced"` motion | Compute path-distance keyTimes where path sampling is stable. | `expand-native` | maybe | Depends on path length approximation. |
| `calcMode="discrete"` | Use `<p:set>` segments or discrete TAV/path entries. | `exact-native` / `expand-native` | no | Implemented for numeric, color, transform, motion, opacity, and set paths; still validate new attr families visually. |
| `calcMode="spline"` | Sample cubic timing into dense linear TAVs or segments. | `mimic-native` | yes | PowerPoint has accel/decel but not arbitrary SMIL cubic per segment. |
| `keyTimes` | TAV `tm` or nested segment delays. | `exact-native` | no | Must preserve non-uniform segment timing. |
| `keySplines` | Sampled TAV/segments. | `mimic-native` | yes | Store raw spline metadata for trace/oracle. |
| `keyPoints` motion | Map path progress points into retimed motion samples. | `expand-native` / `mimic-native` | yes | Exact only if path progress conversion matches SVG. |

## 8. Additive And Accumulate Mapping

| SVG feature | PowerPoint strategy | Level | Mimic? | Notes |
| --- | --- | --- | --- | --- |
| `additive="replace"` | Default behavior. | `exact-native` | no | Omit additive attr. |
| `additive="sum"` for simple concurrent motion | Native composition may work for limited motion cases. | `composed-native` | maybe | Needs oracle; observed reliability issues. |
| `additive="sum"` generic numeric | Precompute effective absolute values when base value and concurrency graph are known. | `expand-native` | no | Requires animation composition solver. |
| `additive="sum"` color/paint | No general semantic addition for colors. | `unsupported-native` | maybe visual approximation | Skip unless explicit policy. |
| `accumulate="none"` | Default behavior. | `exact-native` | no | Implemented by omission. |
| `accumulate="sum"` finite repeat | Expand repeats into sequenced absolute segments. | `expand-native` | no | May grow timeline size quickly. |
| `accumulate="sum"` indefinite repeat | No finite editable equivalent. | `unsupported-native` | maybe with bounded policy | Needs explicit cap if mimicked. |

## 9. Attribute Mapping

### 9.1 Geometry And Transform

| SVG attribute | PowerPoint target | Strategy | Level | Mimic? |
| --- | --- | --- | --- | --- |
| `x`, `y` | motion path | `<p:animMotion>` | `exact-native` | no |
| `cx`, `cy` | motion path | center motion after geometry resolution | `exact-native` | no |
| `x1`, `y1`, `x2`, `y2` | line geometry | line endpoint materialization, motion/scale composition | `composed-native` | no |
| `width`, `height` | scale | `<p:animScale>` plus anchor motion | `composed-native` | no |
| `rx`, `ry` | size/rounding | map to width/height only where shape model supports it | `mimic-native` | yes |
| `r` | size | circle radius to uniform scale if target remains circular | `composed-native` | maybe |
| `transform translate` | motion | `<p:animMotion>` | `exact-native` | no |
| `transform scale` | scale | `<p:animScale>` plus anchor/origin compensation | `composed-native` | no |
| `transform rotate` | rotation | `<p:animRot>` plus orbit if needed | `composed-native` | no |
| `transform skew` | none | static variants or sampled approximation | `mimic-native` | yes |
| `transform matrix` | decomposition | decompose to translate/scale/rotate when possible | `composed-native` | maybe |
| path `d` | none | morph not generally native | `metadata-only` | maybe for special straight-line cases |
| `points` | none | morph not generally native | `metadata-only` | maybe for special cases |

### 9.2 Paint And Opacity

| SVG attribute | PowerPoint target | Strategy | Level | Mimic? |
| --- | --- | --- | --- | --- |
| `opacity` | `style.opacity` or fade effect | `<p:anim>` / `<p:animEffect filter="fade">` | `exact-native` | no |
| `fill-opacity` | `fill.opacity` | `<p:anim>` | `exact-native` if PPT honors target | no |
| `stroke-opacity` | `stroke.opacity` | `<p:anim>` | `exact-native` if PPT honors target | no |
| `fill` flat color | `fill.color` | `<p:animClr>` | `exact-native` | no |
| `stroke` flat color | `stroke.color` | `<p:animClr>` | `exact-native` | no |
| `stop-color` | gradient stop color | only exact if gradient stop is represented natively and targetable | `metadata-only` / `mimic-native` | yes |
| `stop-opacity` | gradient stop opacity | only exact if gradient stop is represented natively and targetable | `metadata-only` / `mimic-native` | yes |
| `flood-color`, `lighting-color` | effect/filter color | no general native target in current profile | `mimic-native` | yes |
| `paint-order` | none | static ordering only | `unsupported-native` | no |
| `color` / `currentColor` | resolved style | resolve then animate concrete target | `composed-native` | no |

### 9.3 Stroke And Markers

| SVG attribute | PowerPoint target | Strategy | Level | Mimic? |
| --- | --- | --- | --- | --- |
| `stroke-width` | `stroke.weight` | `<p:anim>` | `exact-native` | no |
| `stroke-dashoffset` | wipe/reveal | Wipe entrance mimic for line drawing | `mimic-native` | yes |
| `stroke-dasharray` | none/general line dash | set static dash or mimic with wipe for reveal cases | `mimic-native` | yes |
| `stroke-linecap` | line cap | `<p:set>` if target property exists; otherwise static only | `metadata-only` | maybe |
| `stroke-linejoin` | line join | `<p:set>` if target property exists; otherwise static only | `metadata-only` | maybe |
| `stroke-miterlimit` | line join detail | no common animation target | `metadata-only` | maybe |
| marker attrs | marker rendering | no editable marker animation model | `unsupported-native` | maybe by duplicating shapes |

### 9.4 Visibility, Layout, Text

| SVG attribute | PowerPoint target | Strategy | Level | Mimic? |
| --- | --- | --- | --- | --- |
| `visibility` | `style.visibility` | `<p:set>` / compiled intervals | `exact-native` / `composed-native` | no |
| `display` | descendant visibility | compile render-tree visibility intervals | `composed-native` | no |
| `font-size` | text size | text property animation if targetable; otherwise sampled variants | `metadata-only` | maybe |
| `font-weight`, `font-style` | text style | set-style variants if targetable | `metadata-only` | maybe |
| `x`, `y`, `dx`, `dy` on text | motion | move text box or runs where possible | `composed-native` | maybe |
| `textLength`, `letter-spacing` | text layout | no exact runtime equivalent | `mimic-native` | yes |

### 9.5 Gradients, Patterns, Filters, Clips

| SVG feature | PowerPoint strategy | Level | Mimic? |
| --- | --- | --- | --- |
| gradient geometry (`x1`, `y1`, `x2`, `y2`, `cx`, `cy`, `r`, `fx`, `fy`) | native gradient attrs only if emitted as editable gradient and targetable | `metadata-only` / `mimic-native` | yes |
| gradient transform | no stable target yet | `mimic-native` | yes |
| pattern transform/content | no native dynamic pattern model | `unsupported-native` | maybe by duplicating static variants |
| filter parameters | limited native effects only | `mimic-native` | yes |
| clipPath/mask geometry | no runtime equivalent except visibility/reveal masks | `mimic-native` | yes |

## 10. Required Native Matcher Output

Every `AnimationDefinition` should eventually receive a deterministic native
match record before XML emission:

```python
NativeAnimationMatch(
    level="exact-native",
    primitive="p:animMotion",
    confidence="verified",
    mimic_allowed=False,
    reason="position-x-simple-from-to",
    oracle_required=False,
)
```

Minimum fields:

| Field | Purpose |
| --- | --- |
| `level` | One of the match levels in section 2. |
| `primitive` | Primary PowerPoint primitive or `none`. |
| `strategy` | Handler strategy, such as `scale-with-anchor-motion`. |
| `mimic_allowed` | True only for deliberate approximation. |
| `reason` | Stable reason code for tests and telemetry. |
| `oracle_required` | True when native XML is plausible but not yet verified in PowerPoint. |
| `visual_required` | True when XML validity is insufficient to claim support. |

## 11. Policy Rules

1. Prefer `exact-native`.
2. Use `composed-native` when all children are editable native effects and visual
   capture proves the composition.
3. Use `expand-native` when expansion is deterministic and bounded.
4. Use `mimic-native` only when:
   - the emitted result is editable native PowerPoint XML,
   - the reason code says what semantic property is lost,
   - tests make the approximation explicit.
5. Do not silently emit `metadata-only` or `unsupported-native` cases.
6. Do not rasterize under this spec.

## 12. Verification Matrix

| Claim | Required validation |
| --- | --- |
| Parser support | Corpus parse test: all W3C animation elements become IR definitions with no parser degradations. |
| XML support | Unit tests assert primitive, target attr, timing attrs, and trigger mapping. |
| Native PowerPoint support | Oracle PPTX comparison or authored PowerPoint XML sample. |
| Visual support | PowerPoint slideshow capture across relevant timestamps. |
| Mimic support | Side-by-side W3C visual capture with documented acceptable deltas. |

## 13. Closure Decisions

Every unresolved native-animation row must carry one of these decision labels in
the feature map closure ledger:

| Decision | Meaning |
| --- | --- |
| `wire` | Implement the native path directly. The runtime semantics are already close enough to SMIL that no special predicate is required beyond ordinary handler guards. |
| `gate` | Implement the native path only behind a documented semantic predicate. The predicate must be narrow enough that the emitted preset still means the same thing as the authored SMIL. |
| `mimic` | Emit a deliberate native approximation. The semantic loss must be named in docs/tests, and the matcher must mark the result as approximate. |
| `dead` | Never emit the candidate XML shape. PowerPoint accepts it syntactically but drops it or misplays it at runtime. |
| `fallback` | Do not force native timing XML for this case. Route to another supported tier such as compiled visibility, flipbook, morph, or static resolution. |

The row-by-row closure ledger lives in
`docs/reference/research/svg-to-drawingml-feature-map.md` section 8.9.

## 14. Current Validation Focus

The remaining high-signal open work for this mapping contract is visual/runtime
proof on the timing-heavy cases:

- `linear`, `paced`, `discrete`, `spline`, and `keyPoints`
- event-linked `end`, `repeatDur`, and `restart`
- limited concurrent motion under `additive="sum"`

Track implementation slices and blocker ownership in:

- `docs/tasks/animation-smil-parity-tasks.md`
- `docs/tasks/animation-w3c-sample-blocker-matrix.md`
- `docs/internals/animation-documentation-map.md`
