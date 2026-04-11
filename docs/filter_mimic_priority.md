# Filter Mimic Priorities

This document captures the editable-first filter implementation order derived
from measured corpus usage, not intuition.

Regenerate the usage report with:

```bash
./.venv/bin/python -m tools.visual.filter_usage \
  tests/corpus tests/svg tests/visual/fixtures tests/assets \
  --output-dir reports/analysis/filter-usage-20260411-a --top 20
```

Current measured snapshot from `reports/analysis/filter-usage-20260411-a`:

- SVGs scanned: 589
- SVGs with filter primitives: 58
- Filter elements: 250
- Primitive instances: 361

Top primitive counts:

| Primitive | SVGs | Instances | Editable-first note |
| --- | ---: | ---: | --- |
| `feimage` | 11 | 76 | defer for editability-first; often raster by definition |
| `fecomposite` | 16 | 44 | high priority stack operator |
| `fediffuselighting` | 6 | 39 | high priority lighting recipe |
| `feflood` | 12 | 33 | high priority stack source |
| `fegaussianblur` | 13 | 33 | high priority editable blur stack |
| `fespecularlighting` | 7 | 31 | high priority lighting recipe |
| `feturbulence` | 5 | 25 | editable synthesis candidate |
| `feconvolvematrix` | 5 | 17 | selective recipe candidate only |
| `feoffset` | 9 | 16 | high priority stack operator |
| `femerge` | 8 | 14 | high priority stack compositor |
| `feblend` | 3 | 11 | high priority paint/effect stack operator |
| `fecolormatrix` | 2 | 7 | medium priority color transform recipe |

## Editable-First Order

### Slice 1: Blur / Shadow / Offset Core

Target primitives:

- `fegaussianblur`
- `feoffset`
- `femerge`
- `feflood`

Why first:

- High usage
- Strong editable-native surface in PowerPoint
- Many common chains reduce to these recipes

Key measured chains/pairs:

- `feflood > fegaussianblur > femerge`
- `fegaussianblur -> femerge`
- `fegaussianblur -> feoffset`
- `feoffset -> fegaussianblur`
- `feoffset -> feflood`

Editable recipe family:

- duplicate source geometry
- blur stack
- optional offset stack
- flood-tint source
- merge via grouped layer ordering

### Slice 2: Composite / Blend Paint Logic

Target primitives:

- `fecomposite`
- `feblend`
- `feflood`
- `femerge`

Why second:

- `fecomposite` is the most frequent editable-friendly operator
- `feflood` is a strong synthetic source for tint/overlay recipes

Key measured chains/pairs:

- `feflood > feblend`
- `feflood -> feblend`
- `feflood > fecomposite`
- `feflood -> fecomposite`
- `fecomposite -> femerge`

Editable recipe family:

- flood layers
- fillOverlay / solid fill overlays
- alpha-mask recipes
- grouped source and target duplication

### Slice 3: Lighting

Target primitives:

- `fediffuselighting`
- `fespecularlighting`
- `fecomposite`
- `femerge`

Why third:

- Combined count is high
- Most real value comes from a few recurring stacks, not full SVG lighting semantics

Key measured chains/pairs:

- `fespecularlighting > fecomposite`
- `fediffuselighting > fespecularlighting > femerge`
- `fediffuselighting -> fespecularlighting`
- `fespecularlighting -> femerge`

Editable recipe family:

- highlight gradients
- glow rims
- specular hotspots
- shadow/highlight merge stacks

### Slice 4: Color Transforms

Target primitives:

- `fecolormatrix`
- `fecomponenttransfer`

Why fourth:

- Lower measured frequency than blur/composite/lighting
- Good editable coverage for shape paint and opacity transforms

Editable recipe family:

- fill/stroke recolor
- opacity remap
- per-layer tint and alpha recipes

### Slice 5: Morphology

Target primitive:

- `femorphology`

Why:

- Low frequency, but strong candidate for editable shape expansion/contraction

Editable recipe family:

- outline expansion
- inset/erode geometry variant
- glow/soft-edge support

### Slice 6: Turbulence Synthesis

Target primitive:

- `feturbulence`

Why:

- Measured usage is meaningful
- No native primitive exists, but editable synthesis is possible

Editable recipe family:

- blob-cloud field
- grain overlay field
- vector tile noise
- multi-octave grouped stacks

### Slice 7: Selective Convolution

Target primitive:

- `feconvolvematrix`

Why later:

- Some kernels can be mimicked
- General convolution is not honest to claim as editable-native

Editable recipe family:

- box blur
- sharpen/emboss approximations
- edge emphasis recipes

## Defer / Boundary Cases

These should not lead the editable-first roadmap:

- `feimage`
  Usually raster-backed by definition. Support matters, but not as the first
  editable mimic target.
- `fedisplacementmap`
  Keep for later. Best handled after turbulence synthesis and geometry
  perturbation infrastructure exist.

## Working Rule

For each slice:

1. Build one recipe board with parameter sweeps.
2. Validate in PowerPoint slideshow capture, not only XML.
3. Record a complexity budget:
   object count, group count, PPTX size, render stability.
4. Only fall back to raster after the editable recipe space is exhausted.
