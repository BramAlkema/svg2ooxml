# Gradient Raster Fallback Emits Blank PNGs

**Date**: 2026-08-09
**Status**: OPEN — localised, not root-caused
**Severity**: High — silently drops shading on gradient-heavy artwork
**Repro fixture**: `tests/visual/fixtures/gallardo.svg`

## Symptom

Converting `gallardo.svg` embeds **25 PNG media parts, 20 of which are fully
transparent** (`RGBA == [0,0,0,0]` for every pixel). Instrumenting the
rasterizer directly shows **11 of 15 `Rasterizer.rasterize` calls return an
all-transparent image**.

Accounting, so the two counts are not confused: 28 media registrations collapse
to 25 written parts (`image13.png`, the 9×8 pattern tile, is placed 4×). Exactly
15 of those registrations are the geometry raster path
(`media:geometry_rasterized: 15`, matching the 15 rasterizer calls), and 11 of
those are blank. The remaining 13 registrations come from other paths — the
filter/EMF promotion (`filter:resvg_promoted_emf: 2`) and pattern tiling — and
account for the other 9 blank parts. **Those paths were not audited here**; this
note covers only the 11 blank geometry rasters.

The blanks are not small: they are the largest shading regions in the artwork.

| Media | Placement (px) | Size | Area | Region |
|---|---|---|---|---|
| `image2.png` | (0, 449) | 670×156 | 104,329 px² | Front bumper / lower nose |
| `image12.png` | (76, 366) | 471×185 | 87,295 px² | Front fender / hood side |
| `image16.png` | (659, 325) | 277×229 | 63,453 px² | Door / front wheel arch |
| `image18.png` | (999, 49) | 227×227 | 51,495 px² | Roof / rear quarter sheen |
| `image28.png` | (655, 79) | 227×227 | 51,495 px² | Windshield sheen |
| `image23.png` | (1136, 354) | 233×138 | 32,233 px² | Rear fender |
| `image11.png` | (536, 2) | 555×52 | 28,842 px² | Roofline highlight |

That is why the converted deck reads flat next to the SVG reference: the soft
shading layers are present as shapes but carry no pixels.

## Trigger

`shape_renderer_raster.py:176` `_has_fully_transparent_gradient_stop` forces the
raster fallback for **any** gradient carrying a stop at opacity ≤ 0.001. Fading
a highlight to fully transparent is the standard vector-art shading idiom, so
this diverts most of the artwork's shading onto the raster path.

## Cause (localised, not fixed)

The gradient vector is not in the same coordinate space as the rasterized
element's bounds. Dumping paint geometry against raster bounds:

```
BLANK  bounds=(0,449,670x156)    vector=(-338,477) -> (-328,446)   transform=identity
BLANK  bounds=(76,366,471x185)   vector=(1511,803) -> (1558,720)   transform=translate(-1947,-403)
```

The vector lands far outside the shape it fills. With pad spread the shape is
then filled entirely from one end of the ramp — the transparent end in these
cases — producing an empty raster. Shapes landing past the *opaque* end would
instead flatten to a solid colour, which is the same bug wearing a different
symptom.

**The shader is not the fault.** `drawingml/rasterizer_paint.py:119` computes
`matrix = self._to_skia_matrix(paint.transform)` and passes it to
`GradientShader.MakeLinear` as the local matrix, so `gradientTransform` *is*
applied, and `spread_method` is honoured via `_resolve_tile_mode`. The stop
preparation, point resolution, and matrix handling match
`render/skia_paint.py` almost line for line. So the mismatch arrives already
baked into the IR: the paint carries gradient coordinates in the original SVG
user space while the path geometry has been normalised into another. Anything
reading the two together misaligns. The native `gradFill` path is immune because
DrawingML gradient geometry is relative to the shape, which is why only the
raster fallback shows it.

**Proven: the gradient coordinates are never transformed at all.** The IR paint
for the 670×156 region holds `start=(-337.70929, 476.72092)`, byte-identical to
the source SVG's `x1="-337.70929" y1="476.72092"`. The path geometry for the
same element sits at `x:[-8,669] y:[450,604]`, matching its raster bounds. So
geometry reaches final space and paint does not.

**The leaf node is not where the transform lives.** Instrumenting
`resolve_paints_for_node` shows all 21 gradient paints arrive with
`node.transform` = identity. gallardo carries its 25 transforms on ancestor
`<g>` elements (`translate(-370.75508,213.48487)` alone appears 8×). Nor is
`metadata["_ctm"]` present on these elements — that hook (`traversal/hooks.py`)
is on the legacy DOM path, not the resvg path these take.

A fix attempted at `resolve_paints_for_node` — composing `node.transform` into
`userSpaceOnUse` paints — was written and reverted: it is a no-op here because
that matrix is identity.

## Only one of the two raster paths has this bug

There are two Skia implementations with near-identical shader helpers
(`prepare_gradient_stops`, `linear_gradient_points`, `to_skia_matrix`,
`make_*_gradient_shader`). The duplication is real, but the defect is in the
*calling context*, not the shader:

| | `render/` (filter pipeline) | `drawingml/rasterizer*` (fallback) |
|---|---|---|
| Paint types | resvg/usvg (`core.resvg.painting.gradients`) | IR (`ir.paint.LinearGradientPaint`) |
| Canvas | `canvas.concat(total_matrix)` per node — live CTM (`render/pipeline.py:147-150`) | `canvas.scale()` + `canvas.translate(-bounds.x, -bounds.y)` only (`rasterizer.py:60-61`) |
| Gradients | **Correct** — the CTM reconciles user-space coordinates | **Broken** — nothing reconciles them |

`render/` walks the tree as a scene renderer, so `userSpaceOnUse` coordinates
come out right for free; its own source says as much at `pipeline.py:185`
("node.transform is ALREADY applied to the canvas"). The DrawingML fallback
draws one element standalone, with geometry already baked into final space and
paint still in original user space, and no matrix to bridge them.

That suggests the cheapest fix is **deletion, not repair**: route the geometry
fallback through the `render/` scene path, which already handles this, and drop
the duplicate implementation. Repairing in place means finding and threading the
accumulated transform (below) *and* keeping two shader implementations in sync
forever. Written up as **ADR-039 (proposed)** in
[`../../adr/README.md`](../../adr/README.md).

**Open question**: which stage of the resvg conversion composes ancestor group
transforms into path geometry? `convert_path` passes only `path_node.transform`
(identity here) to `normalize_path`, so the accumulation happens elsewhere.
Whatever that stage is, it must rebase `userSpaceOnUse` paint alongside the
geometry. Note `objectBoundingBox` gradients must be left alone — they resolve
against bounds already in final space.

**Also**: the 4 rasters that are not blank are wrong too. Their gradient vectors
are equally misplaced; they simply land past the *opaque* end of the ramp and
flatten to a solid colour instead of a transparent one. The raster gradient path
is uniformly broken — blankness is just the visible half of it.

**Ruled out** by minimal reproduction (each renders correctly):

- a two-stop opaque→transparent gradient on its own
- the same inside `translate`, `scale`, and `matrix` group transforms
- `gradientUnits="userSpaceOnUse"`, with and without `gradientTransform`

So the defect needs gallardo's nesting to surface; a flat single-element case
does not reproduce it. `gallardo.svg` uses `userSpaceOnUse` on 30 gradients and
`gradientTransform` on 21.

## Reproducing

`blank_raster_probe.py` (session scratchpad) monkeypatches
`Rasterizer.rasterize`, converts a fixture, and prints every element whose
raster came back fully transparent along with its bounds and gradient vector.

## Worth questioning: why rasterize at all

DrawingML expresses a stop's alpha natively —
`<a:gs><a:srgbClr><a:alpha val="0"/></a:srgbClr></a:gs>` — and
`test_srgb_clr_carries_display_srgb_bytes_verbatim` already pins per-stop alpha
surviving end-to-end. A two-stop opaque→transparent ramp is therefore natively
representable, and most of gallardo's rasterized regions are exactly that.

The rasterize-on-transparent-stop rule was introduced in `466ef3c` with no
recorded rationale and no linked oracle result. Before fixing the coordinate
bug, it is worth re-testing whether the rule is needed at all: if PowerPoint
renders alpha-0 stops correctly, deleting the trigger removes the blank rasters,
the 25 media parts, and a fidelity tier in one move.

## Related

- [`../assessments/splatthis-raster-handoff.md`](../assessments/splatthis-raster-handoff.md)
  — a splat handoff consumes rasterizer output, so it inherits this bug rather
  than routing around it.
- [`../../reference/research/drawingml-srgb-emission-contract.md`](../../reference/research/drawingml-srgb-emission-contract.md)
  — per-stop alpha emission contract.
