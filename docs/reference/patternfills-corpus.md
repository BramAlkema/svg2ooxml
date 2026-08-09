# patternfills — Preset-Pattern Mapping Corpus

Source: <https://github.com/iros/patternfills> —
[`public/patterns.css`](https://github.com/iros/patternfills/blob/master/public/patterns.css)
Licence: MIT. Retrieved 2026-08-09.

## What it is

49 tiling patterns, each a **10×10 SVG tile** embedded as a base64
`data:image/svg+xml` URI on a CSS class with `background-repeat: repeat`. The
tiles use only `<rect>`, `<circle>`, `<path>`, `stroke`, and `fill` — no
gradients, no filters, no transforms.

| Family | Count | Classes |
|---|---|---|
| Circles | 9 | `.circles-1` … `.circles-9` |
| Dots | 9 | `.dots-1` … `.dots-9` |
| Horizontal stripe | 9 | `.horizontal-stripe-1` … `-9` |
| Vertical stripe | 9 | `.vertical-stripe-1` … `-9` |
| Diagonal stripe | 6 | `.diagonal-stripe-1` … `-6` |
| Other | 7 | `.crosshatch`, `.houndstooth`, `.lightstripe`, `.smalldot`, `.subtle-patch`, `.verticalstripe`, `.whitecarbon` |

Representative decoded tiles:

```xml
<!-- circles-1 -->
<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>
  <rect width='10' height='10' fill="white" />
  <circle cx="1" cy="1" r="1" fill="#5594e7"/>
</svg>

<!-- horizontal-stripe-2 -->
<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>
  <rect width='10' height='10' fill='white' />
  <rect x='0' y='0' width='10' height='2' fill='#5594e7' />
</svg>

<!-- diagonal-stripe-1 -->
<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>
  <rect width='10' height='10' fill='white'/>
  <path d='M-1,1 l2,-2 M0,10 l10,-10 M9,11 l2,-2' stroke='#5594e7' stroke-width='1'/>
</svg>
```

## Why it matters here

DrawingML has ~54 **native preset patterns** (`<a:pattFill prst="…">` with
`fgClr`/`bgClr`), and these six families line up with them almost one-to-one:
stripe density maps to `ltHorz`/`horz`/`dkHorz` and the `Vert`/`Diag` variants,
dot density to the `pct5`…`pct90` series and `dotGrid`, crosshatch to
`diagCross`/`cross`/`trellis`, houndstooth to `weave`/`plaid`.

Native `pattFill` is Tier 1: two colours and one enum attribute, no media part,
resolution-independent, and recolourable by the user in PowerPoint. Everything
that falls short of it rasterizes to a tiled PNG (Tier 2), which is heavier and
frozen at one resolution.

**Our preset matcher recognises three shapes.**
`services/pattern_service.py:171-178` maps `dots → dotGrid`, `lines → horz`,
`diagonal → dnDiag`; anything else gets no preset. The feature map records
`<pattern> matching preset` as Done (rows 296-297), which is true only for those
three — every other pattern lands on the Tier 2 tile path.

Note there are two pattern converters and they behave differently on a miss.
The service-level one above (`_convert_pattern`, on the SVG DOM) returns a flat
`solidFill` when no preset matches. The resvg paint path
(`paint/resvg_bridge.py` → `PatternPaint` →
`drawingml/paint_patterns.py:76` `_pattern_to_fill_elem`) tiles instead, emitting
`blipFill` + `<a:tile>` whenever `tile_relationship_id` is set — which is what
gallardo's grille mesh does today. **Which converter runs in which pipeline mode
is not established here**; the verified claim is only that preset coverage is
three shapes wide.

So patternfills is useful to us in two ways:

1. **A ready-made corpus.** 49 real-world patterns, tiny and dependency-free, in
   exactly the shapes designers actually use. Good input for a preset-matching
   test suite — decode each tile to an SVG fixture and assert the expected
   `prst` value.
2. **A mapping table.** The families are already sorted by density
   (`stripe-1` … `stripe-9`), which is the same axis DrawingML's `pct*` and
   `lt`/`dk` presets vary along. That makes it a natural source for a
   density→preset lookup rather than hand-authoring one.

## Caveats

- Tiles are 10×10 with a **white background rect**. DrawingML `bgClr` is a
  colour, not a layer — a tile whose background is meant to be transparent needs
  that detected, not copied as white.
- `.whitecarbon` and `.subtle-patch` are texture-like rather than geometric;
  they have no clean preset equivalent and should stay on the tile path.
- Preset patterns are rendered by PowerPoint's own rasterizer at display
  resolution. Matching a preset is a *substitution*, not a reproduction — the
  tile geometry will not be pixel-identical to the SVG.

## Related

- Feature map rows 296-304 (`<pattern>` handling and `patternUnits`) in
  [`research/svg-to-drawingml-feature-map.md`](research/svg-to-drawingml-feature-map.md)
- `src/svg2ooxml/services/pattern_service.py` — preset matcher
- `src/svg2ooxml/drawingml/paint_patterns.py` — `a:pattFill` emission
