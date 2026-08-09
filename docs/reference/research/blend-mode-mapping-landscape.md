# Blend-Mode Mapping Landscape — SVG/CSS → DrawingML

Date: 2026-05-24
Status: survey — landscape of what's possible, what's faked, what's lost.

## The gap

SVG content can use blend modes via:
- CSS `mix-blend-mode` on elements
- SVG `<feBlend>` filter primitive
- SVG 2 `style="mix-blend-mode: ..."`

DrawingML has **no public per-shape blend-mode primitive**. Shapes blend
with the page using straight sRGB alpha-over. There is no
`mode="multiply"` attribute, no equivalent of `<feBlend>`, and the
`<a:effectLst>` effects do not include a backdrop-aware compositor.

This means any SVG using non-`normal` blend modes loses information on
conversion to PPTX. For some uses (designer artwork, brand identity,
infographic layering) this is a major fidelity gap.

## Per-mode status

The W3C compositing modes split into two families: separable (per-channel)
and non-separable (HSL-based).

### Separable modes

| Mode | DrawingML path | Notes |
|---|---|---|
| `normal` | native (default) | alpha-over in sRGB. |
| `multiply` | partial fake | A solid `<a:fillOverlay>` with `blendMode="mult"` exists in spec (`a:fillOverlay`), inconsistently supported. Or pre-bake via blip. |
| `screen` | partial fake | `<a:fillOverlay>` accepts `blendMode="screen"` (some renderers). |
| `darken` | partial fake | `<a:fillOverlay blendMode="darken">` — limited support. |
| `lighten` | partial fake | `<a:fillOverlay blendMode="lighten">` — limited support. |
| `color-dodge` | **lost** | No DrawingML primitive. Bake to blip. |
| `color-burn` | **lost** | No DrawingML primitive. Bake to blip. |
| `hard-light` | **lost** | No DrawingML primitive. Bake to blip. |
| `soft-light` | **lost** | No DrawingML primitive. Bake to blip. |
| `overlay` | **lost** | Combination of multiply/screen — no native mode. |
| `difference` | **lost** | No native mode. |
| `exclusion` | **lost** | No native mode. |

### Non-separable (HSL) modes

| Mode | DrawingML path | Notes |
|---|---|---|
| `hue` | **lost** | No backdrop-aware mode. Could be approximated for solid-over-solid by computing the resulting color and emitting a flat fill — useless for general content. |
| `saturation` | **lost** | Same. |
| `color` | **lost** | Same. |
| `luminosity` | **lost** | Same. |

### Important non-modes (often confused with blend modes)

`<a:lumMod>`, `<a:lumOff>`, `<a:satMod>`, `<a:satOff>`, `<a:hueMod>`,
`<a:hueOff>`, `<a:tint>`, `<a:shade>`, `<a:alpha>`, `<a:duotone>` are
**color transforms** on a shape's own fill — they do not interact with
the backdrop. They cannot stand in for `mix-blend-mode: hue` or similar.

## The `<a:fillOverlay blendMode="...">` situation

DrawingML's `<a:fillOverlay>` element accepts a `blend` attribute with
values `over | mult | screen | darken | lighten`. This is a **shape-self-
overlay**, not a backdrop blend. Specifically:

- It overlays an additional fill on top of the shape's own fill.
- The blend is between two fills *on the same shape*, not between the
  shape and what's behind it.
- It can fake some `mix-blend-mode: multiply` effects ONLY when the
  "backdrop" is itself a known fill (e.g. a duplicated shape behind it).
- Renderer support is inconsistent — confirm in real PowerPoint.

So `<a:fillOverlay>` is not the answer for general `mix-blend-mode`
mapping. It's a tool for specific manual recipes (shadow-with-tint,
two-tone shape) where the converter controls both fills.

## Workarounds

### W1. Rasterize at conversion time (flatten to blip)

For any non-`normal` blend mode, compute the post-blend pixels on the
SVG side and emit a `<a:blipFill>` (PNG bitmap) with `mode="normal"`.

Pros:
- Pixel-accurate.
- Works for every blend mode.

Cons:
- Loses vector editability.
- Bloats file size for full-coverage blends.
- Resolution-dependent.

This is svg2ooxml's existing fallback path. The question is policy: when
to fall back. Default policy could be "any non-normal blend mode forces
a blip for the affected subtree."

### W2. Solid-over-solid pre-computation

If a blended shape's only "backdrop" within the bounding region is a
solid color (e.g. a brand background), the converter can pre-compute the
blend result and emit a flat fill in the result color.

Pros:
- Preserves vector, smallest file size.
- Works for any blend mode.

Cons:
- Only valid when backdrop is provably uniform in the shape's bounds.
- Needs analysis of z-order + bounding boxes.

### W3. Subtree blip with vector frame

For a small blended shape over a complex backdrop: clip the backdrop to
the shape's bounds, rasterize *both* into a blip, place a vector outline
of the shape's geometry above for any subsequent operations.

Pros:
- Smaller blip than full-region rasterization.
- Preserves later effect chain (transforms still apply to the blip).

Cons:
- Bounding analysis required.
- Stroke and effects on the shape must be re-applied at vector level.

### W4. Document and warn

For non-recoverable cases, emit a build warning at conversion time:
"shape X uses `mix-blend-mode: difference` which has no DrawingML
equivalent; rasterizing." Don't fail silently.

## Recommendation for svg2ooxml

1. **Default policy**: detect `mix-blend-mode` and `<feBlend>` in the SVG
   pipeline. If mode is not `normal`, route the affected subtree through
   W1 (flatten to blip) or W2 (if a uniform backdrop is provable).
2. **Diagnostics**: emit a structured warning per blended subtree, with
   the mode, bbox, and chosen workaround. This is what designers need to
   audit conversion fidelity.
3. **Future opt-in**: `<a:fillOverlay>` recipes for the four supported
   modes (`mult`, `screen`, `darken`, `lighten`) where the converter
   controls both fills (e.g. shadow tinting, two-tone splat). Feature-
   flag this and validate in real PowerPoint per
   [feedback-no-soffice-for-pptx-validation].

## Open questions

- Does Web PowerPoint honor `<a:fillOverlay blend>` consistently?
- Does Google Slides import preserve `<a:fillOverlay blend>`? (Important
  given the `Figma -> SVG -> OOXML (PPTX) -> Google Slides import` use
  case in `drawingml-unused-opportunities.md`.)
- What is the threshold (in pixels, shape count, or visual complexity)
  at which W1's blip becomes unacceptably large vs the vector-blend
  budget?

## Related

- [drawingml-unused-opportunities.md](./drawingml-unused-opportunities.md)
  — broader gap analysis.
- [anisotropic-blur-emulation.md](./anisotropic-blur-emulation.md) —
  another DrawingML mimicry note with a worked recipe.
- [blur-fidelity-and-scaling.md](./blur-fidelity-and-scaling.md) —
  open characterization questions on `<a:blur>`.
