# Clipping and DrawingML callback for the PHP port

Date: 2026-08-08

Python baseline: `7c4f9cae1eba0bbee20386ef496ad68aaa18cda5`

Consumer: `NCSVG2OOXML`

## Purpose

This is the callback contract from the Python implementation to the PHP port.
It separates three concerns that must not be reported as one feature:

1. resolving SVG clip geometry;
2. computing boolean unions and intersections; and
3. lowering the result to editable DrawingML.

The Python implementation solves much of the first two concerns with Skia
PathOps. It does **not** currently provide a general editable DrawingML clip for
arbitrary vector shapes. The PHP port should reuse the geometry behavior, but
must not copy the current strategy labels or documentation claims without also
checking the emitted OOXML artifact.

## Verified Python behavior

At the baseline above, the resvg bridge builds Skia paths for clip children and
applies SVG transforms before combining them. It then:

- unions sibling clip children with `skia.Op(..., kUnion_PathOp)`;
- intersects a node with its nested clip path using
  `skia.Op(..., kIntersect_PathOp)`;
- converts the resulting Skia path back to normalized line/cubic segments; and
- records the computed path, bounds, rule, primitives, and empty state in the
  clip definition.

`skia-python` is an optional `render` dependency. Without it, the complete
boolean result is not available through this path.

The production writer then lowers clips as follows:

- A path or vector shape with path-based clip geometry is normally rasterized
  to PNG and emitted as `<p:pic>`.
- Rasterization uses Skia's real `canvas.clipPath(..., kIntersect, ...)`.
- A clipped image can remain a picture and use `<a:srcRect>` for rectangular
  cropping and a picture `prstGeom` or `custGeom` for supported clip geometry.
- Empty clips hide the target.
- If rasterization is unavailable, some path cases can receive an EMF overlay:
  a white frame with an even-odd transparent cutout. This is
  background-dependent and is not a general clipping operation.
- `clipmask.clip_xml_for()` intentionally emits no `<a:clipPath>` because that
  element is not standard DrawingML.

The unit test `test_path_clip_path_serialisation` captures the important
artifact-level result: no `<a:clipPath>` is emitted and the clipped path is a
`<p:pic>`, not an editable `<p:sp>`.

## What is not solved yet

### Generic editable DrawingML clipping

DrawingML has no generic SVG-style clip-path property for arbitrary shapes.
Computing `target geometry ∩ clip geometry` is necessary, but it only becomes
an editable DrawingML solution when that result replaces the target's geometry
in a valid `<a:custGeom>`.

That replacement is safe for a fill-only shape. It is not automatically safe
for a stroked shape: stroking the intersection also draws the newly created
clip boundary, which SVG clipping does not do.

### Truthful strategy classification

`resolve_clip_ref()` currently assigns `ClipStrategy.NATIVE` to resolved clips,
including path clips that the writer later rasterizes. `BOOLEAN` and `EMF`
exist in the enum, but the resolver does not use them to describe this actual
lowering path. Consumers must inspect the final lowering decision rather than
treating `NATIVE` as proof of editability.

### `objectBoundingBox` proof

The parsed resvg node retains `clip_path_units`, but the boolean gather path
does not currently show the target-bounds normalization required for
`clipPathUnits="objectBoundingBox"`. Parsing the attribute and passing package
validation are not proof that its geometry was normalized correctly.

### Arbitrary group clips

Bounds propagation can crop rectangular child content, but it does not prove
that a non-rectangular group clip was applied to every child with SVG
compositing semantics.

## Cross-port clip contract

Both implementations should produce a canonical clip result before OOXML
lowering. The parity fixture should expose at least:

- clip id and reference status (`resolved`, `missing`, `cycle`, `empty`);
- coordinate units and the target bounds used for normalization;
- accumulated transform;
- fill/clip rule;
- canonical line/cubic segments after unions and nested intersections;
- computed bounds;
- whether boolean geometry is exact, flattened, approximated, or unavailable;
- chosen lowering (`editable_shape`, `picture_geometry`, `image_crop`,
  `emf`, `png`, `hidden`, or `unsupported`); and
- the reason and dependency used for any fallback.

`boolean_computed=true` and `editable_drawingml=true` must remain separate
flags. Valid package XML is likewise not evidence that a clip is visually
correct or editable.

## Recommended lowering matrix

| Target and clip | Preferred lowering | Constraint |
| --- | --- | --- |
| Fill-only path/basic shape + path clip | Compute target/clip intersection and emit the result as one `<a:custGeom>` | Preserve fill rule and transforms |
| Image + rectangular clip | `<a:srcRect>` | Crop must be expressed relative to the original image bounds |
| Image + supported contour | Picture `prstGeom` or `custGeom` | Validate coordinate mapping against the picture transform |
| Empty clip | Hide or omit target | Must not silently drop the clip and show content |
| Stroked vector shape + arbitrary clip | PNG or faithful EMF fallback | Do not create a stroke on the clip boundary |
| Text, mixed-content group, blend/effect stack | PNG first; EMF only when semantics are proven | Preserve compositing order and opacity |
| Missing, cyclic, or unsupported clip | Explicit diagnostic plus declared fallback | Never silently emit unclipped content |

The first row is the useful next editable-DrawingML slice. Python's Skia
PathOps can serve as the reference boolean engine. PHP may use a different
engine, but should compare canonical output against the same fixtures and
declare flattening tolerances when it cannot preserve curves exactly.

## Callback work for the Python repository

1. Add an explicit lowering decision after clip resolution; do not use
   `ClipStrategy.NATIVE` for content that becomes PNG.
2. Export deterministic canonical clip geometry snapshots for cross-port
   parity tests.
3. Implement editable `<a:custGeom>` intersection for fill-only path/basic
   shape targets.
4. Normalize and test `objectBoundingBox` geometry against target bounds before
   boolean operations.
5. Keep raster/EMF fallbacks explicit for strokes, text, groups, effects, and
   other cases where geometry replacement changes semantics.
6. Reconcile the feature map and pipeline documentation with actual emitted
   artifacts. Current claims that complex, nested, group, and
   `objectBoundingBox` clipping are simply "done" are too broad.

## Acceptance tests shared with PHP

- sibling clip children requiring union;
- nested clip paths requiring intersection;
- even-odd and nonzero rules;
- `userSpaceOnUse` and positive axis-aligned `objectBoundingBox` cases;
- a fill-only path that remains `<p:sp>` with editable custom geometry;
- a stroked path that does not acquire a clip-boundary stroke;
- a non-rectangular group clip over differently colored children;
- a clip over a non-white or overlapping background to expose overlay tricks;
- an empty, missing, and cyclic clip reference;
- open-save-reopen verification in EuroOffice, including visual result and
  whether the native case remains editable.

For every package fixture, assert both the visible result and the artifact type
(`<p:sp>`, `<p:pic>`, EMF, or PNG). Schema/package validation alone is not a
clipping test.

## Source pointers

- `src/svg2ooxml/core/traversal/bridges/resvg_clip_mask_gather.py`
  - path creation, sibling union, and nested intersection
- `src/svg2ooxml/core/traversal/bridges/resvg_clip_mask.py`
  - conversion of the boolean Skia path back to segments and bounds
- `src/svg2ooxml/drawingml/skia_path.py`
  - Skia/IR segment bridge
- `src/svg2ooxml/core/traversal/clipping.py`
  - `ClipRef` creation and current strategy assignment
- `src/svg2ooxml/drawingml/clipmask.py`
  - deliberate absence of non-standard clip XML
- `src/svg2ooxml/drawingml/shape_renderer_raster.py`
  - path-clip raster fallback
- `src/svg2ooxml/drawingml/rasterizer_shapes.py`
  - actual Skia clip operation during rasterization
- `src/svg2ooxml/drawingml/shape_renderer_dispatch.py`
  - supported picture geometry path
- `src/svg2ooxml/drawingml/shape_renderer_utils.py`
  - bounds intersection and image `<a:srcRect>` metadata
- `src/svg2ooxml/drawingml/shape_renderer_clip.py` and `clip_overlay.py`
  - background-dependent EMF overlay fallback
- `tests/unit/drawingml/test_writer.py`
  - current artifact-level expectations
- `docs/reference/research/svg-to-drawingml-feature-map.md`
  - documentation claims that require reconciliation
