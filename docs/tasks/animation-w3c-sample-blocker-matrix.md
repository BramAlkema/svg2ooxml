# W3C Animation Sample Blocker Matrix

- **Status:** Working ledger
- **Date:** 2026-04-18
- **Category:** execution ledger
- **Source sample:** `tests/corpus/w3c/report_animation_full.json`
- **Sample seed:** `20260221`
- **Scope:** the current deterministic 40-deck W3C animation profile, not the full
  W3C animation corpus

## Purpose

The current local gate proves that the sampled W3C animation fixtures export to
valid PPTX packages without hard failures:

- `40/40` decks export successfully
- `0` failed decks
- `100%` OpenXML audit pass rate

That is useful, but it is not a fidelity claim. This matrix freezes the current
40-deck sample against one primary blocker per deck so implementation work can
be staged by semantics instead of by export success.

## Blocker Families

| Family | Meaning | Planned slice |
| --- | --- | --- |
| `native-baseline` | Keep as a control deck. Native mapping is already the expected path. | Preserve during every slice |
| `motion-path-normalization` | Motion is native, but SVG path normalization and coordinate handling still need proof. | Motion cleanup |
| `motion-auto-rotate` | Motion path tangent rotation is only approximate today. | Timing / motion mimic slice |
| `timing-interpolation` | `discrete`, `paced`, `spline`, `keySplines`, or `keyPoints` need timing expansion or sampling. | Timing expansion pass |
| `composition-solver` | Multiple effects or additive/accumulate semantics need pre-emission composition. | Composition solver |
| `value-form-resolution` | `from` / `to` / `by` forms need underlying-value resolution before emission. | Composition / value normalization |
| `timing-trigger-proof` | Trigger-linked scheduling needs runtime proof or cleaner wiring. | Scheduling slice |
| `visibility-compiler` | SVG `display` / inherited visibility must compile to native `style.visibility` plans. | Display / visibility slice |
| `attribute-propagation` | Animated state must propagate through inheritance, `<use>`, or non-leaf structural targets. | Propagation slice |
| `dead-or-mimic-target` | Target attribute is dead natively or only has a narrow mimic path. | Dead-path gating slice |
| `geometry-morph` | Per-vertex or degenerate-shape geometry changes need Morph or flipbook policy. | Geometry fallback slice |
| `unsupported-runtime-attribute` | The animated runtime attribute has no credible in-slide PowerPoint target. | Explicit unsupported policy |
| `unsupported-dom-runtime` | Browser DOM / SMIL API semantics are outside PowerPoint runtime scope. | Explicit unsupported policy |

## Current 40-Deck Sample

| Deck | Fixture focus | Primary blocker | Target slice |
| --- | --- | --- | --- |
| `animate-elem-07-t` | Motion path variants | `motion-path-normalization` | Motion cleanup |
| `animate-elem-06-t` | Motion path variants | `motion-path-normalization` | Motion cleanup |
| `animate-elem-38-t` | `viewBox` animation | `unsupported-runtime-attribute` | Unsupported policy |
| `animate-elem-24-t` | motion + scale together | `composition-solver` | Composition solver |
| `animate-elem-35-t` | dasharray, dashoffset, miterlimit, linecap/join | `dead-or-mimic-target` | Dead-path gating |
| `animate-elem-25-t` | target attribute/property selection | `native-baseline` | Control deck |
| `animate-elem-21-t` | chained timing | `timing-trigger-proof` | Scheduling slice |
| `animate-elem-13-t` | `from` / `by` / `to` / `values` | `value-form-resolution` | Value normalization |
| `animate-elem-04-t` | Motion path variants | `motion-path-normalization` | Motion cleanup |
| `animate-elem-34-t` | `points` and `fill-rule` animation | `geometry-morph` | Geometry fallback |
| `animate-elem-27-t` | target element resolution | `native-baseline` | Control deck |
| `animate-elem-19-t` | linear scalar animation | `native-baseline` | Control deck |
| `animate-elem-15-t` | `calcMode="paced"` | `timing-interpolation` | Timing expansion |
| `animate-elem-12-t` | `calcMode="spline"` | `timing-interpolation` | Timing expansion |
| `animate-elem-09-t` | `calcMode="discrete"` | `timing-interpolation` | Timing expansion |
| `animate-elem-10-t` | `calcMode="linear"` | `native-baseline` | Control deck |
| `animate-dom-02-f` | ElementTimeControl DOM API | `unsupported-dom-runtime` | Unsupported policy |
| `animate-elem-08-t` | motion `rotate="auto"` / `auto-reverse` | `motion-auto-rotate` | Timing / motion mimic |
| `animate-elem-41-t` | graphics properties stress deck | `dead-or-mimic-target` | Dead-path gating |
| `animate-elem-31-t` | `display` animation | `visibility-compiler` | Display / visibility |
| `animate-elem-03-t` | inherited animated properties | `attribute-propagation` | Propagation slice |
| `animate-elem-36-t` | transform on structure / hyperlink / text targets | `attribute-propagation` | Propagation slice |
| `animate-elem-20-t` | hyperlink timing / resolved starts | `timing-trigger-proof` | Scheduling slice |
| `animate-elem-39-t` | animated `xlink:href` | `unsupported-runtime-attribute` | Unsupported policy |
| `animate-elem-32-t` | degenerate basic shapes | `geometry-morph` | Geometry fallback |
| `animate-dom-01-f` | SVGAnimationElement DOM API | `unsupported-dom-runtime` | Unsupported policy |
| `animate-elem-28-t` | inherited animated properties | `attribute-propagation` | Propagation slice |
| `animate-elem-37-t` | transform on shape targets | `native-baseline` | Control deck |
| `animate-elem-02-t` | `additive` / `accumulate` | `composition-solver` | Composition solver |
| `animate-elem-40-t` | x/y/width/height across element types | `composition-solver` | Composition solver |
| `animate-elem-22-b` | basic declarative animation | `native-baseline` | Control deck |
| `animate-elem-17-t` | single-track spline timing | `timing-interpolation` | Timing expansion |
| `animate-elem-23-t` | `set` + `animateColor` | `native-baseline` | Control deck |
| `animate-elem-29-b` | animated fill opacity | `dead-or-mimic-target` | Dead-path gating |
| `animate-elem-11-t` | `calcMode="paced"` | `timing-interpolation` | Timing expansion |
| `animate-elem-30-t` | animated `<use>` with animated `<defs>` | `attribute-propagation` | Propagation slice |
| `animate-elem-33-t` | motion `keyPoints` + `keyTimes` | `timing-interpolation` | Timing expansion |
| `animate-elem-14-t` | discrete scalar timing | `timing-interpolation` | Timing expansion |
| `animate-elem-26-t` | animated `stroke-width` | `dead-or-mimic-target` | Dead-path gating |
| `animate-elem-05-t` | Motion path variants | `motion-path-normalization` | Motion cleanup |

## Execution Order

The current sample argues for this work order:

1. `visibility-compiler` and `timing-trigger-proof`
2. `timing-interpolation`
3. `composition-solver`
4. `attribute-propagation`
5. `dead-or-mimic-target`
6. `geometry-morph`
7. `unsupported-*` policy closure

That order keeps exact and composed-native work ahead of fallback and explicit
unsupported policy.

## Sample Gaps

The deterministic 40-deck sample does **not** currently include several later
fixtures that are still important for full-body parity planning:

- `animate-elem-61-t` (`display` as timing base)
- `animate-elem-69-t` / `animate-elem-70-t` (`repeatDur`, self-referential begin/end)
- `animate-elem-81-t` (`additive` + `accumulate` transform stress)
- `animate-elem-83-t` (`d` path morph)
- `animate-elem-89-t` (`spline` parsing variants)
- `animate-elem-92-t` (extra `discrete` timing coverage)

Those remain the right second-wave fixtures after the current sample’s blocker
families are closed.
